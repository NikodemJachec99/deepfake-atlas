"""Test uruchomienia całego stosu w CI: dwie zmyślone sprawy przez import_bundle, z Postgresem i magazynem S3 z compose.

Uruchamiany w kontenerze backendu przez `manage.py shell`, nie przez pytest (nazwa bez przedrostka test_).
Dane są syntetyczne, te same co w testach importu. Danych organizatora tu nie ma.
"""

import shutil
import sys
from pathlib import Path

from django.core.management import call_command

from ads.models import Ad
from similarity.models import Edge
from tests.test_bundle import ARTICLE_X, make_case

root = Path("/data/raw/syntetyczna")
shutil.rmtree(root, ignore_errors=True)
for name, domain in (("1", "civic-syntetyczna.example"), ("2", "across-syntetyczna.example")):
    make_case(root, name, domain, "Zamach na biznesmena", ARTICLE_X)

call_command("import_bundle", str(root), name="syntetyczna")
ads = Ad.objects.filter(labels__bundle="syntetyczna").count()
edges = list(Edge.objects.filter(ad_a__labels__bundle="syntetyczna", ad_b__labels__bundle="syntetyczna").values_list("relation", flat=True))
print(f"reklamy: {ads}, krawędzie: {edges}")
if ads != 2 or not any(r in ("same_campaign", "same_operator") for r in edges):
    sys.exit("BŁĄD: dwie strony na tym samym zapleczu powinny dać krawędź wspólnego źródła")
print("OK")
