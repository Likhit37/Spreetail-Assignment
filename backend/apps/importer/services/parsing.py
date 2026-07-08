"""Read the export file into raw rows without altering any value.

We accept the file exactly as provided. The assignment calls it a CSV but ships
an .xlsx; we handle both. Nothing is cleaned here — cleaning and judgement are
the detectors' job. We only turn cells into JSON-serialisable primitives and
remember the 1-based data row number for the report.
"""

import csv
import datetime as dt
import io

EXPECTED_COLUMNS = [
    "date",
    "description",
    "paid_by",
    "amount",
    "currency",
    "split_type",
    "split_with",
    "split_details",
    "notes",
]


def _cell(value):
    """Make a cell JSON-safe while preserving its meaning."""
    if value is None:
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.date().isoformat() if isinstance(value, dt.datetime) else value.isoformat()
    return value


def parse_xlsx(file_obj) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(file_obj, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    out = []
    for i, row in enumerate(rows[1:], start=1):
        raw = {header[j]: _cell(row[j]) for j in range(len(header))}
        out.append({"row_number": i, "raw": raw})
    return out


def parse_csv(file_obj) -> list[dict]:
    data = file_obj.read()
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(data))
    out = []
    for i, row in enumerate(reader, start=1):
        out.append({"row_number": i, "raw": {k: (v if v != "" else None) for k, v in row.items()}})
    return out


def parse_upload(file_obj, filename: str) -> list[dict]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return parse_csv(file_obj)
    return parse_xlsx(file_obj)
