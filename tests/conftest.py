import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reconiq import demo  # noqa: E402
from reconiq.engine import build_records, reconcile  # noqa: E402
from reconiq.ingest import prepare  # noqa: E402


@pytest.fixture(scope="session")
def demo_files() -> dict[str, bytes]:
    return demo.build_all()


@pytest.fixture(scope="session")
def demo_prepared(demo_files):
    prepared = {}
    for name, payload in demo_files.items():
        side = "broker" if name.startswith("broker") else "statement"
        prepared[name] = prepare(name, payload, side)
    return prepared


@pytest.fixture(scope="session")
def demo_result(demo_files, demo_prepared):
    broker_source = "broker_register_sep2026.csv"
    broker, _, _ = build_records(
        broker_source, "broker",
        demo_prepared[broker_source]["rows"], demo_prepared[broker_source]["mapping"],
    )
    statements = []
    for name in demo_prepared:
        if name == broker_source:
            continue
        records, _, _ = build_records(
            name, "statement", demo_prepared[name]["rows"], demo_prepared[name]["mapping"]
        )
        statements.append(
            {
                "source_id": name,
                "label": name,
                "records": records,
                "insurer_guess": demo_prepared[name]["context"].get("insurer_guess"),
            }
        )
    return reconcile(broker, statements)
