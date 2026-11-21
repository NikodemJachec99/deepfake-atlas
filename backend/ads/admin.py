from django.contrib import admin

from .models import Ad, AdSnapshot, Advertiser, Analysis, AnalysisEvent


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ["id", "source", "title", "landing_url", "first_seen"]
    list_filter = ["source"]
    search_fields = ["title", "text", "landing_url", "external_id"]
    exclude = ["text_embedding", "image_embedding"]
    raw_id_fields = ["advertiser"]


@admin.register(Advertiser)
class AdvertiserAdmin(admin.ModelAdmin):
    list_display = ["id", "source", "name", "payer"]
    search_fields = ["name", "payer", "external_id"]


class AnalysisEventInline(admin.TabularInline):
    model = AnalysisEvent
    extra = 0
    readonly_fields = ["seq", "stage", "status", "message", "payload", "created_at"]


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ["id", "input_kind", "status", "created_at", "finished_at"]
    list_filter = ["status", "input_kind"]
    inlines = [AnalysisEventInline]
    raw_id_fields = ["ad"]


admin.site.register(AdSnapshot)
