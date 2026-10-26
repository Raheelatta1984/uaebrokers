"""Value normalisation helpers.

Deliberately dependency-free and industry-agnostic: everything in here is about
turning messy real-world cell values into comparable primitives. The same helpers
are what would later be reused for logistics / property / banking reconciliation.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Values that should be treated as "no value" rather than as text.
EMPTY_MARKERS = {
    "", "-", "--", "---", "n/a", "na", "n.a.", "none", "null", "nan", "nil", ".",
    "#n/a", "tbc", "tba",
}

CURRENCY_TOKENS = {
    "AED": "AED", "DHS": "AED", "DH": "AED", "د.إ": "AED", "DIRHAM": "AED", "DIRHAMS": "AED",
    "USD": "USD", "US$": "USD", "$": "USD", "DOLLAR": "USD", "DOLLARS": "USD",
    "EUR": "EUR", "€": "EUR",
    "GBP": "GBP", "£": "GBP",
    "SAR": "SAR", "SR": "SAR",
    "OMR": "OMR",
    "QAR": "QAR",
    "KWD": "KWD",
    "BHD": "BHD",
}

# Indicative AED cross-rates. Only used to give a single comparable total in the
# demo; real deployment would pull a rate table and stamp it with an effective date.
FX_TO_AED = {
    "AED": Decimal("1"),
    "USD": Decimal("3.6725"),
    "EUR": Decimal("3.99"),
    "GBP": Decimal("4.62"),
    "SAR": Decimal("0.98"),
    "OMR": Decimal("9.54"),
    "QAR": Decimal("1.01"),
    "KWD": Decimal("11.95"),
    "BHD": Decimal("9.74"),
}

_LEGAL_SUFFIXES = {
    "llc", "l l c", "ltd", "limited", "co", "company", "pjsc", "psc", "psjc", "fzc",
    "fze", "fzco", "est", "establishment", "holding", "holdings", "group", "inc",
    "incorporated", "corp", "corporation", "plc", "llp", "br", "branch", "the", "and",
}


def is_blank(value) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in EMPTY_MARKERS


def to_text(value) -> str:
    """Render a spreadsheet / PDF / CSV cell as display text."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        return f"{value.normalize():f}"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value).strip()


def clean_text(value) -> str:
    text = to_text(value)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_currency(text: str) -> str | None:
    if not text:
        return None
    upper = unicodedata.normalize("NFKC", str(text)).upper()
    for token, code in CURRENCY_TOKENS.items():
        if token in upper:
            return code
    return None


def parse_money(value) -> Decimal | None:
    """Parse 'AED 1,250.00', '(250.00)', '1 250.00 Dr', 1250.0 ... into Decimal."""
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except InvalidOperation:
            return None
    if is_blank(value):
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if re.search(r"(^|\s)(dr|debit)(\s|$)", text, re.I):
        negative = True
    # Strip currency words/symbols and thousands separators.
    text = re.sub(r"[A-Za-z\u0600-\u06FF]{1,12}", " ", text)
    text = text.replace(",", "").replace("'", "").replace("\u00a0", "")
    text = text.replace("−", "-").replace("–", "-")
    text = re.sub(r"\s+", "", text)
    match = re.search(r"-?\d*\.?\d+", text)
    if not match:
        return None
    try:
        number = Decimal(match.group(0))
    except InvalidOperation:
        return None
    if negative:
        number = -abs(number)
    return number.quantize(Decimal("0.01"))


def parse_percent(value) -> Decimal | None:
    """Parse '12.5%', '0.125', 12.5 -> percentage as 12.5.

    Insurers send commission either as a rate (12.5) or as a fraction (0.125).
    A bare number <= 1 is read as a fraction, which is the only sensible reading
    for commission rates in this market. Kept to 4dp so 0.125 does not become 12.
    """
    if is_blank(value):
        return None
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
        if Decimal(0) < number <= Decimal(1):
            number = number * 100
        return number.quantize(Decimal("0.01"))
    raw = to_text(value)
    had_symbol = "%" in raw
    text = unicodedata.normalize("NFKC", raw).replace("%", " ")
    text = re.sub(r"[A-Za-z\u0600-\u06FF]{1,12}", " ", text)
    text = text.replace(" ", "").replace("\u00a0", "")
    match = re.search(r"-?\d*\.?\d+", text)
    if not match:
        return None
    try:
        number = Decimal(match.group(0))
    except InvalidOperation:
        return None
    if not had_symbol and Decimal(0) < number <= Decimal(1):
        number = number * 100
    return number.quantize(Decimal("0.01"))


_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d-%b-%Y", "%d %B %Y", "%d-%b-%y",
    "%b %d %Y", "%b %d, %Y", "%b-%y", "%d/%b/%Y",
)


def parse_date(value) -> date | None:
    """Parse common UAE / international date renderings.

    Day-first is preferred (UAE convention). Ambiguous values such as 05/09/2026
    are read as DD/MM/YYYY and the UI states that assumption explicitly.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if is_blank(value):
        return None
    text = re.sub(r"\s+", " ", to_text(value)).strip()
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.I)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # Excel serial numbers arriving as text.
    if re.fullmatch(r"\d{5}(\.\d+)?", text):
        try:
            from datetime import timedelta
            return (datetime(1899, 12, 30) + timedelta(days=float(text))).date()
        except (ValueError, OverflowError):
            return None
    return None


def canonical_key(value) -> str:
    """Policy/certificate keys compare on alphanumerics only, upper-cased."""
    if is_blank(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).upper()
    return re.sub(r"[^A-Z0-9]", "", text)


def key_variants(key: str) -> set[str]:
    """Equivalent spellings of the same policy key.

    Systems pad policy numerals inconsistently: GIG/2026/000451 vs GIG-2026-451
    vs GIG/2026/451 are the same policy. Each variant below removes one *class*
    of padding, and callers guard the match on name/premium agreement so an
    aggressive variant cannot invent a pair on its own.
    """
    if not key:
        return set()
    variants = {
        key,
        re.sub(r"(?<=\d)0{2,}(?=\d)", "", key),   # internal zero padding
        re.sub(r"(?<=\D)0+(?=\d)", "", key),       # leading zeros of a numeric group
        re.sub(r"^0+(?=\d)", "", key),              # leading zeros of the key
        re.sub(r"0{3,}", "", key),                   # long zero runs anywhere
    }
    return {v for v in variants if len(v) >= 4}


_ENDORSEMENT_SUFFIX = re.compile(
    r"(?:[/\-_\s](?:E|END|ENDT|ENDR|CN|CR|D|R)\s?\d{1,3}|(?:E|CN|CR)\d{1,3})$", re.I
)


def endorsement_parent(policy_no: str) -> str | None:
    """Canonical parent key if a policy number looks like an endorsement/credit note.

    Works on the *display* policy number (GIG/2026/000312/E1) rather than the
    canonical key, because separators carry the meaning.
    """
    text = clean_text(policy_no).upper()
    if not text:
        return None
    match = _ENDORSEMENT_SUFFIX.search(text)
    if not match:
        return None
    parent_text = text[: match.start()]
    parent = canonical_key(parent_text)
    return parent if len(parent) >= 5 else None


def normalize_name(value) -> str:
    """Lower-case, strip punctuation and legal suffixes for name comparison.

    Dots are removed rather than turned into spaces so that "L.L.C." and
    "P.J.S.C." collapse to the same tokens as "LLC" and "PJSC".
    """
    text = clean_text(value).lower().replace(".", "")
    text = re.sub(r"[^a-z0-9\u0600-\u06FF ]+", " ", text)
    tokens = [t for t in text.split() if t and t not in _LEGAL_SUFFIXES]
    return " ".join(tokens)


def name_similarity(a, b) -> float:
    """0..1 similarity that tolerates legal-suffix and token-order differences."""
    import difflib

    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    jaccard = len(ta & tb) / len(ta | tb)
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    return round(max(jaccard, 0.55 * ratio + 0.45 * jaccard), 4)


_GENERIC_INSURER_TOKENS = {
    "insurance", "insurances", "insurer", "assurance", "takaful", "co", "company",
    "companies", "pjsc", "psc", "llc", "ltd", "plc", "group", "holding", "holdings",
    "broker", "brokers", "brokerage", "services", "uae", "pvt", "private", "general",
    "ins", "insur", "assur", "comp", "intl", "international",
}


def insurer_core(value) -> str:
    """Insurer name with generic industry words removed.

    Without this, 'Sukoon Insurance' and 'Orient Insurance PJSC' look 56% similar
    and every statement ends up scoped against every policy.
    """
    tokens = [t for t in normalize_name(value).split() if t not in _GENERIC_INSURER_TOKENS]
    return " ".join(tokens)


def insurer_similarity(a, b) -> float:
    core_a, core_b = insurer_core(a), insurer_core(b)
    if not core_a or not core_b:
        return 0.0
    if core_a == core_b:
        return 1.0
    return name_similarity(core_a, core_b)


def insurer_tokens(value) -> set[str]:
    return {
        t for t in normalize_name(value).split()
        if len(t) >= 4 and t not in _GENERIC_INSURER_TOKENS
    }


def money_close(a: Decimal | None, b: Decimal | None, abs_tol: Decimal, pct_tol: Decimal) -> bool:
    if a is None or b is None:
        return a is None and b is None
    diff = abs(a - b)
    if diff <= abs_tol:
        return True
    base = max(abs(a), abs(b))
    if base == 0:
        return diff == 0
    return (diff / base) * 100 <= pct_tol


def to_aed(amount: Decimal | None, currency: str | None) -> Decimal | None:
    if amount is None:
        return None
    rate = FX_TO_AED.get((currency or "AED").upper())
    if rate is None:
        return None
    return (amount * rate).quantize(Decimal("0.01"))
