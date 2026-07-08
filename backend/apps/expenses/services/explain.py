"""Plain-English balance explanation (the JD's "ship an LLM feature" ask).

We hand the model the member's *computed* ledger — never the raw sheet — and
ask it to narrate. The numbers come from our balance engine, so the LLM only
phrases what we already proved; it can't invent a balance. If no API key is
configured we fall back to a deterministic template, so the feature degrades
gracefully and the demo never depends on a network call.
"""

from django.conf import settings

from .balances import member_ledger


def _build_prompt(ledger: dict) -> str:
    lines = [
        f"Member: {ledger['member']}",
        f"Net position: ₹{ledger['net_inr']} ({ledger['interpretation']}).",
        "",
        "Expenses they paid for the group:",
    ]
    for p in ledger["paid_expenses"]:
        lines.append(f"  - {p['date']} {p['description']}: ₹{p['amount_inr']}")
    lines.append("Their share of group expenses:")
    for o in ledger["owed_shares"]:
        lines.append(f"  - {o['date']} {o['description']}: ₹{o['share_inr']}")
    if ledger["settlements"]:
        lines.append("Settlements:")
        for s in ledger["settlements"]:
            lines.append(
                f"  - {s['date']} {s['direction']} ₹{s['amount_inr']} "
                f"({s['counterparty']})"
            )
    return "\n".join(lines)


def _template_explanation(ledger: dict) -> str:
    paid = sum(float(p["amount_inr"]) for p in ledger["paid_expenses"])
    owed = sum(float(o["share_inr"]) for o in ledger["owed_shares"])
    verb = ledger["interpretation"]
    magnitude = abs(float(ledger["net_inr"]))
    return (
        f"{ledger['member']} {verb} ₹{magnitude:.2f}. "
        f"They paid ₹{paid:.2f} on behalf of the group across "
        f"{len(ledger['paid_expenses'])} expense(s), while their own share of "
        f"all expenses came to ₹{owed:.2f}. The difference, after any "
        f"settlements, is their net balance."
    )


def explain_balance(group, member) -> dict:
    ledger = member_ledger(group, member)
    api_key = settings.ANTHROPIC_API_KEY
    if not api_key:
        return {"source": "rule", "text": _template_explanation(ledger)}

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=300,
            system=(
                "You explain a shared-expenses balance to a flatmate in 3-4 "
                "plain sentences. Use only the numbers given. Do not invent "
                "expenses. Mention the one or two biggest drivers of their "
                "balance. Currency is INR (₹)."
            ),
            messages=[{"role": "user", "content": _build_prompt(ledger)}],
        )
        text = "".join(
            block.text for block in msg.content if block.type == "text"
        )
        return {"source": "llm", "text": text.strip()}
    except Exception as exc:  # network/key/quota issues -> graceful fallback
        return {
            "source": "rule",
            "text": _template_explanation(ledger),
            "note": f"LLM unavailable ({type(exc).__name__}); used rule-based text.",
        }
