# video_project/models.py

from django.db import models
import uuid

class VideoProject(models.Model):
    """
    Represents a single video project created by the user.
    A project consists of multiple images, text overlays, and an audio track.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Store JSON string of image paths, order, and durations
    # Example: [{"image_path": "/media/projects/img1.jpg", "duration": 5}, ...]
    image_data = models.JSONField(default=list)
    # Store JSON string of text overlays
    # Example: [{"text": "Hello", "start_time": 1, "end_time": 3, "font": "Arial", "color": "#FFFFFF"}, ...]
    text_overlays = models.JSONField(default=list)
    # Store path to the audio file
    audio_path = models.CharField(max_length=255, blank=True, null=True)
    # Store the path to the final generated video
    final_video_path = models.CharField(max_length=255, blank=True, null=True)
    # Store the path to the thumbnail of the final video
    thumbnail_path = models.CharField(max_length=255, blank=True, null=True)
    # Status of video generation (e.g., 'pending', 'generating', 'completed', 'failed')
    status = models.CharField(max_length=50, default='pending')
    # Any messages related to status or errors
    message = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']