"""Ewaluacja wersji pytania Jev na stanach syntetycznych (#72). Raport JSON, bez zapisu do bazy.

Wysyła wyłącznie stany wygenerowane w `similarity/evaluation.py`, nic z bazy ani z materiałów organizatora.
Dlatego nie wymaga `JEV_ALLOW_CASE_DATA`, ale wymaga trybu, przypiętego modelu i klucza jak `jev_review`.
"""

import dataclasses
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from similarity import assist, evaluation


class Command(BaseCommand):
    help = "Porównuje regułę bez modelu i wersje pytania Jev na stanach syntetycznych (similarity/evaluation.py)."

    def add_arguments(self, parser):
        parser.add_argument("--versions", default=",".join(assist.QUESTIONS), help="Wersje pytania po przecinku.")
        parser.add_argument("--sample", type=int, default=evaluation.SAMPLE, help="Liczba stanów syntetycznych.")
        parser.add_argument("--out", required=True, help="Plik JSON z raportem.")

    def handle(self, *args, **options):
        # Stany syntetyczne nie są danymi spraw, więc zgoda na ich wysyłkę nie jest potrzebna.
        config = dataclasses.replace(assist.Config.from_settings(), allow_case_data=True)
        try:
            client = assist.JevClient(config)
        except assist.AssistDisabled as exc:
            raise CommandError(str(exc)) from exc
        versions = [v for v in options["versions"].split(",") if v]
        unknown = [v for v in versions if v not in assist.QUESTIONS]
        if unknown:
            raise CommandError(f"nieznane wersje pytania: {unknown}")
        cases = evaluation.synthetic_cases(options["sample"])
        report = evaluation.run(client, versions, cases, float(getattr(settings, "JEV_BUDGET_USD", 0.10)),
                                float(getattr(settings, "JEV_PRICE_PER_MTOK", 0.042)))
        report["model"] = config.model
        Path(options["out"]).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        for split in ("val", "test"):
            for key, m in report["splits"][split].items():
                self.stdout.write(f"{split:4} {key:16} n={m['n']:3} pokrycie={m['coverage']} trafność={m['accuracy']} "
                                  f"zbalansowana={m['balanced_accuracy']} recall_przeglad={m['recall_przeglad']} "
                                  f"recall_spojne={m['recall_spojne']} brier={m.get('brier_przeglad')}")
        self.stdout.write(f"wybrana na walidacji: {report['chosen_on_val']}; etykiety: {report['labels']}")
        for name, res in report["robustness"].items():
            self.stdout.write(f"odporność {name}: {res}")
        self.stdout.write(f"tokenów {report['input_tokens']}, koszt ok. {report['cost_usd']} USD, przerwane: {report['stopped'] or 'nie'}")
