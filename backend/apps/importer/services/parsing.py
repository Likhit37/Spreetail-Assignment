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
    rows = list(ws.iter_rows())  # cell objects, so we can read number_format
    if not rows:
        return []
    header = [
        str(c.value).strip() if c.value is not None else "" for c in rows[0]
    ]
    try:
        date_idx = header.index("date")
    except ValueError:
        date_idx = 0
    out = []
    for i, row in enumerate(rows[1:], start=1):
        raw = {header[j]: _cell(row[j].value) for j in range(len(header))}
        # The date cell's Excel number format disambiguates weird dates
        # (e.g. a month-year format hides the day). Detectors use it.
        date_format = row[date_idx].number_format if date_idx < len(row) else None
        out.append(
            {"row_number": i, "raw": raw, "meta": {"date_format": date_format}}
        )
    return out


def parse_csv(file_obj) -> list[dict]:
    data = file_obj.read()
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(data))
    out = []
    for i, row in enumerate(reader, start=1):
        out.append(
            {
                "row_number": i,
                "raw": {k: (v if v != "" else None) for k, v in row.items()},
                "meta": {},  # CSV carries no cell-format info
            }
        )
    return out


def parse_upload(file_obj, filename: str) -> list[dict]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return parse_csv(file_obj)
    return parse_xlsx(file_obj)
