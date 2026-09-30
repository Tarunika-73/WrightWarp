import pytest

from app.core.enums import DataProvenance, SourceStatus
from app.core.sources import ALL_SOURCES, get_source, list_sources


def test_registered_sources_include_expected_ids():
    ids = {s.source_id for s in list_sources()}
    for expected in {"6E", "AI", "IX", "QP", "SG", "MAKEMYTRIP", "YATRA", "CLEARTRIP", "IXIGO", "GOIBIBO", "EASEMYTRIP", "MOCK"}:
        assert expected in ids


def test_lookup_known_source():
    source = get_source("MOCK")
    assert source.source_id == "MOCK"
    assert source.status == SourceStatus.IMPLEMENTED
    assert source.enabled is True


def test_lookup_unknown_source_raises():
    with pytest.raises(ValueError):
        get_source("NOT_A_REAL_SOURCE")


def test_only_non_real_sources_are_implemented():
    implemented = [s for s in ALL_SOURCES if s.status == SourceStatus.IMPLEMENTED]
    assert sorted(s.source_id for s in implemented) == ["DEMO_SIM", "MOCK"]
    for source in implemented:
        assert source.data_provenance != DataProvenance.REAL


def test_every_real_source_is_pending_review_and_disabled():
    real_sources = [s for s in ALL_SOURCES if s.data_provenance == DataProvenance.REAL]
    assert real_sources, "expected at least one non-mock source to be registered"
    for source in real_sources:
        assert source.status == SourceStatus.PENDING_REVIEW
        assert source.enabled is False


def test_every_source_declares_compliance_metadata():
    for source in ALL_SOURCES:
        assert source.rate_limit_per_minute > 0
        assert isinstance(source.notes, str) and source.notes
