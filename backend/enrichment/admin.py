from django.contrib import admin

from .models import DomainRecord, WarningDomain


@admin.register(WarningDomain)
class WarningDomainAdmin(admin.ModelAdmin):
    list_display = ["domain", "added_at", "removed_at"]
    search_fields = ["domain"]


admin.site.register(DomainRecord)
