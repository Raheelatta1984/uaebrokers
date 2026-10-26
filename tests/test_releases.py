"""Keep the public changelog and application version in sync with every release."""

from copy import deepcopy

import pytest

from reconiq import __version__
from reconiq.releases import CURRENT_VERSION, RELEASES, validate_releases


def test_changelog_is_valid_and_defines_the_application_version():
    assert validate_releases(RELEASES) == RELEASES
    assert __version__ == CURRENT_VERSION == RELEASES[0]["version"]


def test_original_release_is_kept_in_the_history():
    assert any(release["version"] == "0.1.0" for release in RELEASES)


@pytest.mark.parametrize("version", ["0.02.0", "v0.2.0", "0.2", "0.2.0-beta", "0.2.0\n"])
def test_versions_use_a_simple_semantic_version(version):
    releases = deepcopy(RELEASES)
    releases[0]["version"] = version
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        validate_releases(releases)


@pytest.mark.parametrize("version", ["0.1.0", "0.0.9"])
def test_duplicate_or_out_of_order_versions_are_rejected(version):
    releases = deepcopy(RELEASES)
    releases[0]["version"] = version
    with pytest.raises(ValueError, match="unique and ordered newest first"):
        validate_releases(releases)


def test_versions_are_compared_numerically_not_alphabetically():
    releases = deepcopy(RELEASES[:2])
    releases[0]["version"] = "0.10.0"
    releases[1]["version"] = "0.9.0"
    assert validate_releases(releases) == releases


@pytest.mark.parametrize("published", ["26/10/2026", "2026-02-30", "20261026"])
def test_dates_must_be_real_iso_calendar_dates(published):
    releases = deepcopy(RELEASES)
    releases[0]["date"] = published
    with pytest.raises(ValueError):
        validate_releases(releases)


def test_dates_must_be_newest_first():
    releases = deepcopy(RELEASES)
    releases[1]["date"] = "2099-01-01"
    with pytest.raises(ValueError, match="dates must be ordered newest first"):
        validate_releases(releases)


@pytest.mark.parametrize("field", ["version", "date", "title", "summary"])
def test_release_metadata_cannot_be_missing(field):
    releases = deepcopy(RELEASES)
    del releases[0][field]
    with pytest.raises(ValueError, match=field):
        validate_releases(releases)


@pytest.mark.parametrize("notes", [None, [], {}, [None]])
def test_history_requires_release_objects(notes):
    with pytest.raises(ValueError):
        validate_releases(notes)


@pytest.mark.parametrize("changes", [None, [], [None], [{"type": "unknown", "title": "A", "description": "B"}]])
def test_release_changes_are_validated(changes):
    releases = deepcopy(RELEASES)
    releases[0]["changes"] = changes
    with pytest.raises(ValueError):
        validate_releases(releases)


@pytest.mark.parametrize("field", ["type", "title", "description"])
def test_change_fields_cannot_be_blank(field):
    releases = deepcopy(RELEASES)
    releases[0]["changes"][0][field] = "  "
    with pytest.raises(ValueError, match=field):
        validate_releases(releases)
