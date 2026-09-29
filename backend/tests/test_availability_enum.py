from app.core.enums import AvailabilityStatus, DataProvenance, QualityStatus


def test_availability_status_has_required_members():
    expected = {
        "AVAILABLE",
        "SOLD_OUT",
        "CANCELLED",
        "NOT_FOUND",
        "SCRAPE_FAILED",
        "INVALID_QUOTE",
        "UNKNOWN",
    }
    assert {member.value for member in AvailabilityStatus} == expected


def test_provenance_and_quality_are_distinct_enums():
    # Provenance and quality intentionally do not overlap: an item's origin
    # (REAL/SYNTHETIC/SIMULATED) is orthogonal to the pipeline's verdict on
    # it (RAW/VALIDATED/REJECTED/OUTLIER/DUPLICATE/PROVISIONAL).
    provenance_values = {member.value for member in DataProvenance}
    quality_values = {member.value for member in QualityStatus}
    assert provenance_values.isdisjoint(quality_values)
    assert "REAL" in provenance_values
    assert "SYNTHETIC" in provenance_values
    assert "VALIDATED" in quality_values
    assert "PROVISIONAL" in quality_values
