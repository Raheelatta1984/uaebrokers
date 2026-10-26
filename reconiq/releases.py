"""Version-controlled public release notes, with no runtime service dependencies.

Edit releases.json to publish an update. The newest entry defines the app version;
validation keeps duplicate/out-of-order versions and malformed notes out of a release.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

VERSION_PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
CHANGE_TYPES = frozenset({"added", "improved", "fixed"})


def _require_text(item: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise ValueError(f"Release notes require non-empty text for '{field}'.")


def validate_releases(releases: object) -> list[dict]:
    """Check the small changelog format and require newest-first semantic versions."""
    if not isinstance(releases, list) or not releases:
        raise ValueError("Release notes must be a non-empty list.")

    previous_version = None
    previous_date = None
    for release in releases:
        if not isinstance(release, dict):
            raise ValueError("Each release must be an object.")
        _require_text(release, ("version", "date", "title", "summary"))
        if not VERSION_PATTERN.fullmatch(release["version"]):
            raise ValueError("Release versions must use MAJOR.MINOR.PATCH without a 'v' prefix.")
        version = tuple(int(part) for part in release["version"].split("."))
        if previous_version is not None and version >= previous_version:
            raise ValueError("Release versions must be unique and ordered newest first.")

        published = date.fromisoformat(release["date"])
        if published.isoformat() != release["date"]:
            raise ValueError("Release dates must use YYYY-MM-DD.")
        if previous_date is not None and published > previous_date:
            raise ValueError("Release dates must be ordered newest first.")

        changes = release.get("changes")
        if not isinstance(changes, list) or not changes:
            raise ValueError("Each release must include at least one change.")
        for change in changes:
            if not isinstance(change, dict):
                raise ValueError("Each release change must be an object.")
            _require_text(change, ("type", "title", "description"))
            if change["type"] not in CHANGE_TYPES:
                raise ValueError("Change types must be added, improved or fixed.")
        previous_version, previous_date = version, published

    return releases


RELEASES = validate_releases(
    json.loads(Path(__file__).with_name("releases.json").read_text(encoding="utf-8"))
)
CURRENT_VERSION = RELEASES[0]["version"]
