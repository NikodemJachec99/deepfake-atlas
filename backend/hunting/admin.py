from django.contrib import admin

from .models import HuntCandidate, HuntRun


@admin.register(HuntCandidate)
class HuntCandidateAdmin(admin.ModelAdmin):
    list_display = ["domain", "operator", "status", "prelim_score", "bits", "checked_at"]
    list_filter = ["status"]
    search_fields = ["domain"]


admin.site.register(HuntRun)
