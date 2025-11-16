from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("optimize/", views.optimize, name="optimize"),
    path("discover/", views.discover, name="discover"),
    path("ai/", views.ai_generator, name="ai_generator"),
    path("url/", views.youtube_lookup, name="youtube_lookup"),
    path("tags/", views.tag_finder, name="tag_finder"),
    path("hashtags/", views.hashtag_finder, name="hashtag_finder"),
    path("library/", views.library, name="library"),
]
