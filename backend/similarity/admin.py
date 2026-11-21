from django.contrib import admin

from .models import Campaign, CampaignMembership, Edge, EdgeEvidence


class EdgeEvidenceInline(admin.TabularInline):
    model = EdgeEvidence
    extra = 0
    fields = ["family", "kind", "value_a", "value_b", "similarity", "df", "weight_bits", "decisive"]
    readonly_fields = fields


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    """Etykietowanie zbioru złotego: analityk ogląda dowody i zapisuje decyzję."""

    list_display = ["id", "ad_a", "ad_b", "relation", "probability", "decisive", "verdict"]
    list_filter = ["relation", "verdict", "decisive"]
    list_editable = ["verdict"]
    raw_id_fields = ["ad_a", "ad_b", "verdict_by"]
    inlines = [EdgeEvidenceInline]


class MembershipInline(admin.TabularInline):
    model = CampaignMembership
    extra = 0
    raw_id_fields = ["ad"]


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ["id", "key", "label", "created_at"]
    inlines = [MembershipInline]
