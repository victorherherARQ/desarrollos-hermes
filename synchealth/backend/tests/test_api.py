"""Integration tests for the FastAPI app (sync `TestClient`)."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_ok(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] is True
    assert body["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# /ingest/weight (JSON, idempotent)
# ---------------------------------------------------------------------------

def test_ingest_weight_inserts_new_rows(client: TestClient):
    payload = {
        "rows": [
            {"date": "2025-05-01", "weight_kg": 89.4, "bmi": 28.5},
            {"date": "2025-05-02", "weight_kg": 89.2, "bmi": 28.4},
        ],
        "source": "manual",
    }
    resp = client.post("/ingest/weight", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inserted"] == 2
    assert body["updated"] == 0
    assert body["skipped"] == 0
    assert body["total"] == 2


def test_ingest_weight_is_idempotent_on_same_date(client: TestClient):
    payload = {
        "rows": [
            {"date": "2025-05-01", "weight_kg": 89.4, "bmi": 28.5},
        ],
        "source": "manual",
    }
    r1 = client.post("/ingest/weight", json=payload)
    assert r1.status_code == 200
    assert r1.json()["inserted"] == 1

    # Re-POST same date with a new value -> should UPDATE not duplicate.
    payload2 = {
        "rows": [
            {"date": "2025-05-01", "weight_kg": 89.9, "bmi": 28.7},
        ],
        "source": "manual",
    }
    r2 = client.post("/ingest/weight", json=payload2)
    assert r2.status_code == 200
    assert r2.json()["inserted"] == 0
    assert r2.json()["updated"] == 1


def test_ingest_weight_skips_rows_without_weight(client: TestClient):
    payload = {
        "rows": [
            {"date": "2025-05-01", "weight_kg": None, "bmi": 28.0},
        ],
    }
    resp = client.post("/ingest/weight", json=payload)
    assert resp.status_code == 200
    assert resp.json()["skipped"] == 1


def test_ingest_weight_rejects_empty_rows(client: TestClient):
    resp = client.post("/ingest/weight", json={"rows": [], "source": "manual"})
    assert resp.status_code == 422  # Pydantic min_length=1


def test_ingest_weight_rejects_out_of_range_weight(client: TestClient):
    payload = {
        "rows": [
            {"date": "2025-05-01", "weight_kg": 500.0, "bmi": 28.0},
        ],
    }
    resp = client.post("/ingest/weight", json=payload)
    assert resp.status_code == 422  # Pydantic Field(le=200.0)


def test_ingest_weight_rejects_too_many_rows(client: TestClient):
    payload = {
        "rows": [
            {"date": f"2025-05-{(i % 28) + 1:02d}", "weight_kg": 80.0}
            for i in range(1001)
        ],
    }
    resp = client.post("/ingest/weight", json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /ingest/csv (multipart upload)
# ---------------------------------------------------------------------------

def test_ingest_csv_happy_path(client: TestClient, sample_csv_bytes: bytes):
    resp = client.post(
        "/ingest/csv",
        files={"file": ("zepp_sample.csv", sample_csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inserted"] >= 1
    assert body["total"] >= 1


def test_ingest_csv_idempotent_on_reupload(client: TestClient, sample_csv_bytes: bytes):
    r1 = client.post(
        "/ingest/csv",
        files={"file": ("zepp_sample.csv", sample_csv_bytes, "text/csv")},
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["inserted"] > 0

    r2 = client.post(
        "/ingest/csv",
        files={"file": ("zepp_sample.csv", sample_csv_bytes, "text/csv")},
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["inserted"] == 0
    assert body2["updated"] > 0


def test_ingest_csv_rejects_empty_file(client: TestClient):
    resp = client.post(
        "/ingest/csv",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert resp.status_code == 400


def test_ingest_csv_rejects_garbage(client: TestClient):
    resp = client.post(
        "/ingest/csv",
        files={"file": ("garbage.csv", b"this is not a csv at all", "text/csv")},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /ingest/preview-csv
# ---------------------------------------------------------------------------

def test_preview_csv_returns_structured_rows(client: TestClient, sample_csv_bytes: bytes):
    resp = client.post(
        "/ingest/preview-csv",
        files={"file": ("zepp_sample.csv", sample_csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_rows"] == 7
    assert body["valid_rows"] == 7
    assert body["invalid_rows"] == 0
    assert body["rows"][0]["date"] == "2025-05-01"


# ---------------------------------------------------------------------------
# /metrics/*
# ---------------------------------------------------------------------------

def test_metrics_weight_empty(client: TestClient):
    resp = client.get("/metrics/weight?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "weight_kg"
    assert body["period_days"] == 30
    assert body["points"] == []


def test_metrics_weight_after_insert(client: TestClient):
    from datetime import timedelta
    today = date.today()
    client.post("/ingest/weight", json={
        "rows": [
            {
                "date": (today - timedelta(days=5)).isoformat(),
                "weight_kg": 89.4,
                "bmi": 28.5,
            },
            {
                "date": (today - timedelta(days=1)).isoformat(),
                "weight_kg": 89.2,
                "bmi": 28.4,
            },
        ],
    })
    resp = client.get("/metrics/weight?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["points"]) == 2
    assert body["points"][0]["value"] == 89.4


def test_metrics_weight_rejects_bad_days(client: TestClient):
    resp = client.get("/metrics/weight?days=0")
    assert resp.status_code == 422


def test_metrics_body_fat_endpoint(client: TestClient):
    from datetime import timedelta
    today = date.today()
    client.post("/ingest/weight", json={
        "rows": [
            {
                "date": (today - timedelta(days=10)).isoformat(),
                "weight_kg": 89.4,
                "bmi": 28.5,
                "body_fat_pct": 25.2,
            },
        ],
    })
    resp = client.get("/metrics/body_fat?days=90")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "body_fat_pct"
    assert len(body["points"]) == 1


def test_metrics_resting_hr_endpoint_empty(client: TestClient):
    resp = client.get("/metrics/resting_hr?days=30")
    assert resp.status_code == 200
    assert resp.json()["metric"] == "resting_hr"
    assert resp.json()["points"] == []


def test_metrics_sleep_endpoint_empty(client: TestClient):
    resp = client.get("/metrics/sleep?days=30")
    assert resp.status_code == 200
    assert resp.json()["metric"] == "total_minutes"


def test_metrics_steps_endpoint_empty(client: TestClient):
    resp = client.get("/metrics/steps?days=30")
    assert resp.status_code == 200
    assert resp.json()["metric"] == "count"