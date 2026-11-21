from django.contrib import admin

from .models import Artifact, AuditLog, Marker


@admin.register(Marker)
class MarkerAdmin(admin.ModelAdmin):
    list_display = ["id", "kind", "value", "ad_count"]
    list_filter = ["kind"]
    search_fields = ["value"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "action", "object_type", "object_id"]
    list_filter = ["action"]


admin.site.register(Artifact)
