"""Reconcile independent CSV exports with a review gate for every link."""

import csv
import io
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

TITLE = "CSV Reconciliation Studio"
DESCRIPTION = "Reconcile two ledger exports into a one-to-one settlement register with an explicit unmatched queue."
PROMPT = "Explain proposed pairings using the recorded amount, date distance, reference and description similarity. Flag competing matches; never infer a transaction was settled."


def identifier(value, field="id"):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,119}", value
    ):
        raise ValueError(
            f"Invalid {field}: use a short stable identifier without spaces."
        )
    return value


def spreadsheet_text(value):
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def csv_file(columns, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue()


def selected(evidence, approved):
    available = {item["id"]: item for item in evidence["candidates"]}
    seen = set()
    result = []
    for item in approved:
        key = item["id"]
        if key not in available or key in seen:
            raise ValueError("Approval contains an unknown or duplicate decision.")
        seen.add(key)
        result.append(available[key])
    return result


def read_ledger(raw, side):
    if not isinstance(raw, str) or len(raw) > 500_000:
        raise ValueError(f"{side}_csv must contain CSV text up to 500,000 characters.")
    reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff"), newline=""), strict=True)
    fields = ["id", "date", "currency", "amount", "reference", "description"]
    seen, records = set(), []
    try:
        if (
            not reader.fieldnames
            or set(reader.fieldnames) != set(fields)
            or len(reader.fieldnames) != len(fields)
        ):
            raise ValueError(
                "Both CSV files need columns id,date,currency,amount,reference,description."
            )
        for row in reader:
            if (
                None in row
                or any(v is None for v in row.values())
                or len(records) >= 1000
            ):
                raise ValueError("Malformed CSV row or more than 1,000 records.")
            rid = identifier(row["id"])
            if rid in seen:
                raise ValueError(f"Duplicate {side} ID: {rid}.")
            seen.add(rid)
            currency = row["currency"].strip().upper()
            value = Decimal(row["amount"].strip())
            if (
                not value.is_finite()
                or value.copy_abs() > 10**12
                or value != value.quantize(Decimal("0.01"))
            ):
                raise ValueError(
                    "Amounts must be finite with at most two significant decimal places."
                )
            if not value:
                value = Decimal(0)
            if not re.fullmatch("[A-Z]{3}", currency):
                raise ValueError("Use three-letter currency codes.")
            when = date.fromisoformat(row["date"])
            records.append(
                {
                    "id": f"{side}:{rid}",
                    "source_id": rid,
                    "side": side,
                    "date": when.isoformat(),
                    "currency": currency,
                    "amount": f"{value:.2f}",
                    "reference": row["reference"].strip(),
                    "description": row["description"].strip(),
                }
            )
    except (InvalidOperation, csv.Error) as e:
        raise ValueError(f"Invalid amount or CSV structure in {side}.") from e
    return records


def prepare(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Provide bank_csv and book_csv.")
    window = data.get("date_window_days", 3)
    if type(window) != int or not 0 <= window <= 31:
        raise ValueError("date_window_days must be between 0 and 31.")
    bank = read_ledger(data.get("bank_csv"), "bank")
    book = read_ledger(data.get("book_csv"), "book")
    buckets = defaultdict(list)
    for b in book:
        buckets[b["amount"], b["currency"]].append(b)
    candidates = []
    degree = defaultdict(int)
    for a in bank:
        for b in buckets[a["amount"], a["currency"]]:
            gap = abs(
                (date.fromisoformat(a["date"]) - date.fromisoformat(b["date"])).days
            )
            if gap > window:
                continue
            if len(candidates) >= 5000:
                raise ValueError(
                    "Too many candidate pairs. Narrow the date window or split the exports."
                )
            same = bool(
                a["reference"]
                and a["reference"].casefold() == b["reference"].casefold()
            )
            similarity = (
                SequenceMatcher(
                    None,
                    a["description"].casefold()[:300],
                    b["description"].casefold()[:300],
                ).ratio()
                if a["description"] and b["description"]
                else 0.0
            )
            # IDs are length-prefixed so punctuation in source IDs cannot collide.
            cid = f"match:{len(a['id'])}:{a['id']}:{b['id']}"
            pair = [a["id"], b["id"]]
            candidates.append(
                {
                    "id": cid,
                    "action": "Match transactions",
                    "evidence_ids": pair,
                    "bank_id": a["source_id"],
                    "book_id": b["source_id"],
                    "days_apart": gap,
                    "matching_reference": same,
                    "description_similarity": round(similarity, 3),
                }
            )
            for key in pair:
                degree[key] += 1
    candidates.sort(
        key=lambda c: (
            not c["matching_reference"],
            c["days_apart"],
            -c["description_similarity"],
            c["id"],
        )
    )
    for c in candidates:
        c["ambiguous"] = any(degree[key] > 1 for key in c["evidence_ids"])
    return {
        "summary": f"{len(candidates)} potential pairings across {len(bank)} bank and {len(book)} book entries.",
        "metrics": {
            "Bank entries": len(bank),
            "Book entries": len(book),
            "Candidate pairs": len(candidates),
            "Ambiguous pairs": sum(c["ambiguous"] for c in candidates),
        },
        "records": bank + book,
        "candidates": candidates,
    }


def export(data, evidence, approved):
    used, rows = set(), []
    index = {r["id"]: r for r in evidence["records"]}
    for c in selected(evidence, approved):
        a, b = c["evidence_ids"]
        if a in used or b in used:
            raise ValueError("A transaction cannot be reconciled more than once.")
        used.update([a, b])
        r = index[a]
        rows.append(
            [
                r["source_id"],
                index[b]["source_id"],
                r["date"],
                index[b]["date"],
                r["currency"],
                r["amount"],
                c["days_apart"],
            ]
        )
    unresolved = [
        [
            r["side"],
            r["source_id"],
            r["date"],
            r["currency"],
            r["amount"],
            spreadsheet_text(r["description"]),
        ]
        for r in evidence["records"]
        if r["id"] not in used
    ]
    return {
        "reconciled.csv": csv_file(
            [
                "bank_id",
                "book_id",
                "bank_date",
                "book_date",
                "currency",
                "amount",
                "days_apart",
            ],
            rows,
        ),
        "unmatched.csv": csv_file(
            ["source", "id", "date", "currency", "amount", "description"], unresolved
        ),
    }
