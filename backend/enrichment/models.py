from django.db import models
from django.db.models import F, Q


class WarningDomainQuerySet(models.QuerySet):
    def active(self):
        """Wpis jest aktywny, gdy domenę zdjęto z listy nigdy albo zablokowano ponownie po zdjęciu."""
        return self.filter(Q(removed_at__isnull=True) | Q(added_at__gt=F("removed_at")))


class WarningDomain(models.Model):
    """Wpis z Listy Ostrzeżeń CERT Polska. Lista nie podaje typu oszustwa, tylko domenę i daty."""

    domain = models.CharField(max_length=255, unique=True)
    register_position = models.PositiveIntegerField(null=True, blank=True)
    added_at = models.DateTimeField(null=True, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=16, default="cert_pl")

    objects = WarningDomainQuerySet.as_manager()

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


class CertLookup(models.Model):
    """Odpowiedź crt.sh dla domeny. Pamięć podręczna, żeby nie pytać o to samo przy każdej analizie."""

    domain = models.CharField(max_length=255, unique=True)
    raw = models.JSONField(default=list, blank=True)
    fetched_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.domain
