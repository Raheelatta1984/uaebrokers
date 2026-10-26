"""The reconciliation engine.

Pure functions only: give it normalised records, get findings back. No I/O, no
framework, no database. That keeps it testable and reusable outside insurance -
which is the whole point of keeping the matching core separate from the workflow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from .normalize import (
    FX_TO_AED,
    canonical_key,
    clean_text,
    detect_currency,
    endorsement_parent,
    key_variants,
    money_close,
    name_similarity,
    insurer_similarity,
    insurer_tokens,
    parse_date,
    parse_money,
    parse_percent,
    to_aed,
)
from .schema import FIELD_LABELS

CATEGORIES: dict[str, dict[str, Any]] = {
    "premium_mismatch": {
        "label": "Premium mismatch",
        "short": "Premium differs from the statement.",
        "action": "Confirm the correct premium with the insurer and raise a debit/credit note.",
    },
    "commission_mismatch": {
        "label": "Commission mismatch",
        "short": "Commission differs from the statement.",
        "action": "Claim the shortfall or correct the commission recorded against the policy.",
    },
    "sum_insured_mismatch": {
        "label": "Sum insured mismatch",
        "short": "Cover limit does not match - a coverage risk, not just a cash one.",
        "action": "Check the schedule/certificate and request an endorsement if cover is short.",
    },
    "date_mismatch": {
        "label": "Period mismatch",
        "short": "Inception or expiry dates differ.",
        "action": "Align the policy period; wrong periods distort renewal chasing.",
    },
    "name_mismatch": {
        "label": "Insured name mismatch",
        "short": "The insured name reads differently on the two documents.",
        "action": "Confirm it is the same insured; correct the internal policy record.",
    },
    "status_mismatch": {
        "label": "Cancelled but invoiced",
        "short": "Policy is cancelled in your book yet the statement still charges commission.",
        "action": "Reject the commission and request a reversal from the insurer.",
    },
    "currency_mismatch": {
        "label": "Currency mismatch",
        "short": "The two records are in different currencies.",
        "action": "Confirm the invoicing currency; values were compared at indicative FX.",
    },
    "missing_in_insurer": {
        "label": "Not on insurer statement",
        "short": "Policy is in your book but the insurer has not accounted for it.",
        "action": "Chase the insurer for the missing premium/commission - unbilled revenue.",
    },
    "missing_in_broker": {
        "label": "Not in broker book",
        "short": "The insurer has paid or invoiced on a policy your book does not hold.",
        "action": "Investigate before accepting: unknown policy, timing difference or leakage.",
    },
    "duplicate_in_statement": {
        "label": "Duplicate on statement",
        "short": "The same policy key appears more than once on the insurer statement.",
        "action": "Reject the duplicate line - otherwise commission is paid or claimed twice.",
    },
    "duplicate_in_broker": {
        "label": "Duplicate in broker book",
        "short": "The same policy key appears more than once in your own register.",
        "action": "Remove the duplicate internal record to avoid double counting.",
    },
    "low_confidence_match": {
        "label": "Probable match - confirm",
        "short": "Records look like the same policy but the key differs (typo or format).",
        "action": "Confirm the pair, then fix the key at source.",
    },
    "endorsement_not_in_book": {
        "label": "Endorsement not in book",
        "short": "Statement line is an endorsement/credit note for a policy you hold.",
        "action": "Post the endorsement to the parent policy in your book.",
    },
    "insurer_not_in_statements": {
        "label": "Insurer not covered",
        "short": "Policies for this insurer had no statement in this reconciliation.",
        "action": "Request the statement so these policies are not silently skipped.",
    },
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Config:
    """Tolerances are business policy, not code - so they are explicit and tunable."""

    premium_abs_tol: Decimal = Decimal("1.00")
    premium_pct_tol: Decimal = Decimal("0.10")
    commission_abs_tol: Decimal = Decimal("1.00")
    commission_pct_tol: Decimal = Decimal("0.10")
    sum_insured_pct_tol: Decimal = Decimal("0.50")
    commission_high_threshold: Decimal = Decimal("500")
    commission_medium_threshold: Decimal = Decimal("50")
    premium_high_amount: Decimal = Decimal("1000")
    premium_high_pct: Decimal = Decimal("5")
    date_tol_days: int = 7
    name_similarity_min: float = 0.90
    fuzzy_match_min: float = 0.62
    assume_seconds_per_line: int = 45

    def to_dict(self) -> dict:
        return {
            "premium_abs_tol": str(self.premium_abs_tol),
            "premium_pct_tol": str(self.premium_pct_tol),
            "commission_abs_tol": str(self.commission_abs_tol),
            "commission_pct_tol": str(self.commission_pct_tol),
            "date_tol_days": self.date_tol_days,
            "name_similarity_min": self.name_similarity_min,
            "fuzzy_match_min": self.fuzzy_match_min,
            "commission_high_threshold": str(self.commission_high_threshold),
        }


@dataclass
class Record:
    uid: str
    source_id: str
    side: str  # 'broker' | 'statement'
    row_no: int
    raw: dict[str, str]
    values: dict[str, Any]
    key: str
    notes: list[str] = field(default_factory=list)

    @property
    def insurer(self) -> str:
        return self.raw.get("insurer", "") or ""

    @property
    def insured(self) -> str:
        return self.raw.get("insured_name", "") or ""

    def display(self, field_key: str) -> str:
        return self.raw.get(field_key, "") or ""

    def to_brief(self) -> dict:
        return {
            "row_no": self.row_no,
            "source_id": self.source_id,
            "policy_no": self.raw.get("policy_no", ""),
            "insured_name": self.raw.get("insured_name", ""),
            "insurer": self.raw.get("insurer", ""),
            "class_of_business": self.raw.get("class_of_business", ""),
            "inception_date": self.raw.get("inception_date", ""),
            "expiry_date": self.raw.get("expiry_date", ""),
            "sum_insured": self.raw.get("sum_insured", ""),
            "premium": self.raw.get("premium", ""),
            "commission_pct": self.raw.get("commission_pct", ""),
            "commission_amount": self.raw.get("commission_amount", ""),
            "currency": self.raw.get("currency", ""),
            "status": self.raw.get("status", ""),
        }


@dataclass
class Finding:
    id: str
    source_id: str
    category: str
    severity: str
    policy_no: str
    insured: str
    insurer: str
    field: str
    broker_value: str
    insurer_value: str
    variance: Decimal | None
    currency: str
    detail: str
    action: str
    broker_row: dict | None = None
    insurer_row: dict | None = None
    confidence: int | None = None

    def to_dict(self) -> dict:
        meta = CATEGORIES.get(self.category, {})
        return {
            "id": self.id,
            "source_id": self.source_id,
            "category": self.category,
            "category_label": meta.get("label", self.category),
            "severity": self.severity,
            "policy_no": self.policy_no,
            "insured": self.insured,
            "insurer": self.insurer,
            "field": self.field,
            "broker_value": self.broker_value,
            "insurer_value": self.insurer_value,
            "variance": float(self.variance) if self.variance is not None else None,
            "variance_aed": float(to_aed(self.variance, self.currency) or 0)
            if self.variance is not None
            else None,
            "currency": self.currency,
            "detail": self.detail,
            "action": self.action,
            "broker_row": self.broker_row,
            "insurer_row": self.insurer_row,
            "confidence": self.confidence,
        }


# --------------------------------------------------------------------------- #
# Building records from a mapped source
# --------------------------------------------------------------------------- #
_STATUS_PATTERNS = (
    ("cancelled", r"canc|void|revok|terminat|surrend|declin|reject|not ?taken"),
    ("expired", r"expir|lapse|closed|elapsed"),
    ("active", r"active|in ?force|inforce|current|live|issued|renew|paid|open|ok"),
)


def normalize_status(value: str) -> str:
    text = clean_text(value).lower()
    if not text:
        return "unknown"
    for status, pattern in _STATUS_PATTERNS:
        if re.search(pattern, text):
            return status
    return "unknown"


def build_records(
    source_id: str, side: str, rows: list[list[str]], mapping: dict[str, dict]
) -> tuple[list[Record], list[dict], list[str]]:
    """Turn raw rows + a column mapping into normalised records.

    Returns (records, skipped_row_report, notes).
    """
    columns = {key: spec["column"] for key, spec in mapping.items()}
    records: list[Record] = []
    skipped: list[dict] = []
    notes: list[str] = []
    derived_commission = 0
    missing_currency = 0
    unreadable_premium = 0

    def cell(row: list[str], key: str) -> str:
        idx = columns.get(key)
        if idx is None or idx >= len(row):
            return ""
        return clean_text(row[idx])

    for offset, row in enumerate(rows):
        row_no = offset + 1
        raw = {key: cell(row, key) for key in columns}
        key = canonical_key(raw.get("policy_no"))
        if not key:
            skipped.append(
                {
                    "row_no": row_no,
                    "reason": "No policy number",
                    "values": [c for c in row if clean_text(c)][:6],
                }
            )
            continue

        has_figure = any(
            parse_money(raw.get(field)) is not None
            for field in ("premium", "commission_amount", "sum_insured")
        ) or any(parse_date(raw.get(field)) for field in ("inception_date", "expiry_date"))
        if not has_figure:
            skipped.append(
                {
                    "row_no": row_no,
                    "reason": "Not a policy line (no amounts or dates)",
                    "values": [c for c in row if clean_text(c)][:6],
                }
            )
            continue

        values: dict[str, Any] = {
            "inception_date": parse_date(raw.get("inception_date")),
            "expiry_date": parse_date(raw.get("expiry_date")),
            "sum_insured": parse_money(raw.get("sum_insured")),
            "premium": parse_money(raw.get("premium")),
            "commission_pct": parse_percent(raw.get("commission_pct")),
            "commission_amount": parse_money(raw.get("commission_amount")),
            "status": normalize_status(raw.get("status")),
        }

        if raw.get("premium") and values["premium"] is None:
            unreadable_premium += 1

        currency = detect_currency(raw.get("currency") or "")
        if currency is None:
            for candidate in ("premium", "commission_amount", "sum_insured"):
                currency = detect_currency(raw.get(candidate) or "")
                if currency:
                    break
        if currency is None:
            currency = "AED"
            missing_currency += 1
        values["currency"] = currency

        premium = values["premium"]
        pct = values["commission_pct"]
        amount = values["commission_amount"]
        if amount is None and premium is not None and pct is not None:
            amount = (premium * pct / Decimal(100)).quantize(Decimal("0.01"))
            values["commission_amount"] = amount
            raw["commission_amount"] = f"{amount:,.2f}"
            derived_commission += 1
            notes.append(f"Row {row_no}: commission amount derived from premium x {pct}%.")
        if pct is None and premium and amount is not None and premium != 0:
            values["commission_pct"] = (amount / premium * Decimal(100)).quantize(Decimal("0.01"))
            raw["commission_pct"] = f"{values['commission_pct']}%"

        records.append(
            Record(
                uid=f"{source_id}:{row_no}",
                source_id=source_id,
                side=side,
                row_no=row_no,
                raw=raw,
                values=values,
                key=key,
            )
        )

    if derived_commission:
        notes.append(f"{derived_commission} row(s) had no commission amount - derived from premium x rate.")
    if missing_currency:
        notes.append(f"{missing_currency} row(s) had no currency - assumed AED.")
    if unreadable_premium:
        notes.append(
            f"{unreadable_premium} row(s) have a premium that could not be read as a number "
            f"- check that Gross Premium is mapped to the right column."
        )
    return records, skipped, notes


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
def _infer_insurer(statement_records: list[Record], broker_records: list[Record]) -> str | None:
    """Guess the insurer from the broker records whose keys appear on the statement.

    Used when a statement carries no insurer column and no readable letterhead.
    If the matched keys do not point clearly at one insurer, we return None and
    the caller reconciles without insurer scoping.
    """
    from collections import Counter

    keys = {r.key for r in statement_records if r.key}
    if not keys:
        return None
    counts: Counter[str] = Counter()
    for record in broker_records:
        if record.key in keys and record.insurer:
            counts[record.insurer] += 1
    if not counts:
        return None
    name, hits = counts.most_common(1)[0]
    if hits >= max(2, int(0.6 * len(keys))):
        return name
    return None


def _insurer_match(broker: Record, statement_insurer: str | None) -> bool:
    """Does this broker policy belong to the insurer that issued the statement?

    Deliberately conservative: a policy we cannot attribute is left out of the
    statement scope entirely rather than reported as 'missing from statement',
    because a false exception is worse than a missed one for a finance team.
    """
    if not statement_insurer:
        return True
    if not broker.insurer:
        return True
    if insurer_similarity(broker.insurer, statement_insurer) >= 0.7:
        return True
    statement_tokens = insurer_tokens(statement_insurer)
    return bool(insurer_tokens(broker.insurer) & statement_tokens)


def _amounts_in_aed(rec: Record) -> tuple[Decimal | None, Decimal | None]:
    return (
        to_aed(rec.values.get("premium"), rec.values.get("currency")),
        to_aed(rec.values.get("commission_amount"), rec.values.get("currency")),
    )


def _fmt(value: Any, currency: str = "") -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{currency} {value:,.2f}".strip()
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value)


def _compare_pair(
    source_id: str, broker: Record, statement: Record, cfg: Config, match_note: str | None = None
) -> tuple[list[Finding], bool]:
    findings: list[Finding] = []

    def add(category: str, field_key: str, b_val, i_val, variance, severity: str, detail: str,
            action: str | None = None, confidence: int | None = None) -> None:
        findings.append(
            Finding(
                id=f"{source_id}:{category}:{broker.key}:{field_key}",
                source_id=source_id,
                category=category,
                severity=severity,
                policy_no=broker.display("policy_no") or statement.display("policy_no"),
                insured=broker.insured or statement.insured,
                insurer=broker.insurer or statement.insurer,
                field=FIELD_LABELS.get(field_key, field_key),
                broker_value=b_val,
                insurer_value=i_val,
                variance=variance,
                currency=broker.values.get("currency") or statement.values.get("currency") or "AED",
                detail=detail,
                action=action or CATEGORIES[category]["action"],
                broker_row=broker.to_brief(),
                insurer_row=statement.to_brief(),
                confidence=confidence,
            )
        )

    b_cur = broker.values.get("currency")
    i_cur = statement.values.get("currency")
    if b_cur and i_cur and b_cur != i_cur:
        add(
            "currency_mismatch", "currency",
            broker.display("currency") or b_cur, statement.display("currency") or i_cur,
            None, "medium",
            f"Broker record is in {b_cur}; statement line is in {i_cur}. "
            f"Compared at indicative rates (1 {b_cur} = {(FX_TO_AED.get(b_cur) or Decimal(1))} AED).",
        )

    b_prem, b_comm = _amounts_in_aed(broker)
    i_prem, i_comm = _amounts_in_aed(statement)

    if b_prem is not None and i_prem is not None:
        if not money_close(b_prem, i_prem, cfg.premium_abs_tol, cfg.premium_pct_tol):
            variance = (i_prem - b_prem).quantize(Decimal("0.01"))
            pct = (abs(variance) / abs(b_prem) * 100) if b_prem else Decimal(0)
            severity = (
                "high"
                if abs(variance) >= cfg.premium_high_amount or pct >= cfg.premium_high_pct
                else "medium" if abs(variance) >= Decimal("50") or pct >= Decimal("1")
                else "low"
            )
            direction = "understated" if variance < 0 else "overstated"
            add(
                "premium_mismatch", "premium",
                _fmt(broker.values["premium"], b_cur or ""),
                _fmt(statement.values["premium"], i_cur or ""),
                variance, severity,
                f"Statement premium is {pct:.2f}% {direction} versus the broker book "
                f"(difference {_fmt(abs(variance))} AED).",
            )

    premium_flagged = any(f.category == "premium_mismatch" for f in findings)

    if b_comm is not None and i_comm is not None:
        # If the premium differs and the insurer's commission is exactly its own
        # premium x the booked rate, the commission gap is a consequence, not a
        # second exception. Flagging both inflates the exception list and wastes
        # the finance team's time.
        explained_by_premium = False
        book_rate = broker.values.get("commission_pct")
        if premium_flagged and book_rate is not None and i_prem is not None:
            expected = (i_prem * book_rate / Decimal(100)).quantize(Decimal("0.01"))
            explained_by_premium = money_close(
                i_comm, expected, cfg.commission_abs_tol, cfg.commission_pct_tol
            )

        if not explained_by_premium and not money_close(
            b_comm, i_comm, cfg.commission_abs_tol, cfg.commission_pct_tol
        ):
            variance = (i_comm - b_comm).quantize(Decimal("0.01"))
            shortfall = variance < 0
            magnitude = abs(variance)
            severity = (
                "high" if magnitude >= cfg.commission_high_threshold
                else "medium" if magnitude >= cfg.commission_medium_threshold
                else "low"
            )
            detail = (
                f"Commission shortfall of {_fmt(magnitude)} AED - the statement pays less "
                f"than booked." if shortfall else
                f"Commission exceeds the book by {_fmt(magnitude)} AED - check for a rate error "
                f"or an unrecorded endorsement."
            )
            add(
                "commission_mismatch", "commission_amount",
                _fmt(broker.values["commission_amount"], b_cur or ""),
                _fmt(statement.values["commission_amount"], i_cur or ""),
                variance, severity, detail,
            )

    b_pct = broker.values.get("commission_pct")
    i_pct = statement.values.get("commission_pct")
    if b_pct is not None and i_pct is not None and abs(b_pct - i_pct) >= Decimal("0.25"):
        has_amount_finding = any(f.category == "commission_mismatch" for f in findings)
        if not has_amount_finding and not explained_by_premium:
            add(
                "commission_mismatch", "commission_pct",
                f"{b_pct}%", f"{i_pct}%", None, "medium",
                f"Commission rate differs: {b_pct}% in the book versus {i_pct}% on the statement.",
            )

    b_si = broker.values.get("sum_insured")
    i_si = statement.values.get("sum_insured")
    if b_si is not None and i_si is not None and b_si != 0:
        pct = abs(i_si - b_si) / abs(b_si) * 100
        if pct > cfg.sum_insured_pct_tol:
            add(
                "sum_insured_mismatch", "sum_insured",
                _fmt(b_si), _fmt(i_si), (i_si - b_si).quantize(Decimal("0.01")),
                "medium" if pct >= 5 else "low",
                f"Sum insured differs by {pct:.1f}% - the certificate on file may not match "
                f"the cover actually placed.",
            )

    b_inc, i_inc = broker.values.get("inception_date"), statement.values.get("inception_date")
    if b_inc and i_inc and abs((i_inc - b_inc).days) > cfg.date_tol_days:
        delta = (i_inc - b_inc).days
        add(
            "date_mismatch", "inception_date",
            _fmt(b_inc), _fmt(i_inc), None,
            "medium" if abs(delta) > 30 else "low",
            f"Inception dates are {abs(delta)} days apart.",
        )

    b_exp, i_exp = broker.values.get("expiry_date"), statement.values.get("expiry_date")
    if b_exp and i_exp and abs((i_exp - b_exp).days) > cfg.date_tol_days:
        add(
            "date_mismatch", "expiry_date",
            _fmt(b_exp), _fmt(i_exp), None,
            "medium" if abs((i_exp - b_exp).days) > 30 else "low",
            f"Expiry dates are {abs((i_exp - b_exp).days)} days apart.",
        )

    if broker.insured and statement.insured:
        similarity = name_similarity(broker.insured, statement.insured)
        if similarity < cfg.name_similarity_min:
            add(
                "name_mismatch", "insured_name", broker.insured, statement.insured,
                None, "medium" if similarity < 0.6 else "low",
                f"Insured names match at {similarity * 100:.0f}% - confirm these are the same party.",
            )

    b_status, i_status = broker.values.get("status"), statement.values.get("status")
    commission_value = abs(float(b_comm or 0))
    if b_status == "cancelled" and i_status not in {"cancelled", "expired"} and commission_value > 0:
        add(
            "status_mismatch", "status",
            broker.display("status") or "Cancelled",
            statement.display("status") or "Active",
            b_comm, "high",
            f"Policy is cancelled in the broker book but the statement still carries "
            f"{_fmt(b_comm)} AED of commission.",
        )

    if match_note:
        findings.append(
            Finding(
                id=f"{source_id}:low_confidence_match:{broker.key}:policy_no",
                source_id=source_id,
                category="low_confidence_match",
                severity="medium",
                policy_no=broker.display("policy_no") or statement.display("policy_no"),
                insured=broker.insured or statement.insured,
                insurer=broker.insurer or statement.insurer,
                field="Policy Number",
                broker_value=broker.display("policy_no"),
                insurer_value=statement.display("policy_no"),
                variance=None,
                currency=broker.values.get("currency") or "AED",
                detail=match_note,
                action=CATEGORIES["low_confidence_match"]["action"],
                broker_row=broker.to_brief(),
                insurer_row=statement.to_brief(),
                confidence=getattr(statement, "_confidence", None),
            )
        )

    has_problem = any(f.category not in {"low_confidence_match"} for f in findings)
    return findings, not has_problem


def _duplicate_findings(source_id: str, side: str, records: list[Record]) -> tuple[list[Finding], list[Record]]:
    groups: dict[str, list[Record]] = {}
    for rec in records:
        groups.setdefault(rec.key, []).append(rec)

    findings: list[Finding] = []
    unique: list[Record] = []
    for key, group in groups.items():
        unique.append(group[0])
        if len(group) < 2:
            continue
        category = "duplicate_in_statement" if side == "statement" else "duplicate_in_broker"
        extras = group[1:]
        commission = sum(
            (to_aed(r.values.get("commission_amount"), r.values.get("currency")) or Decimal(0))
            for r in extras
        )
        premium = sum(
            (to_aed(r.values.get("premium"), r.values.get("currency")) or Decimal(0))
            for r in extras
        )
        findings.append(
            Finding(
                id=f"{source_id}:{category}:{key}",
                source_id=source_id,
                category=category,
                severity="high" if side == "statement" else "medium",
                policy_no=group[0].display("policy_no"),
                insured=group[0].insured,
                insurer=group[0].insurer,
                field="Policy Number",
                broker_value=f"{len(group)} rows" if side == "broker" else "",
                insurer_value=f"{len(group)} rows" if side == "statement" else "",
                variance=commission if side == "statement" else None,
                currency=group[0].values.get("currency") or "AED",
                detail=(
                    f"Policy {group[0].display('policy_no')} appears {len(group)} times "
                    f"({'statement rows ' + ', '.join(str(r.row_no) for r in group) if side == 'statement' else 'register rows ' + ', '.join(str(r.row_no) for r in group)}). "
                    f"Duplicate lines carry {_fmt(premium)} premium and {_fmt(commission)} commission."
                ),
                action=CATEGORIES[category]["action"],
                broker_row=group[0].to_brief() if side == "broker" else None,
                insurer_row=group[0].to_brief() if side == "statement" else None,
            )
        )
    return findings, unique


def _fuzzy_match(
    brokers: list[Record], statements: list[Record], cfg: Config
) -> list[tuple[Record, Record, float]]:
    """Suggest likely pairs whose keys differ. Blocked on premium/name to stay fast."""
    if not brokers or not statements:
        return []

    def blocks(rec: Record) -> set[tuple]:
        out: set[tuple] = set()
        premium = rec.values.get("premium")
        if premium is not None:
            bucket = int(abs(premium) // 1000)
            out.update({("p", bucket - 1), ("p", bucket), ("p", bucket + 1)})
        first = clean_text(rec.insured).lower().split()[:2]
        if first:
            out.add(("n", " ".join(first)))
            out.add(("n", first[0]))
        out.add(("i", canonical_key(rec.insurer)[:12]))
        return out

    stmt_index: dict[tuple, list[Record]] = {}
    for rec in statements:
        for block in blocks(rec):
            stmt_index.setdefault(block, []).append(rec)

    scored: list[tuple[float, Record, Record]] = []
    seen: set[tuple[str, str]] = set()
    for broker in brokers:
        candidates: list[Record] = []
        for block in blocks(broker):
            candidates.extend(stmt_index.get(block, []))
        for statement in candidates:
            if (broker.uid, statement.uid) in seen:
                continue
            seen.add((broker.uid, statement.uid))
            name = name_similarity(broker.insured, statement.insured) if (broker.insured and statement.insured) else 0.0
            b_prem, _ = _amounts_in_aed(broker)
            i_prem, _ = _amounts_in_aed(statement)
            if b_prem is None or i_prem is None:
                prem_score = 0.0 if (b_prem is None) != (i_prem is None) else 0.5
            else:
                base = max(abs(b_prem), abs(i_prem), Decimal("1"))
                prem_score = max(0.0, 1.0 - float(abs(b_prem - i_prem) / base))
            b_date, i_date = broker.values.get("inception_date"), statement.values.get("inception_date")
            if b_date and i_date:
                date_score = max(0.0, 1.0 - abs((i_date - b_date).days) / 90)
            else:
                date_score = 0.5
            score = round(0.55 * name + 0.30 * prem_score + 0.15 * date_score, 4)
            if name >= 0.70 and score >= cfg.fuzzy_match_min:
                scored.append((score, broker, statement))

    scored.sort(key=lambda item: -item[0])
    used_broker: set[str] = set()
    used_statement: set[str] = set()
    pairs: list[tuple[Record, Record, float]] = []
    for score, broker, statement in scored:
        if broker.uid in used_broker or statement.uid in used_statement:
            continue
        used_broker.add(broker.uid)
        used_statement.add(statement.uid)
        pairs.append((broker, statement, score))
    return pairs


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def reconcile(
    broker_records: list[Record],
    statements: list[dict],
    cfg: Config | None = None,
) -> dict:
    """Reconcile every statement against the broker book.

    `statements` items: {"source_id": str, "label": str, "records": [Record],
                         "insurer_guess": str|None}
    """
    cfg = cfg or Config()
    findings: list[Finding] = []
    matched_pairs: list[dict] = []
    source_summaries: list[dict] = []
    covered_broker_uids: set[str] = set()

    broker_dupes, broker_unique = _duplicate_findings("broker", "broker", broker_records)
    findings.extend(broker_dupes)

    for statement in statements:
        source_id = statement["source_id"]
        label = statement.get("label") or source_id
        stmt_records = [r for r in statement["records"] if r.key]
        if not stmt_records:
            raise ValueError(
                f"'{label}' contains no policy lines. Check the column mapping, or "
                f"remove the file from this reconciliation."
            )

        stmt_insurers = [r.insurer for r in stmt_records if r.insurer]
        dominant_insurer = None
        if stmt_insurers:
            from collections import Counter

            dominant_insurer = Counter(stmt_insurers).most_common(1)[0][0]
        statement_insurer = (
            dominant_insurer
            or statement.get("insurer_guess")
            or _infer_insurer(stmt_records, broker_unique)
        )

        scoped = [r for r in broker_unique if _insurer_match(r, statement_insurer)]
        covered_broker_uids.update(r.uid for r in scoped)

        stmt_dupes, stmt_unique = _duplicate_findings(source_id, "statement", stmt_records)
        findings.extend(stmt_dupes)

        by_key: dict[str, Record] = {r.key: r for r in scoped}
        used_broker: set[str] = set()
        used_statement: set[str] = set()
        pairs: list[tuple[Record, Record, str | None, str]] = []

        # Stage A - exact key.
        for rec in stmt_unique:
            candidate = by_key.get(rec.key)
            if candidate and candidate.uid not in used_broker:
                pairs.append((candidate, rec, None, "exact"))
                used_broker.add(candidate.uid)
                used_statement.add(rec.uid)

        # Stage B - key variants (zero padding / punctuation), guarded by value agreement.
        variant_index: dict[str, list[Record]] = {}
        for rec in scoped:
            for variant in key_variants(rec.key):
                variant_index.setdefault(variant, []).append(rec)

        for rec in stmt_unique:
            if rec.uid in used_statement:
                continue
            for variant in key_variants(rec.key):
                candidates = [c for c in variant_index.get(variant, []) if c.uid not in used_broker]
                if not candidates:
                    continue
                chosen = None
                for candidate in candidates:
                    b_prem, _ = _amounts_in_aed(candidate)
                    i_prem, _ = _amounts_in_aed(rec)
                    same_name = name_similarity(candidate.insured, rec.insured) >= 0.7 if (candidate.insured and rec.insured) else True
                    close_premium = (
                        b_prem is not None and i_prem is not None
                        and money_close(b_prem, i_prem, cfg.premium_abs_tol, Decimal("2"))
                    )
                    if same_name or close_premium:
                        chosen = candidate
                        break
                if chosen is not None:
                    pairs.append((chosen, rec, None, "normalised"))
                    used_broker.add(chosen.uid)
                    used_statement.add(rec.uid)
                    break

        # Stage C - fuzzy suggestions that a human must confirm.
        remaining_broker = [r for r in scoped if r.uid not in used_broker]
        remaining_statement = [r for r in stmt_unique if r.uid not in used_statement]
        for broker_rec, stmt_rec, score in _fuzzy_match(remaining_broker, remaining_statement, cfg):
            note = (
                f"Probable match at {score * 100:.0f}% confidence: policy numbers differ "
                f"('{broker_rec.display('policy_no')}' vs '{stmt_rec.display('policy_no')}') "
                f"but insured, premium and dates line up."
            )
            setattr(stmt_rec, "_confidence", int(score * 100))
            pairs.append((broker_rec, stmt_rec, note, "probable"))
            used_broker.add(broker_rec.uid)
            used_statement.add(stmt_rec.uid)

        # Compare all matched pairs.
        for broker_rec, stmt_rec, note, kind in pairs:
            pair_findings, _clean = _compare_pair(source_id, broker_rec, stmt_rec, cfg, note)
            findings.extend(pair_findings)
            matched_pairs.append(
                {
                    "source_id": source_id,
                    "policy_no": broker_rec.display("policy_no"),
                    "statement_policy_no": stmt_rec.display("policy_no"),
                    "insured": broker_rec.insured or stmt_rec.insured,
                    "insurer": broker_rec.insurer or stmt_rec.insurer,
                    "premium": _fmt(broker_rec.values.get("premium"),
                                    broker_rec.values.get("currency") or ""),
                    "commission": _fmt(broker_rec.values.get("commission_amount"),
                                       broker_rec.values.get("currency") or ""),
                    "status": {"probable": "probable", "normalised": "key normalised"}.get(kind, "confirmed"),
                    "match_kind": kind,
                    "finding_count": len([f for f in pair_findings if f.category != "low_confidence_match"]),
                }
            )

        # Endorsements / credit notes for policies that do exist in the book.
        broker_keys = set(by_key)
        for rec in stmt_unique:
            if rec.uid in used_statement:
                continue
            parent = endorsement_parent(rec.display("policy_no"))
            if parent and (parent in broker_keys or any(v in broker_keys for v in key_variants(parent))):
                commission = to_aed(rec.values.get("commission_amount"), rec.values.get("currency"))
                findings.append(
                    Finding(
                        id=f"{source_id}:endorsement_not_in_book:{rec.key}",
                        source_id=source_id,
                        category="endorsement_not_in_book",
                        severity="low",
                        policy_no=rec.display("policy_no"),
                        insured=rec.insured,
                        insurer=rec.insurer,
                        field="Policy Number",
                        broker_value="",
                        insurer_value=_fmt(rec.values.get("commission_amount"),
                                           rec.values.get("currency") or ""),
                        variance=commission,
                        currency=rec.values.get("currency") or "AED",
                        detail=(
                            "Statement line looks like an endorsement/credit note against a policy "
                            "in your book, but it is not posted separately."
                        ),
                        action=CATEGORIES["endorsement_not_in_book"]["action"],
                        insurer_row=rec.to_brief(),
                    )
                )
                used_statement.add(rec.uid)

        # Leftovers.
        for rec in scoped:
            if rec.uid in used_broker:
                continue
            commission = to_aed(rec.values.get("commission_amount"), rec.values.get("currency"))
            premium = to_aed(rec.values.get("premium"), rec.values.get("currency"))
            findings.append(
                Finding(
                    id=f"{source_id}:missing_in_insurer:{rec.key}",
                    source_id=source_id,
                    category="missing_in_insurer",
                    severity="high" if (commission or 0) >= cfg.commission_high_threshold else "medium",
                    policy_no=rec.display("policy_no"),
                    insured=rec.insured,
                    insurer=rec.insurer,
                    field="Policy",
                    broker_value=_fmt(rec.values.get("commission_amount"),
                                      rec.values.get("currency") or ""),
                    insurer_value="Not on statement",
                    variance=-(commission or Decimal("0")),
                    currency=rec.values.get("currency") or "AED",
                    detail=(
                        f"Policy is in the broker book ({_fmt(premium)} AED premium) but does not "
                        f"appear on the {label} statement - commission of {_fmt(commission)} AED "
                        f"is unbilled."
                    ),
                    action=CATEGORIES["missing_in_insurer"]["action"],
                    broker_row=rec.to_brief(),
                )
            )

        for rec in stmt_unique:
            if rec.uid in used_statement:
                continue
            commission = to_aed(rec.values.get("commission_amount"), rec.values.get("currency"))
            findings.append(
                Finding(
                    id=f"{source_id}:missing_in_broker:{rec.key}",
                    source_id=source_id,
                    category="missing_in_broker",
                    severity="high",
                    policy_no=rec.display("policy_no"),
                    insured=rec.insured,
                    insurer=rec.insurer,
                    field="Policy",
                    broker_value="Not in book",
                    insurer_value=_fmt(rec.values.get("commission_amount"),
                                       rec.values.get("currency") or ""),
                    variance=commission,
                    currency=rec.values.get("currency") or "AED",
                    detail=(
                        f"The insurer statement carries policy {rec.display('policy_no')} with "
                        f"{_fmt(commission)} AED of commission, but the broker book has no such "
                        f"policy - possible leakage, timing difference or a wrong policy number."
                    ),
                    action=CATEGORIES["missing_in_broker"]["action"],
                    insurer_row=rec.to_brief(),
                )
            )

        # Statement files rarely carry an insurer column - label their findings
        # with the insurer we attributed the statement to.
        if statement_insurer:
            for finding in findings:
                if finding.source_id == source_id and not finding.insurer:
                    finding.insurer = statement_insurer

        source_findings = [f for f in findings if f.source_id == source_id]
        source_summaries.append(
            {
                "source_id": source_id,
                "label": label,
                "insurer": statement_insurer or "Unspecified",
                "statement_rows": len(stmt_records),
                "broker_rows_in_scope": len(scoped),
                "matched": len(pairs),
                "confirmed_matches": sum(1 for p in matched_pairs if p["source_id"] == source_id and p["status"] == "confirmed"),
                "probable_matches": sum(1 for p in matched_pairs if p["source_id"] == source_id and p["status"] == "probable"),
                "normalised_matches": sum(1 for p in matched_pairs if p["source_id"] == source_id and p["status"] == "key normalised"),
                "findings": len(source_findings),
                "high": sum(1 for f in source_findings if f.severity == "high"),
            }
        )

    # Broker policies whose insurer had no statement at all - never silently dropped.
    statement_insurers = [
        s["insurer"] for s in source_summaries if s["insurer"] and s["insurer"] != "Unspecified"
    ]
    uncovered: dict[str, list[Record]] = {}
    for rec in broker_unique:
        if rec.uid in covered_broker_uids:
            continue
        if not rec.insurer:
            continue
        uncovered.setdefault(rec.insurer.strip(), []).append(rec)

    for insurer, records in uncovered.items():
        if any(insurer_similarity(insurer, s) >= 0.55 for s in statement_insurers):
            continue
        total = sum(
            (to_aed(r.values.get("commission_amount"), r.values.get("currency")) or Decimal(0))
            for r in records
        )
        findings.append(
            Finding(
                id=f"broker:insurer_not_in_statements:{canonical_key(insurer)}",
                source_id="broker",
                category="insurer_not_in_statements",
                severity="low",
                policy_no=f"{len(records)} policies",
                insured="",
                insurer=insurer,
                field="Insurer",
                broker_value=f"{len(records)} policies",
                insurer_value="No statement uploaded",
                variance=None,
                currency="AED",
                detail=(
                    f"{len(records)} policies for {insurer} were not reconciled because no "
                    f"statement for that insurer was uploaded ({_fmt(total)} AED of commission)."
                ),
                action=CATEGORIES["insurer_not_in_statements"]["action"],
            )
        )

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 3), f.category, f.policy_no))
    kpis = _kpis(broker_records, statements, findings, matched_pairs, cfg)
    return {
        "kpis": kpis,
        "findings": [f.to_dict() for f in findings],
        "matched_pairs": matched_pairs,
        "sources": source_summaries,
        "config": cfg.to_dict(),
        "categories": {
            key: {"label": meta["label"], "short": meta["short"], "action": meta["action"]}
            for key, meta in CATEGORIES.items()
        },
    }


def _sum(values: Iterable[Decimal | None]) -> Decimal:
    return sum((v for v in values if v is not None), Decimal("0")).quantize(Decimal("0.01"))


def _kpis(
    broker_records: list[Record],
    statements: list[dict],
    findings: list[Finding],
    matched_pairs: list[dict],
    cfg: Config,
) -> dict:
    by_category: dict[str, int] = {}
    by_severity = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        by_category[finding.category] = by_category.get(finding.category, 0) + 1
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1

    statement_rows = sum(len([r for r in s["records"] if r.key]) for s in statements)
    broker_commission = _sum(to_aed(r.values.get("commission_amount"), r.values.get("currency")) for r in broker_records)
    broker_premium = _sum(to_aed(r.values.get("premium"), r.values.get("currency")) for r in broker_records)
    statement_commission = _sum(
        to_aed(r.values.get("commission_amount"), r.values.get("currency"))
        for s in statements for r in s["records"]
    )

    unbilled = _sum(
        abs(f.variance) for f in findings if f.category == "missing_in_insurer"
    )
    unrecognised = _sum(f.variance for f in findings if f.category == "missing_in_broker")
    commission_variance = _sum(f.variance for f in findings if f.category == "commission_mismatch")
    duplicates = _sum(
        abs(f.variance) for f in findings if f.category == "duplicate_in_statement"
    )
    cancelled = _sum(abs(f.variance) for f in findings if f.category == "status_mismatch")
    premium_variance = _sum(
        abs(f.variance) for f in findings
        if f.category == "premium_mismatch" and f.variance is not None and f.currency in FX_TO_AED
    )

    exposure = _sum(
        abs(f.variance) for f in findings
        if f.variance is not None and f.category not in {"insurer_not_in_statements", "premium_mismatch", "sum_insured_mismatch"}
    )

    matched = len([p for p in matched_pairs if p["status"] in {"confirmed", "key normalised"}])
    probable = len([p for p in matched_pairs if p["status"] == "probable"])
    manual_lines = broker_records.__len__() + statement_rows
    hours = round(manual_lines * cfg.assume_seconds_per_line / 3600, 1)

    return {
        "broker_records": len(broker_records),
        "statement_records": statement_rows,
        "matched": matched,
        "probable_match": probable,
        "exceptions": len(findings),
        "by_severity": by_severity,
        "by_category": by_category,
        "match_rate": round(matched / statement_rows * 100, 1) if statement_rows else 0.0,
        "clean_matches": sum(
            1 for p in matched_pairs
            if p["status"] in {"confirmed", "key normalised"} and p["finding_count"] == 0
        ),
        "normalised_matches": len([p for p in matched_pairs if p["status"] == "key normalised"]),
        "broker_premium_aed": float(broker_premium),
        "broker_commission_aed": float(broker_commission),
        "statement_commission_aed": float(statement_commission),
        "commission_variance_aed": float(commission_variance),
        "unbilled_commission_aed": float(unbilled),
        "unrecognised_commission_aed": float(unrecognised),
        "duplicate_exposure_aed": float(duplicates),
        "cancelled_commission_aed": float(cancelled),
        "premium_variance_aed": float(premium_variance),
        "exposure_aed": float(exposure),
        "manual_hours_estimate": hours,
        "tolerance_summary": (
            f"Premium +/- AED {cfg.premium_abs_tol} or {cfg.premium_pct_tol}%; "
            f"commission +/- AED {cfg.commission_abs_tol} or {cfg.commission_pct_tol}%; "
            f"dates +/- {cfg.date_tol_days} days"
        ),
    }
