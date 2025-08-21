# shortvideo

# Shorts Project — AI-Powered Short Video Generator

Create stunning short clips from YouTube videos using AI-powered suggestions and automated generation — effortlessly craft viral-ready content!

---

## 🚀 Setup and Running the Project

### Prerequisites

- **Python 3.10 or 3.11** (recommended for best compatibility)
- Virtual environment tool (`venv`)
- **YouTube API Key** for accessing YouTube Data API
- **Google Gemini API Key** for AI-powered clip suggestions
- **FFmpeg** installed and added to your system PATH (for video processing)

### Installation Steps

1. **Clone the repository and open the project folder**

2. **Create and activate a virtual environment**

python -m venv venv

macOS/Linux
source venv/bin/activate

Windows PowerShell
.\venv\Scripts\activate

text

3. **Install the necessary dependencies**

pip install -r requirements.txt

text

4. **Create a `.env` file in your project root with the following variables**

YOUTUBE_API_KEY=your_valid_youtube_api_key
GEMINI_API_KEY=your_valid_gemini_api_key

text

5. **Apply database migrations**

python manage.py makemigrations
python manage.py migrate

text

6. **Create an admin superuser account**

python manage.py createsuperuser

text

7. **Start the development server**

python manage.py runserver

text

8. **Visit your project**

Open your browser and go to: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 🔧 Common Issues & Their Solutions

### 1. `ModuleNotFoundError: No module named 'moviepy.editor'`

- **Cause:** The `moviepy` package is missing or virtual environment is not active.
- **Fix:** Activate your environment and install moviepy:

pip install moviepy

text

---

### 2. Pillow `ANTIALIAS` Attribute Error

- **Cause:** Pillow version 10+ removed `ANTIALIAS` constant, but `moviepy` still uses it.
- **Fix:** Add this code to the **top of your `views.py` file**, before importing `moviepy`:

from PIL import Image

if not hasattr(Image, "ANTIALIAS") and hasattr(Image, "Resampling"):
Image.ANTIALIAS = Image.Resampling.LANCZOS

text

---

### 3. Pillow Downgrade Installation Failure

- **Cause:** Older Pillow versions may fail to build on some platforms.
- **Fix:** Use the monkey patch above instead of downgrading Pillow.

---

### 4. Invalid YouTube API Key

- **Cause:** API key missing or incorrect in `.env`.
- **Fix:** Get a valid YouTube Data API key from [Google Cloud Console](https://console.cloud.google.com/), enable YouTube Data API v3, and update `.env`.

---

### 5. Invalid Google Gemini API Key

- **Cause:** API key missing or invalid for Google generative language API.
- **Fix:** Enable the `generativelanguage.googleapis.com` API in Google Cloud Console, generate a key, and add it to `.env`.

---

### 6. Media Files Return 404 Errors

- **Cause:** Improper media file serving or missing files.
- **Fix:**  
  - Verify `MEDIA_URL` and `MEDIA_ROOT` are correct in `settings.py`:  
    ```
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    ```  
  - Ensure your main `urls.py` includes:  
    ```
    from django.conf import settings
    from django.conf.urls.static import static

    if settings.DEBUG:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    ```  
  - Confirm media files actually exist on disk.

---

### 7. Migration Issues

- **Cause:** Model changes not applied or database inconsistencies.
- **Fix:** Run migration commands and fix model syntax errors if any:

python manage.py makemigrations
python manage.py migrate

text

---

## 📦 Dependency Versions (`requirements.txt`)

Ensure compatibility by using these package versions:

Django==4.2.7
moviepy==2.2.1
Pillow<10.0.0,>=9.0.0
yt-dlp==2023.9.17
google-api-python-client==2.97.0
google-generativeai==0.1.6
python-dotenv==1.1.1
webvtt-py==0.4.1

text

> **Note:** If Pillow fails to install the recommended version, keep the latest Pillow and apply the monkey patch provided above.

---

## 💡 Additional Tips

- Always activate your virtual environment before running any project commands.
- Restart your server after changing environment variables or dependencies.
- Use your IDE’s Python interpreter configured to the virtual environment for smooth development.
- Monitor terminal logs closely for debugging assistance.

---
