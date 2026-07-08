"""Produce the import report deliverable from the command line.

Runs the same analysis the app runs on upload (no DB writes) and prints/saves
the report. This gives us a committable artifact and a quick way to re-verify
detection during the live session.

    python manage.py generate_import_report --file "../expenses_export ....xlsx" \
        --out ../import_report.json
"""

import json

from django.core.management.base import BaseCommand

from apps.importer.services.detectors import analyze
from apps.importer.services.parsing import parse_upload
from apps.importer.services.roster import default_roster


class Command(BaseCommand):
    help = "Analyze an export file and emit the anomaly import report."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--out", default=None)

    def handle(self, *args, **opts):
        with open(opts["file"], "rb") as f:
            rows = analyze(parse_upload(f, opts["file"]), default_roster())

        counts = {}
        findings = []
        for r in rows:
            for a in r["anomalies"]:
                counts[a.code] = counts.get(a.code, 0) + 1
                findings.append(
                    {
                        "row": r["row_number"],
                        "description": r["raw"].get("description"),
                        "code": a.code,
                        "severity": a.severity,
                        "message": a.message,
                        "action": a.action,
                    }
                )

        report = {
            "file": opts["file"],
            "total_rows": len(rows),
            "rows_with_anomalies": sum(1 for r in rows if r["anomalies"]),
            "distinct_anomaly_types": len(counts),
            "anomaly_counts": counts,
            "findings": findings,
        }

        text = json.dumps(report, indent=2, ensure_ascii=False)
        if opts["out"]:
            with open(opts["out"], "w", encoding="utf-8") as fh:
                fh.write(text)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Wrote report ({report['distinct_anomaly_types']} anomaly "
                    f"types, {report['rows_with_anomalies']} rows) to {opts['out']}"
                )
            )
        else:
            self.stdout.write(text)
