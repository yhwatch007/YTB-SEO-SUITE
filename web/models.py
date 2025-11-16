from django.db import models

class Optimization(models.Model):
    keyword = models.CharField(max_length=200)
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    tags_text = models.CharField(max_length=500, blank=True)

    has_custom_thumbnail = models.BooleanField(default=False)
    in_playlists = models.BooleanField(default=False)

    score = models.PositiveIntegerField(default=0)  # SEO score v1
    entities = models.TextField(blank=True)        # comma-joined list for simplicity

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.keyword} ({self.score})"
