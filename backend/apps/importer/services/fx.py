"""Currency conversion to INR, dated per expense (Priya's complaint).

Strategy:
  1. INR -> INR is always 1.
  2. Otherwise look for a cached rate for that exact date (FxRate table).
  3. Otherwise fetch the historical rate from Frankfurter (free, no key) and
     cache it.
  4. If the network is unavailable, fall back to a documented constant and
     mark the rate `source=fallback` so the report is honest about it.

The rate we use is stored on the Expense (fx_rate) so every rupee figure is
reproducible and explainable line by line.
"""

from decimal import Decimal

import requests
from django.conf import settings

# Documented offline fallback (approx. USD->INR for early 2026). Only used if
# the API cannot be reached; flagged as such in the import report.
FALLBACK_RATES = {("USD", "INR"): Decimal("86.0")}


def get_rate(on_date, base: str, quote: str = "INR") -> tuple[Decimal, str]:
    """Return (rate, source). rate converts `base` into `quote`."""
    base = (base or "INR").upper()
    quote = quote.upper()
    if base == quote:
        return Decimal("1"), "identity"

    from ..models import FxRate

    cached = FxRate.objects.filter(
        on_date=on_date, base=base, quote=quote
    ).first()
    if cached:
        return cached.rate, cached.source

    rate, source = _fetch(on_date, base, quote)
    FxRate.objects.get_or_create(
        on_date=on_date,
        base=base,
        quote=quote,
        defaults={"rate": rate, "source": source},
    )
    return rate, source


def _fetch(on_date, base: str, quote: str) -> tuple[Decimal, str]:
    url = f"{settings.FX_PROVIDER_URL.rstrip('/')}/{on_date.isoformat()}"
    try:
        resp = requests.get(
            url, params={"base": base, "symbols": quote}, timeout=10
        )
        resp.raise_for_status()
        rate = resp.json()["rates"][quote]
        return Decimal(str(rate)), "frankfurter"
    except Exception:
        fallback = FALLBACK_RATES.get((base, quote))
        if fallback is None:
            raise
        return fallback, "fallback"
