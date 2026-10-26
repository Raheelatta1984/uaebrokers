"""Canonical reconciliation schema and column auto-detection.

Every source file - broker register, insurer CSV, Excel export or PDF statement -
is reduced to the same small set of canonical fields. Column detection is what
makes the demo feel instant: drop in a file from any insurer and the mapping is
guessed, shown, and editable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import canonical_key, clean_text


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    type: str  # text | money | date | percent
    required: bool = False
    hint: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "policy_no", "Policy Number", "text", required=True,
        hint="The join key between your book and the insurer statement.",
        aliases=(
            "policynumber", "policyno", "policynum", "policyref", "policyreference",
            "policyid", "certificatenumber", "certificateno", "certno", "referencenumber",
            "riskno", "masterpolicyno", "policyno.", "policynumberref",
        ),
    ),
    FieldSpec(
        "insured_name", "Insured / Client", "text",
        hint="Used for near-match suggestions and name-mismatch checks.",
        aliases=(
            "insuredname", "insured", "clientname", "client", "nameofinsured",
            "customername", "policyholder", "assured", "accountname", "companyname",
        ),
    ),
    FieldSpec(
        "insurer", "Insurer", "text",
        hint="Scopes each statement to the policies that belong to that insurer.",
        aliases=(
            "insurer", "insurancecompany", "insurername", "carrier", "underwriter",
            "insuranceco", "riskcarrier", "insurancecompanyname",
        ),
    ),
    FieldSpec(
        "class_of_business", "Class of Business", "text",
        aliases=(
            "classofbusiness", "class", "lineofbusiness", "lob", "product",
            "producttype", "covertype", "businessclass", "typeofcover", "coverage",
        ),
    ),
    FieldSpec(
        "inception_date", "Inception / From", "date",
        aliases=(
            "inceptiondate", "inception", "policystart", "startdate", "from",
            "fromdate", "effectivedate", "commencementdate", "datefrom", "periodfrom",
            "coverfrom",
        ),
    ),
    FieldSpec(
        "expiry_date", "Expiry / To", "date",
        aliases=(
            "expirydate", "expiry", "policyend", "enddate", "to", "todate",
            "expirationdate", "dateto", "periodto", "coverto", "renewaldate",
        ),
    ),
    FieldSpec(
        "sum_insured", "Sum Insured", "money",
        aliases=(
            "suminsured", "si", "sumassured", "insuredvalue", "sumins", "siamount",
            "suminsuredaed", "totalinsuredvalue", "limitofindemnity", "tsi",
        ),
    ),
    FieldSpec(
        "premium", "Gross Premium", "money",
        hint="Premium as invoiced / declared. Compared with a configurable tolerance.",
        aliases=(
            "grosspremium", "premium", "grosswrittenpremium", "gwp", "premiumamount",
            "totalpremium", "grosspremiumaed", "prem", "premiumaed", "premiumgross",
            "netpremium", "writtenpremium", "invoicedpremium",
        ),
    ),
    FieldSpec(
        "commission_pct", "Commission %", "percent",
        hint="A rate column only - detected from '%', 'pct', 'percent' or 'rate'.",
        aliases=(
            "commissionpct", "commissionpercent", "commissionrate", "commpct",
            "commrate", "commperc", "rateofcommission", "brokeragerate",
            "brokeragepct", "commissionpercentage", "percent", "pct", "rate",
        ),
    ),
    FieldSpec(
        "commission_amount", "Commission Amount", "money",
        hint="The number the business actually cares about: cash owed to the broker.",
        aliases=(
            "commissionamount", "commission", "commissionaed", "brokerage",
            "brokerageamount", "commamount", "commissionpayable", "netpayable",
            "amountpayable", "commissiondue", "commision", "commissionvalue",
            "totalcommission", "commissionearned", "payablecommission",
        ),
    ),
    FieldSpec(
        "currency", "Currency", "text",
        aliases=("currency", "ccy", "curr", "currencycode", "premiumcurrency"),
    ),
    FieldSpec(
        "status", "Policy Status", "text",
        hint="Active / Cancelled detection so cancelled covers are not paid on.",
        aliases=("status", "policystatus", "state", "coverstatus", "accountstatus", "stage"),
    ),
    FieldSpec(
        "broker_ref", "Broker / Insurer Ref", "text",
        aliases=(
            "brokerref", "referenceno", "refno", "ref", "insurerref",
            "statementref", "transref", "debitnote", "debitnoteno", "dnote",
        ),
    ),
)

FIELDS_BY_KEY = {f.key: f for f in FIELDS}
FIELD_LABELS = {f.key: f.label for f in FIELDS}

# Headers that must never be mistaken for a commission rate.
_RATE_REJECTS = ("vat", "tax", "discount", "loading", "fee", "stamp", "fx", "exchange")


def _norm_header(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", clean_text(text).lower())


def _score(header_norm: str, alias: str) -> int:
    if not header_norm:
        return 0
    if header_norm == alias:
        return 100
    if header_norm.startswith(alias) or alias.startswith(header_norm):
        return 82 if len(header_norm) <= len(alias) + 6 else 70
    if alias in header_norm:
        return 64
    return 0


def _looks_like_rate(header: str) -> bool:
    raw = clean_text(header).lower()
    norm = _norm_header(header)
    if any(token in norm for token in _RATE_REJECTS):
        return False
    if "%" in raw:
        return True
    return any(token in norm for token in ("pct", "percent", "rate"))


def detect_columns(header: list[str], sample_rows: list[list[str]] | None = None) -> dict[str, dict]:
    """Map canonical fields to column indexes.

    Returns {field_key: {"column": int|None, "confidence": int, "header": str}}.

    Two passes: rate columns are resolved first (so 'Commission %' cannot be
    stolen by the commission *amount* field), then everything else greedily.
    """
    headers = [_norm_header(h) for h in header]
    mapping: dict[str, dict] = {}
    used_cols: set[int] = set()

    # Pass 1 - commission rate columns.
    rate_candidates: list[tuple[int, int]] = []
    for col, htext in enumerate(headers):
        if not htext or not _looks_like_rate(header[col]):
            continue
        best = 0
        for alias in FIELDS_BY_KEY["commission_pct"].aliases:
            best = max(best, _score(htext, alias))
        # A '%' column that mentions commission/brokerage is a rate even if the
        # wording is unusual ("Brokerage %", "Comm. Rate", "Rate %").
        if best == 0 and any(token in htext for token in ("comm", "broker", "rate", "pct")):
            best = 90
        if best:
            rate_candidates.append((best, col))
    rate_candidates.sort(key=lambda c: (-c[0], c[1]))
    if rate_candidates:
        score, col = rate_candidates[0]
        mapping["commission_pct"] = {"column": col, "confidence": score, "header": header[col]}
        used_cols.add(col)

    # Pass 2 - everything else.
    candidates: list[tuple[int, str, int]] = []
    for col, htext in enumerate(headers):
        if not htext or col in used_cols:
            continue
        for spec in FIELDS:
            if spec.key == "commission_pct":
                continue
            best = 0
            for alias in spec.aliases:
                best = max(best, _score(htext, alias))
            if best:
                candidates.append((best, spec.key, col))

    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    for score, fkey, col in candidates:
        if fkey in mapping or col in used_cols:
            continue
        mapping[fkey] = {"column": col, "confidence": score, "header": header[col]}
        used_cols.add(col)

    for spec in FIELDS:
        mapping.setdefault(spec.key, {"column": None, "confidence": 0, "header": None})

    _resolve_ambiguities(mapping, headers, sample_rows or [])
    return mapping


def _resolve_ambiguities(mapping: dict[str, dict], headers: list[str], rows: list[list[str]]) -> None:
    """One trap worth fixing automatically: a rate column mapped as commission amount.

    Money semantics are deliberately *not* guessed. If a statement has vague
    headers such as "Amount" or "Value", the field stays unmapped and the user
    chooses in the UI - silently picking a money column is how a reconciliation
    tool loses a finance team's trust.
    """
    pct, amt = mapping["commission_pct"], mapping["commission_amount"]
    if pct["column"] is None and amt["column"] is not None:
        if _looks_like_rate(amt["header"] or ""):
            mapping["commission_pct"] = {
                "column": amt["column"],
                "confidence": 60,
                "header": amt["header"],
            }
            mapping["commission_amount"] = {"column": None, "confidence": 0, "header": None}


def header_row_index(rows: list[list[str]], scan: int = 20) -> int | None:
    """Find the header row inside a statement that starts with title/metadata lines."""
    best_index, best_score = None, 0
    for idx, row in enumerate(rows[:scan]):
        cells = [_norm_header(c) for c in row if clean_text(c)]
        if len(cells) < 2:
            continue
        hits = 0
        for cell in cells:
            for spec in FIELDS:
                if any(_score(cell, alias) >= 70 for alias in spec.aliases):
                    hits += 1
                    break
        score = hits * 10 + min(len(cells), 10)
        if hits >= 2 and score > best_score:
            best_index, best_score = idx, score
    return best_index


def normalize_mapping(mapping: dict[str, dict]) -> dict[str, dict]:
    """Ensure every canonical field is present and columns are ints or None."""
    out: dict[str, dict] = {}
    for spec in FIELDS:
        item = mapping.get(spec.key) or {}
        column = item.get("column")
        out[spec.key] = {
            "column": int(column) if column is not None and str(column) != "" else None,
            "confidence": item.get("confidence", 0),
            "header": item.get("header"),
        }
    return out


def mapping_ready(mapping: dict[str, dict]) -> tuple[bool, list[str]]:
    missing = [
        FIELD_LABELS[key]
        for key in ("policy_no", "premium")
        if (mapping.get(key) or {}).get("column") is None
    ]
    return (not missing, missing)


def describe_mapping(mapping: dict[str, dict]) -> list[dict]:
    out = []
    for spec in FIELDS:
        item = mapping.get(spec.key) or {}
        out.append(
            {
                "key": spec.key,
                "label": spec.label,
                "type": spec.type,
                "required": spec.required,
                "hint": spec.hint,
                "column": item.get("column"),
                "header": item.get("header"),
                "confidence": item.get("confidence", 0),
            }
        )
    return out


def key_preview(value) -> str:
    return canonical_key(value)
