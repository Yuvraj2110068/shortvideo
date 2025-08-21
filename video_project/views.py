# video_project/views.py

import os
import uuid
import json
import logging
import threading
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, FileResponse, Http404
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.views.decorators.http import require_POST
from django.core.cache import cache

# Ensure moviepy and PIL are installed:
# pip install moviepy Pillow
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip, vfx # Import vfx
from moviepy.video.fx.all import fadein, fadeout, resize, crop
from PIL import Image as PILImage # Renamed to avoid conflict with ImageClip, already good

import google.generativeai as genai

from .models import VideoProject

logger = logging.getLogger(__name__)

# Configure Gemini (ensure settings.GEMINI_API_KEY is set)
genai_configured = False
try:
    if settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        genai_configured = True
    else:
        logger.error("GEMINI_API_KEY not set. AI caption features disabled.")
except Exception as e:
    logger.error(f"Error during Gemini configuration: {e}. AI caption features disabled.")
    genai = None

# --- Helper Functions ---

def time_to_seconds(t_str):
    """Converts MM:SS or HH:MM:SS string to seconds."""
    try:
        parts = list(map(int, t_str.split(':')))
        if len(parts) == 2: # MM:SS
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3: # HH:MM:SS
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except (ValueError, IndexError):
        logger.error(f"Invalid time format: {t_str}")
        return 0
    return 0

def get_project_media_dir(project_id):
    """Returns the absolute path for a project's media directory."""
    # Using os.path.join with settings.MEDIA_ROOT ensures absolute paths
    return os.path.join(settings.MEDIA_ROOT, 'video_projects', str(project_id))

def get_project_media_url(project_id):
    """Returns the URL path for a project's media directory."""
    # This is for URL generation, not file system paths
    return os.path.join(settings.MEDIA_URL, 'video_projects', str(project_id))


# --- Views ---

def project_list(request):
    """Displays a list of all video projects."""
    projects = VideoProject.objects.all()
    return render(request, 'video_project/project_list.html', {'projects': projects})

@require_POST
def create_project(request):
    """Handles creating a new video project."""
    title = request.POST.get('title', 'New Video Project')
    project = VideoProject.objects.create(title=title)
    # Ensure the project directory is created immediately upon project creation
    project_dir = get_project_media_dir(project.id)
    os.makedirs(project_dir, exist_ok=True)
    return redirect('video_project:edit_project', project_id=project.id)

def edit_project(request, project_id):
    """Handles editing an existing video project."""
    project = get_object_or_404(VideoProject, id=project_id)
    return render(request, 'video_project/edit_project.html', {'project': project})

@require_POST
def upload_image(request):
    """Handles image uploads for a specific project."""
    if not request.FILES.get('image'):
        return JsonResponse({'status': 'error', 'message': 'No image provided.'}, status=400)

    project_id = request.POST.get('project_id')
    if not project_id:
        return JsonResponse({'status': 'error', 'message': 'Project ID is required.'}, status=400)

    project = get_object_or_404(VideoProject, id=project_id)
    uploaded_file = request.FILES['image']

    project_dir = get_project_media_dir(project_id)
    os.makedirs(project_dir, exist_ok=True) # Ensure directory exists

    fs = FileSystemStorage(location=project_dir, base_url=get_project_media_url(project_id))
    filename = fs.save(uploaded_file.name, uploaded_file)
    file_url = fs.url(filename) # This will be a relative URL from MEDIA_URL

    width, height = 0, 0
    try:
        # Construct the full absolute path for PIL to open
        full_image_path = os.path.join(project_dir, filename)
        with PILImage.open(full_image_path) as img:
            width, height = img.size
    except Exception as e:
        logger.error(f"Could not get image dimensions for {full_image_path}: {e}")

    image_info = {
        'id': str(uuid.uuid4()),
        'image_path': file_url, # Store the URL for front-end use
        'filename': filename, # Store filename for backend file system access
        'duration': 5,
        'order': len(project.image_data),
        'width': width,
        'height': height,
    }
    project.image_data.append(image_info)
    project.save()

    return JsonResponse({
        'status': 'success',
        'message': 'Image uploaded successfully.',
        'image_info': image_info
    })

@require_POST
def generate_video(request, project_id):
    """Starts the video generation process in a separate thread."""
    try:
        project = get_object_or_404(VideoProject, id=project_id)
        data = json.loads(request.body)

        # Get updated project data from frontend
        project.image_data = data.get('image_data', [])
        project.text_overlays = data.get('text_overlays', [])
        # IMPORTANT: Ensure audio_path is a server-side file path, not a browser blob URL.
        # If audio is uploaded via another endpoint, its path should be stored correctly.
        project.audio_path = data.get('audio_path')
        project.save()

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        logger.error(f"Error preparing video generation for project {project_id}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Error preparing video generation: {e}'}, status=500)

    project.status = 'generating'
    project.message = 'Video generation started...'
    project.save()
    cache.set(f'project_progress_{project_id}', {"status": "PENDING", "progress": 0, "message": "Initializing video generation..."})

    # Start the generation in a separate thread
    threading.Thread(target=_generate_video_task, args=(project_id,)).start()

    return JsonResponse({'status': 'processing', 'message': 'Video generation started.'})


def _generate_video_task(project_id):
    """Background task to generate the video using MoviePy."""
    project = VideoProject.objects.get(id=project_id)
    project_dir = get_project_media_dir(project_id)
    cache_key = f'project_progress_{project_id}'

    final_clip = None # Initialize final_clip for the finally block

    try:
        sorted_images = sorted(project.image_data, key=lambda x: x.get('order', 0))
        if not sorted_images:
            raise ValueError("No images found for this project.")

        clips = []
        target_width, target_height = 1920, 1080 # Full HD (16:9 aspect ratio)

        cache.set(cache_key, {"status": "processing", "progress": 10, "message": "Composing image clips..."})

        for i, img_data in enumerate(sorted_images):
            image_filename = img_data.get('filename') # This is the stored filename
            duration = img_data.get('duration', 5)
            if not image_filename:
                logger.warning(f"Skipping image with missing filename in project {project_id}")
                continue

            # Construct the full absolute path for MoviePy ImageClip
            image_full_path = os.path.join(project_dir, image_filename)
            if not os.path.exists(image_full_path):
                logger.error(f"Image file not found: {image_full_path}. Skipping.")
                project.message += f" (Missing image: {image_filename})"
                continue

            try:
                image_clip = ImageClip(image_full_path, duration=duration)

                # Resize and crop logic to fit 16:9 aspect ratio
                img_w, img_h = image_clip.size
                aspect_ratio_target = target_width / target_height
                aspect_ratio_img = img_w / img_h

                if aspect_ratio_img > aspect_ratio_target:
                    # Image is wider than target, crop width
                    new_width = int(img_h * aspect_ratio_target)
                    image_clip = crop(image_clip, width=new_width, height=img_h, x_center=img_w/2, y_center=img_h/2)
                elif aspect_ratio_img < aspect_ratio_target:
                    # Image is taller than target, crop height
                    new_height = int(img_w / aspect_ratio_target)
                    image_clip = crop(image_clip, width=img_w, height=new_height, x_center=img_w/2, y_center=img_h/2)

                # Finally resize to target dimensions
                image_clip = resize(image_clip, newsize=(target_width, target_height))

                # Add fades
                if i > 0: image_clip = image_clip.fx(fadein, 0.5)
                if i < len(sorted_images) - 1: image_clip = image_clip.fx(fadeout, 0.5)

                clips.append(image_clip)
                progress = 10 + (i / len(sorted_images)) * 40
                cache.set(cache_key, {"status": "processing", "progress": progress, "message": f"Composing image {i+1}/{len(sorted_images)}..."})

            except Exception as e:
                logger.error(f"Error processing image {image_full_path}: {e}", exc_info=True)
                project.message += f" (Image processing error for {image_filename}: {e})"
                continue # Try to continue with other images

        if not clips:
            raise ValueError("No valid image clips to generate video. Check image paths and processing errors.")

        # Concatenate all image clips into a single video clip
        final_clip = CompositeVideoClip(clips, size=(target_width, target_height))
        video_duration = final_clip.duration

        cache.set(cache_key, {"status": "processing", "progress": 50, "message": "Adding text overlays..."})

        text_clips = []
        for text_data in project.text_overlays:
            text_content = text_data.get('text', '')
            if not text_content: continue

            start_s = time_to_seconds(text_data.get('start_time', '00:00'))
            end_s = time_to_seconds(text_data.get('end_time', '00:05'))
            if end_s <= start_s: end_s = start_s + 1 # Ensure duration is positive

            try:
                # Using method='caption' should prevent ImageMagick from being called for text.
                # It relies on Pillow (PIL) for text rendering.
                # 'font' should ideally be a system-installed font name or a path to a .ttf file.
                # Using a generic 'sans-serif' or a known system font is often safer.
                txt_clip = TextClip(
                    text_content,
                    fontsize=text_data.get('font_size', 70),
                    color=text_data.get('color', 'white'),
                    font='sans-serif', # Changed to a more generic font name for better compatibility
                    method='caption', # This ensures Pillow is used, not ImageMagick for text
                    align='center',
                    size=(target_width - 100, None) # Provide a width for the caption to wrap
                ).set_start(start_s).set_duration(end_s - start_s).set_position(('center', text_data.get('position', 'center')))
                text_clips.append(txt_clip)
            except Exception as e:
                logger.error(f"Error creating TextClip for content '{text_content}': {e}", exc_info=True)
                project.message += f" (Text overlay error: {e})"
                continue # Try to continue with other elements

        if text_clips:
            # Add text clips as overlays on the final_clip
            final_clip = CompositeVideoClip([final_clip] + text_clips, size=final_clip.size)


        cache.set(cache_key, {"status": "processing", "progress": 70, "message": "Adding audio..."})

        if project.audio_path:
            # The audio_path should be an absolute path to the audio file on the server.
            # It's crucial that this path is correctly formed.
            audio_full_path = os.path.join(settings.MEDIA_ROOT, project.audio_path.lstrip(settings.MEDIA_URL))

            if os.path.exists(audio_full_path):
                try:
                    audio_clip = AudioFileClip(audio_full_path)
                    # Trim audio to video duration or loop if audio is shorter
                    if audio_clip.duration < final_clip.duration:
                        # If audio is shorter, loop it
                        audio_clip = audio_clip.fx(vfx.loop, duration=final_clip.duration)
                    elif audio_clip.duration > final_clip.duration:
                        audio_clip = audio_clip.subclip(0, final_clip.duration)
                    final_clip = final_clip.set_audio(audio_clip)
                except Exception as e:
                    logger.error(f"Error adding audio {audio_full_path}: {e}", exc_info=True)
                    project.message += f" (Audio error: {e})"
            else:
                logger.warning(f"Audio file not found: {audio_full_path}. Skipping audio.")
                project.message += " (Audio file not found)"

        # Define output directories and filenames
        output_dir = os.path.join(settings.MEDIA_ROOT, 'generated_videos')
        os.makedirs(output_dir, exist_ok=True) # Ensure output directory exists

        video_filename = f'{project_id}.mp4'
        thumbnail_filename = f'{project_id}.png'
        video_full_path = os.path.join(output_dir, video_filename)
        thumbnail_full_path = os.path.join(output_dir, thumbnail_filename)

        cache.set(cache_key, {"status": "processing", "progress": 80, "message": "Rendering video..."})

        # Render the video
        # Increased threads for potentially faster rendering
        # Ensure 'preset' is a valid FFmpeg preset (e.g., 'medium', 'fast', 'slow')
        final_clip.write_videofile(
            video_full_path,
            codec="libx264",
            audio_codec="aac",
            fps=24,
            preset="medium",
            threads=os.cpu_count() or 4 # Use all CPU cores or default to 4
        )
        # Save a thumbnail
        final_clip.save_frame(thumbnail_full_path, t=min(1, final_clip.duration / 2)) # Thumbnail at 1s or halfway

        # Update project status and paths
        project.final_video_path = os.path.join(settings.MEDIA_URL, 'generated_videos', video_filename)
        project.thumbnail_path = os.path.join(settings.MEDIA_URL, 'generated_videos', thumbnail_filename)
        project.status = 'completed'
        project.message = 'Video generated successfully!'
        cache.set(cache_key, {"status": "complete", "progress": 100, "message": "Video generation complete!"})

    except Exception as e:
        logger.error(f"Error during video generation for project {project_id}: {e}", exc_info=True)
        project.status = 'failed'
        project.message = f"Video generation failed: {e}"
        cache.set(cache_key, {"status": "error", "progress": 0, "message": project.message})
    finally:
        project.save()
        # Ensure resources are closed
        if final_clip:
            final_clip.close()
        # Clean up temporary files if any were created by moviepy (MoviePy usually handles this well)


def check_generation_progress(request, project_id):
    """Checks the progress of video generation."""
    cache_key = f'project_progress_{project_id}'
    progress_data = cache.get(cache_key, {"status": "PENDING", "progress": 0, "message": "Initializing..."})
    return JsonResponse(progress_data)

def download_video(request, project_id):
    """Allows downloading the generated video."""
    project = get_object_or_404(VideoProject, id=project_id)
    if not project.final_video_path:
        raise Http404("Video not yet generated or path not found.")

    # Construct the full absolute path from the stored URL
    # project.final_video_path usually starts with /media/ or similar.
    # settings.BASE_DIR is the root of your Django project.
    # lstrip('/') is used to remove leading slash so os.path.join works correctly.
    full_path = os.path.join(settings.BASE_DIR, project.final_video_path.lstrip('/'))
    # Alternative and possibly more robust:
    # full_path = os.path.join(settings.MEDIA_ROOT, os.path.basename(project.final_video_path))


    if os.path.exists(full_path):
        return FileResponse(open(full_path, 'rb'), as_attachment=True, filename=os.path.basename(project.final_video_path))
    raise Http404(f"File not found at {full_path}")

@require_POST
def delete_project(request, project_id):
    """Deletes a video project and its associated files."""
    project = get_object_or_404(VideoProject, id=project_id)

    # Clean up final generated video and thumbnail
    if project.final_video_path:
        # Reconstruct the absolute path to the generated video
        gen_video_path = os.path.join(settings.MEDIA_ROOT, 'generated_videos', f'{project.id}.mp4')
        if os.path.exists(gen_video_path):
            os.remove(gen_video_path)
            logger.info(f"Deleted generated video: {gen_video_path}")
    if project.thumbnail_path:
        # Reconstruct the absolute path to the thumbnail
        gen_thumbnail_path = os.path.join(settings.MEDIA_ROOT, 'generated_videos', f'{project.id}.png')
        if os.path.exists(gen_thumbnail_path):
            os.remove(gen_thumbnail_path)
            logger.info(f"Deleted generated thumbnail: {gen_thumbnail_path}")

    # Clean up project-specific media directory (uploaded images/audio)
    project_dir = get_project_media_dir(project.id)
    if os.path.exists(project_dir):
        import shutil
        try:
            shutil.rmtree(project_dir)
            logger.info(f"Deleted project media directory: {project_dir}")
        except OSError as e:
            logger.error(f"Error deleting project directory {project_dir}: {e}")

    project.delete()
    return JsonResponse({'status': 'success', 'message': 'Project deleted successfully.'})


@require_POST
def ai_caption_suggestion(request):
    """Provides AI-suggested captions based on provided image descriptions."""
    if not genai_configured:
        return JsonResponse({'status': 'error', 'message': 'AI features are not configured.'}, status=500)

    try:
        data = json.loads(request.body)
        image_descriptions = data.get('image_descriptions', [])
        if not image_descriptions:
            return JsonResponse({'status': 'error', 'message': 'No image descriptions provided.'}, status=400)

        context_text = "\n".join([f"Image {i+1}: {desc}" for i, desc in enumerate(image_descriptions)])
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Based on the following sequence of image descriptions, suggest a short, engaging caption for each image.
        The captions should be concise and suitable for a short video.
        Return a JSON array of strings, where each string is a suggested caption for the corresponding image.
        Example: ["Caption for image 1", "Caption for image 2"]

        Image Descriptions:
        {context_text}
        """
        response = model.generate_content(prompt)
        # Clean up potential markdown code fences from the AI response
        json_response_text = response.text.strip().lstrip("```json").rstrip("```").strip()
        suggested_captions = json.loads(json_response_text)

        if not isinstance(suggested_captions, list):
            raise ValueError("AI did not return a list of captions.")

        return JsonResponse({'status': 'success', 'captions': suggested_captions})

    except json.JSONDecodeError as e:
        logger.error(f"AI returned invalid JSON format: {e}. Raw response: {response.text if 'response' in locals() else 'N/A'}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'AI returned an invalid format: {e}'}, status=500)
    except Exception as e:
        logger.error(f"Error calling Gemini API for captions: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'AI caption suggestion failed: {e}'}, status=500)