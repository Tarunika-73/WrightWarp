from datetime import date, timedelta


def _collection_payload(**overrides):
    payload = dict(
        source_id="MOCK",
        origin="DEL",
        destination="BOM",
        travel_date=str(date.today() + timedelta(days=15)),
        lead_days=15,
    )
    payload.update(overrides)
    return payload


def test_get_sources_lists_registry(client_with_db):
    response = client_with_db.get("/api/v1/sources")
    assert response.status_code == 200
    body = response.json()
    ids = {s["source_id"] for s in body}
    assert "MOCK" in ids
    assert "6E" in ids

    mock_entry = next(s for s in body if s["source_id"] == "MOCK")
    assert mock_entry["status"] == "IMPLEMENTED"
    assert mock_entry["enabled"] is True

    indigo_entry = next(s for s in body if s["source_id"] == "6E")
    assert indigo_entry["status"] == "PENDING_REVIEW"
    assert indigo_entry["enabled"] is False


def test_post_collection_with_mock_source_succeeds(client_with_db, seed_airports):
    response = client_with_db.post("/api/v1/collections", json=_collection_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "SUCCESS"
    assert body["success"] is True
    assert body["quotes_normalized"] == 1
    assert body["search_run_id"] is not None


def test_post_collection_with_pending_review_source_is_blocked(client_with_db, seed_airports):
    response = client_with_db.post("/api/v1/collections", json=_collection_payload(source_id="6E"))
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "BLOCKED"
    assert body["success"] is False


def test_post_collection_rejects_invalid_request_shape(client_with_db):
    response = client_with_db.post("/api/v1/collections", json=_collection_payload(origin="DEL", destination="DEL"))
    assert response.status_code == 422


def test_get_collection_status_after_creation(client_with_db, seed_airports):
    create_response = client_with_db.post("/api/v1/collections", json=_collection_payload())
    search_run_id = create_response.json()["search_run_id"]

    status_response = client_with_db.get(f"/api/v1/collections/{search_run_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["id"] == search_run_id
    assert body["status"] == "SUCCESS"
    assert body["source"] == "MOCK"


def test_get_collection_status_unknown_id_returns_404(client_with_db):
    response = client_with_db.get("/api/v1/collections/999999999")
    assert response.status_code == 404
