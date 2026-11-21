from django.db import models


class WarningDomain(models.Model):
    """Wpis z Listy Ostrzeżeń CERT Polska. Lista nie podaje typu oszustwa, tylko domenę i daty."""

    domain = models.CharField(max_length=255, unique=True)
    register_position = models.PositiveIntegerField(null=True, blank=True)
    added_at = models.DateTimeField(null=True, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=16, default="cert_pl")

    def __str__(self) -> str:
        return self.domain


class DomainRecord(models.Model):
    """Dane rejestrowe domeny z RDAP."""

    domain = models.CharField(max_length=255, unique=True)
    registered_at = models.DateTimeField(null=True, blank=True)
    registrar = models.CharField(max_length=255, blank=True)
    nameservers = models.JSONField(default=list, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    fetched_at = models.DateTimeField(auto_now=True)
