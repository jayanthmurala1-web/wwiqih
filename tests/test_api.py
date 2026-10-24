from fastapi.testclient import TestClient

from backend.app import app, cutoff_for, latest_before, stats
from datetime import date

c = TestClient(app)


def test_no_lookahead():
    # every forecast used for delivery day D must be published before the D-1 cutoff
    for p in c.get("/api/decision", params={"day": "2026-01-15"}).json()["points"]:
        assert p["publishTime"] <= cutoff_for(date(2026, 1, 15), 9) == "2026-01-14T09:00:00Z"


def test_latest_before():
    pub, _ = latest_before("2026-01-15T12:00:00Z", "2026-01-14T09:00:00Z")
    assert pub <= "2026-01-14T09:00:00Z"


def test_stats():
    s = stats([10, -10], [100, 100])
    assert s["mae"] == 10 and s["bias"] == 0 and s["rmse"] == 10 and s["mape"] == 10


def test_accuracy_endpoint():
    r = c.get("/api/accuracy").json()
    assert r["overall"]["n"] > 600 and r["overall"]["mae"] > 0
    assert len(r["by_hour"]) == 24 and r["by_horizon"]
