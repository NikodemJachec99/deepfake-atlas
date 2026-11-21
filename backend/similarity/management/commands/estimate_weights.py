"""Szacuje wagi modelu z danych (EM Fellegi-Sunter bez etykiet), porównuje je z eksperckimi i zapisuje JSON.

Niczego nie zapisuje w bazie. Plik wynikowy włącza się ustawieniem MODEL_WEIGHTS=learned.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ads.models import Ad
from similarity import learning


class Command(BaseCommand):
    help = "EM Fellegi-Sunter na parach kandydatów: m, u i bity dla każdego typu markera, raport porównania z wagami eksperckimi."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=None, help="Plik wyniku (domyślnie MODEL_WEIGHTS_PATH, data/models/wagi.json)")
        parser.add_argument("--source", default="capture", help="Pary między reklamami z tego źródła; pusty napis: wszystkie")
        parser.add_argument("--bootstrap", type=int, default=30, help="Liczba powtórzeń do oceny stabilności (0: bez)")
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--no-write", action="store_true", help="Tylko raport, bez zapisu pliku")
        parser.add_argument("--json", action="store_true", help="Raport porównania jako JSON zamiast tekstu")

    def handle(self, *args, **options):
        source = options["source"] or None
        pairs, n_ads = learning.collect_pairs(source)
        if len(pairs) < 20:
            raise CommandError(f"Za mało par do uczenia: {len(pairs)} (reklam: {n_ads}). Potrzeba co najmniej 20.")
        data = learning.build_weights(pairs, n_ads, options["bootstrap"], options["seed"], source)

        weights = learning.weights_from(data)
        samples, counts = learning.decision_samples(weights)
        data["calibration"] = learning.calibrate(samples)
        data["calibration"]["verdicts"] = dict(counts)

        ad_labels = {ad.pk: f"{ad.labels.get('bundle', ad.source)}/{ad.labels.get('case', ad.external_id)}" for ad in Ad.objects.filter(source=source)} if source else {}
        report = learning.compare(pairs, data, lambda p: f"{ad_labels.get(p.a, p.a)} | {ad_labels.get(p.b, p.b)}")
        data["comparison"] = {k: report[k] for k in ("pairs", "with_relation", "same_source", "relation_changes", "transitions", "core", "groups")}

        if not options["no_write"]:
            out = Path(options["out"] or settings.MODEL_WEIGHTS_PATH)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
            self.stdout.write(f"zapisano {out}")
        if options["json"]:
            self.stdout.write(json.dumps({"meta": data["meta"], "calibration": data["calibration"], "report": report}, ensure_ascii=False, indent=1))
            return
        self.print_report(data, report)

    def print_report(self, data: dict, report: dict):
        w = self.stdout.write
        m = data["meta"]
        w(f"reklam: {m['ads']}, par kandydatów: {m['pairs']} (ze zgodnością: {m['pairs_with_agreement']}), źródło: {m['source']}")
        for name, c in m["classes"].items():
            w(f"EM klasa {name}: {c['iterations']} iteracji, zbieżność: {'tak' if c['converged'] else 'NIE'}, udział par pasujących: {c['match_share']}, "
              f"oczekiwane pary pasujące: {c['expected_matches']}")
        w(f"typy uczone z par: {m['learned_kinds']} z {m['kinds']} (reszta: za mało par, zostaje ekspercka wartość)")
        w(f"stabilność (bootstrap po reklamach, {m['bootstrap']} prób): typów z odchyleniem powyżej {learning.UNSTABLE_STD_BITS:g} bitów: {m['unstable_kinds']}, "
          f"udział {m['unstable_share']}, ocena: {'stabilne' if m['stable'] else 'NIESTABILNE'}")
        cal = data["calibration"]
        if cal["fitted"]:
            w(f"kalibracja: {cal['decisions']} decyzji (potwierdzone {cal['confirmed']}, odrzucone {cal['rejected']}), Brier na zbiorze uczącym {cal['brier_train']}")
        else:
            w(f"{cal['note']} (decyzje w bazie: {cal['verdicts'] or 0})")
        s, ws = report["same_source"], report["with_relation"]
        w(f"porównanie expert vs learned na {report['pairs']} parach: relacja się zmienia w {report['relation_changes']}, "
          f"z relacją: {ws['expert']} vs {ws['learned']}, wspólne źródło: {s['expert']} vs {s['learned']} (utrata {s['lost']}, nowe {s['gained']})")
        if report["transitions"]:
            w(f"  przejścia: {report['transitions']}")
        c = report["core"]
        w(f"rdzeń operatora A (funnel_id i meta_pixel): {c['kept']} z {c['pairs']} par zostaje; utracone: {c['lost'] or 'brak'}")
        g = report["groups"]
        w(f"grupy wspólnego źródła: {g['expert']} vs {g['learned']}, rozpadły się: {g['expert_groups_split']}, "
          f"nowe grupy scalające kilka eksperckich: {g['learned_groups_merging_expert']}")
        w("typy o największej różnicy wag (bity: uczone minus eksperckie):")
        for d in report["kind_differences"][:10]:
            std = "" if d["bits_std"] is None else f", odch. {d['bits_std']}"
            w(f"  {d['kind']:<18} {d['expert_bits']:>6} -> {d['learned_bits']:>6}  ({d['diff']:+}, {d['source']}, par ze zgodnością {d['pairs_agree']}{std})")
        w(f"pary graniczne lub ze zmianą relacji: {len(report['borderline'])}")
        for row in report["borderline"][:25]:
            w(f"  {row['pair']}: {row['expert']} ({row['expert_probability']}, {row['expert_bits']} b) -> {row['learned']} "
              f"({row['learned_probability']}, {row['learned_bits']} b)  [{', '.join(row['kinds'])}]")
        for name, key in (("nowe połączenia wspólnego źródła", "gained_same_source"), ("utracone połączenia wspólnego źródła", "lost_same_source")):
            if report[key]:
                w(f"{name}:")
                for row in report[key]:
                    w(f"  {row['pair']}: {row['expert']} -> {row['learned']} [{', '.join(row['kinds'])}]")
