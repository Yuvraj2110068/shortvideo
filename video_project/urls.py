
# video_project/urls.py

from django.urls import path
from . import views

app_name = 'video_project'

urlpatterns = [
    path('', views.project_list, name='project_list'),
    path('create/', views.create_project, name='create_project'),
    path('edit/<uuid:project_id>/', views.edit_project, name='edit_project'),
    path('upload_image/', views.upload_image, name='upload_image'), # For AJAX image uploads
    path('generate_video/<uuid:project_id>/', views.generate_video, name='generate_video'),
    path('check_generation_progress/<uuid:project_id>/', views.check_generation_progress, name='check_generation_progress'),
    path('download_video/<uuid:project_id>/', views.download_video, name='download_video'),
    path('delete_project/<uuid:project_id>/', views.delete_project, name='delete_project'),
    path('ai_caption_suggestion/', views.ai_caption_suggestion, name='ai_caption_suggestion'),
]