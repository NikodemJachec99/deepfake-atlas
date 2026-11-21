from django.contrib import admin

from .models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ["name", "wikidata_id"]
    search_fields = ["name", "wikidata_id"]
