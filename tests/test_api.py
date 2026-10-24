from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend import app as m

c = TestClient(m.app)
CUTOFFS = ["05:00", "08:00", "09:50", "12:00"]


# --- scope -----------------------------------------------------------------

def test_delivery_days_are_exactly_january_decisions():
    days = c.get("/api/days").json()
    assert days[0] == "2026-01-02" and days[-1] == "2026-02-01" and len(days) == 31


@pytest.mark.parametrize("day", ["2026-01-01", "2026-02-02"])
def test_out_of_scope_days_rejected(day):
    assert c.get("/api/decision", params={"day": day}).status_code == 404


@pytest.mark.parametrize("cutoff", ["9", "24:00", "09:60", "9:50", "abc"])
def test_bad_cutoff_rejected(cutoff):
    assert c.get("/api/accuracy", params={"cutoff": cutoff}).status_code == 422


def test_default_cutoff_is_n2ex_gate():
    assert c.get("/api/decision", params={"day": "2026-01-15"}).json()["cutoff"] == "2026-01-14T09:50:00Z"


# --- no look-ahead -----------------------------------------------------------

@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_no_forecast_published_after_cutoff_any_day(cutoff):
    for d in m.delivery_days():
        cut = m.cutoff_for(d, cutoff)
        for p in m.day_points(d, cutoff):
            assert p["publishTime"] is None or p["publishTime"] <= cut


def test_latest_before_matches_brute_force():
    # independent oracle: linear scan instead of bisect
    for start, fs in list(m.FC.items())[::50]:
        for cut in ("2026-01-10T09:50:00Z", "2026-01-20T08:00:00Z"):
            ok = [f for f in fs if f[0] <= cut]
            assert m.latest_before(start, cut) == (max(ok) if ok else None)


def test_every_delivery_hour_has_a_forecast_at_gate():
    assert all(p["forecast"] is not None for d in m.delivery_days() for p in m.day_points(d, "09:50"))


# --- error band uses only past information ------------------------------------

def test_history_only_includes_days_settled_before_decision():
    assert max(m.history_days(date(2026, 1, 15))) == date(2026, 1, 13)
    assert m.history_days(date(2026, 1, 3)) == []


def test_no_history_means_no_band():
    r = c.get("/api/decision", params={"day": "2026-01-03"}).json()
    assert r["history"]["n"] == 0 and all(p["low"] is None for p in r["points"])


def test_band_ignores_future_actuals(monkeypatch):
    def band():
        m.day_errors.cache_clear()
        return [(p["low"], p["high"]) for p in m.decision(date(2026, 1, 15), "09:50")["points"]]

    before = band()
    # corrupt every actual from the decision day onwards; the band must not move
    future = {k: v * 3 for k, v in m.ACTUAL.items() if k >= "2026-01-14"}
    monkeypatch.setattr(m, "ACTUAL", {**m.ACTUAL, **future})
    assert band() == before
    monkeypatch.undo()
    m.day_errors.cache_clear()


# --- comparison & metric maths -------------------------------------------------

def test_actual_is_mean_of_two_half_hours():
    t = datetime(2026, 1, 15, 12)
    assert m.actual_hour(t) == (m.ACTUAL["2026-01-15T12:00:00Z"] + m.ACTUAL["2026-01-15T12:30:00Z"]) / 2


def test_stats_known_values():
    s = m.stats([10, -10, 20, -20], [100, 100, 200, 200])
    assert s["mae"] == 15 and s["bias"] == 0 and s["mape"] == 10
    assert s["rmse"] == pytest.approx((250) ** 0.5) and s["p90_abs"] == 20
    assert m.stats([], []) == {"n": 0}


def test_overall_mae_matches_independent_recompute():
    errs = []
    for d in m.delivery_days():
        cut = m.cutoff_for(d, "09:50")
        for h in range(24):
            t = datetime(d.year, d.month, d.day, h)
            fs = [g for pub, g in m.FC[m.fmt(t)] if pub <= cut]
            a = [m.ACTUAL[m.fmt(t)], m.ACTUAL[m.fmt(t + timedelta(minutes=30))]]
            errs.append(fs[-1] - sum(a) / 2)
    o = c.get("/api/accuracy").json()["overall"]
    assert o["n"] == len(errs) == 744
    assert o["mae"] == pytest.approx(sum(map(abs, errs)) / len(errs))
    assert o["bias"] == pytest.approx(sum(errs) / len(errs))


def test_daily_and_hourly_breakdowns_add_up():
    a = c.get("/api/accuracy").json()
    assert sum(d["n"] for d in a["daily"]) == a["overall"]["n"] == sum(h["n"] for h in a["by_hour"])
    assert len(a["daily"]) == 31 and len(a["by_hour"]) == 24


def test_horizon_bins_are_non_negative_and_in_scope():
    hz = m.horizon_accuracy()
    assert hz and all(0 <= b["horizon_h"] <= 72 and b["n"] > 0 for b in hz)
