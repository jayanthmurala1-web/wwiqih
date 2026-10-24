import json, math
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parents[1]
# Decisions made 1..31 Jan 2026 -> delivery days 2 Jan..1 Feb.
FIRST_DAY, LAST_DAY = date(2026, 1, 2), date(2026, 2, 1)
# N2EX (Nord Pool) GB day-ahead auction gate closure, UK time.
GATE = "09:50"

_raw = json.loads((ROOT / "data/wind.json").read_text())
ACTUAL: dict[str, int] = _raw["actual"]  # half-hourly, keyed by startTime
# start time -> [(publishTime, generation)] sorted by publishTime (ISO-Z strings sort chronologically)
FC: dict[str, list] = defaultdict(list)
for pub, start, gen in _raw["forecast"]:
    FC[start].append((pub, gen))
for v in FC.values():
    v.sort()

app = FastAPI(title="Wind forecast decision support")
fmt = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
CUTOFF = Query(GATE, pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="Decision time on the day before delivery, HH:MM UK time")


def cutoff_for(day: date, hhmm: str) -> str:
    # January is GMT, so UK local time == UTC. Decision is made the day before delivery.
    h, m = map(int, hhmm.split(":"))
    return fmt(datetime(day.year, day.month, day.day, h, m) - timedelta(days=1))


def latest_before(start: str, cutoff: str):
    """Latest forecast for `start` published at or before `cutoff`, as (publishTime, generation)."""
    f = FC.get(start, [])
    i = bisect_right(f, (cutoff, math.inf))
    return f[i - 1] if i else None


def actual_hour(t: datetime):
    """Mean of the two half-hourly actuals in the hour starting at t (WINDFOR is hourly)."""
    a, b = ACTUAL.get(fmt(t)), ACTUAL.get(fmt(t + timedelta(minutes=30)))
    return None if a is None or b is None else (a + b) / 2


def delivery_days() -> list[date]:
    return [FIRST_DAY + timedelta(days=i) for i in range((LAST_DAY - FIRST_DAY).days + 1)]


def day_points(day: date, hhmm: str):
    cutoff = cutoff_for(day, hhmm)
    out = []
    for h in range(24):
        t = datetime(day.year, day.month, day.day, h)
        f = latest_before(fmt(t), cutoff)
        out.append({"t": fmt(t), "forecast": f and f[1], "publishTime": f and f[0], "actual": actual_hour(t)})
    return out


@lru_cache(maxsize=None)
def day_errors(day: date, hhmm: str):
    """(errors, actuals) per hour for one delivery day; error = forecast - actual."""
    e, a = [], []
    for p in day_points(day, hhmm):
        if p["forecast"] is not None and p["actual"] is not None:
            e.append(p["forecast"] - p["actual"]); a.append(p["actual"])
    return tuple(e), tuple(a)


def stats(errs, actuals):
    n = len(errs)
    if not n:
        return {"n": 0}
    abs_ = sorted(abs(e) for e in errs)
    nz = [(e, a) for e, a in zip(errs, actuals) if a]
    return {
        "n": n,
        "mae": sum(abs_) / n,
        "rmse": math.sqrt(sum(e * e for e in errs) / n),
        "bias": sum(errs) / n,  # positive = over-forecast
        "mape": 100 * sum(abs(e) / a for e, a in nz) / len(nz) if nz else None,
        "p90_abs": abs_[math.ceil(0.9 * n) - 1],
    }


def pooled(days, hhmm):
    e, a = [], []
    for d in days:
        de, da = day_errors(d, hhmm)
        e += de; a += da
    return stats(e, a)


def history_days(day: date) -> list[date]:
    """Delivery days fully settled before the decision for `day` (decision on D-1, so up to D-2)."""
    return [d for d in delivery_days() if d <= day - timedelta(days=2)]


def accuracy(hhmm: str):
    days = delivery_days()
    by_hour = defaultdict(lambda: ([], []))
    for d in days:
        for h, p in enumerate(day_points(d, hhmm)):
            if p["forecast"] is not None and p["actual"] is not None:
                by_hour[h][0].append(p["forecast"] - p["actual"]); by_hour[h][1].append(p["actual"])
    return {"overall": pooled(days, hhmm),
            "daily": [{"day": str(d), **stats(*day_errors(d, hhmm))} for d in days],
            "by_hour": [{"hour": h, **stats(*by_hour[h])} for h in sorted(by_hour)]}


@lru_cache(maxsize=1)
def horizon_accuracy():
    """Error vs lead time over every published forecast for in-scope target hours (6h bins).
    Deliberately not limited to decision-time forecasts: it answers 'how does error grow with lead time?'"""
    bins = defaultdict(lambda: ([], []))
    lo, hi = fmt(datetime.combine(FIRST_DAY, datetime.min.time())), fmt(datetime.combine(LAST_DAY + timedelta(days=1), datetime.min.time()))
    for start, fs in FC.items():
        if not lo <= start < hi:
            continue
        a = actual_hour(datetime.fromisoformat(start[:-1]))
        if a is None:
            continue
        for pub, gen in fs:
            h = (datetime.fromisoformat(start[:-1]) - datetime.fromisoformat(pub[:-1])).total_seconds() / 3600
            if h >= 0:
                b = min(int(h // 6) * 6, 72)
                bins[b][0].append(gen - a); bins[b][1].append(a)
    return [{"horizon_h": b, **stats(*bins[b])} for b in sorted(bins)]


@app.get("/api/days")
def days():
    return [str(d) for d in delivery_days()]


@app.get("/api/decision")
def decision(day: date, cutoff: str = CUTOFF):
    if not FIRST_DAY <= day <= LAST_DAY:
        raise HTTPException(404, f"Delivery day must be between {FIRST_DAY} and {LAST_DAY}")
    pts = day_points(day, cutoff)
    hist_days = history_days(day)
    hist = pooled(hist_days, cutoff)
    p90 = hist.get("p90_abs")
    for p in pts:
        f = p["forecast"]
        p["low"], p["high"] = (None, None) if f is None or p90 is None else (max(0, f - p90), f + p90)
    fs = [p["forecast"] for p in pts if p["forecast"] is not None]
    pubs = [p["publishTime"] for p in pts if p["publishTime"]]
    return {"day": str(day), "cutoff": cutoff_for(day, cutoff),
            "history": {"days": len(hist_days), **hist},  # only errors known before the decision
            "forecast_published": [min(pubs), max(pubs)] if pubs else None,
            "mean_forecast": sum(fs) / len(fs) if fs else None, "points": pts}


@app.get("/api/accuracy")
def accuracy_ep(cutoff: str = CUTOFF):
    return {**accuracy(cutoff), "by_horizon": horizon_accuracy()}


dist = ROOT / "frontend/dist"
if dist.exists():  # Docker image serves the built UI; on Vercel the CDN does
    app.mount("/", StaticFiles(directory=dist, html=True))
