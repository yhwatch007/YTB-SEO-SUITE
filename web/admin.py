from django.contrib import admin
from .models import Optimization

@admin.register(Optimization)
class OptimizationAdmin(admin.ModelAdmin):
    list_display = ("keyword", "score", "created_at")
    search_fields = ("keyword", "title", "tags_text")
    list_filter = ("created_at",)
