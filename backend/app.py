import json, math
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parents[1]
_raw = json.loads((ROOT / "data/wind.json").read_text())
ACTUAL: dict[str, int] = _raw["actual"]
# start time -> [(publishTime, generation)] sorted by publishTime (ISO-Z strings sort chronologically)
FC: dict[str, list] = defaultdict(list)
for pub, start, gen in _raw["forecast"]:
    FC[start].append((pub, gen))
for v in FC.values():
    v.sort()

app = FastAPI(title="Wind forecast decision support")
fmt = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def cutoff_for(day: date, hour: int) -> str:
    # January is GMT, so UK local time == UTC. Decision is made the day before delivery.
    return fmt(datetime(day.year, day.month, day.day, hour) - timedelta(days=1))


def latest_before(start: str, cutoff: str):
    """Latest forecast for `start` published at or before `cutoff`, as (publishTime, generation)."""
    f = FC.get(start, [])
    i = bisect_right(f, (cutoff, math.inf))
    return f[i - 1] if i else None


def delivery_days() -> list[date]:
    return sorted({date.fromisoformat(k[:10]) for k in ACTUAL if k >= "2026-01-02"})


def day_points(day: date, hour: int):
    cutoff = cutoff_for(day, hour)
    out = []
    for h in range(24):
        t = fmt(datetime(day.year, day.month, day.day, h))
        f = latest_before(t, cutoff)
        out.append({"t": t, "forecast": f and f[1], "publishTime": f and f[0], "actual": ACTUAL.get(t)})
    return out


def stats(errs: list[float], actuals: list[float]):
    n = len(errs)
    if not n:
        return {"n": 0}
    abs_ = sorted(abs(e) for e in errs)
    return {
        "n": n,
        "mae": sum(abs_) / n,
        "rmse": math.sqrt(sum(e * e for e in errs) / n),
        "bias": sum(errs) / n,  # forecast - actual; positive = over-forecast
        "mape": 100 * sum(abs(e) / a for e, a in zip(errs, actuals) if a) / max(1, sum(1 for a in actuals if a)),
        "p90_abs": abs_[min(n - 1, math.ceil(0.9 * n) - 1)],
    }


def accuracy(hour: int):
    daily, by_hour, rows = [], defaultdict(lambda: ([], [])), ([], [])
    for day in delivery_days():
        e, a = [], []
        for h, p in enumerate(day_points(day, hour)):
            if p["forecast"] is None or p["actual"] is None:
                continue
            err = p["forecast"] - p["actual"]
            e.append(err); a.append(p["actual"])
            by_hour[h][0].append(err); by_hour[h][1].append(p["actual"])
        rows[0].extend(e); rows[1].extend(a)
        daily.append({"day": str(day), **stats(e, a)})
    return {"overall": stats(*rows), "daily": daily,
            "by_hour": [{"hour": h, **stats(*by_hour[h])} for h in sorted(by_hour)]}


def horizon_accuracy():
    """Error vs how far ahead of the target the forecast was published (all forecasts, 6h bins)."""
    bins = defaultdict(lambda: ([], []))
    for start, fs in FC.items():
        a = ACTUAL.get(start)
        if a is None:
            continue
        for pub, gen in fs:
            h = (datetime.fromisoformat(start[:-1]) - datetime.fromisoformat(pub[:-1])).total_seconds() / 3600
            if h < 0:
                continue
            b = min(int(h // 6) * 6, 72)
            bins[b][0].append(gen - a); bins[b][1].append(a)
    return [{"horizon_h": b, **stats(*bins[b])} for b in sorted(bins)]


@app.get("/api/days")
def days():
    return [str(d) for d in delivery_days()]


@app.get("/api/decision")
def decision(day: date, cutoff_hour: int = Query(9, ge=0, le=23)):
    if day not in delivery_days():
        raise HTTPException(404, "No data for that delivery day")
    pts = day_points(day, cutoff_hour)
    p90 = accuracy(cutoff_hour)["overall"]["p90_abs"]
    for p in pts:
        f = p["forecast"]
        p["low"], p["high"] = (None, None) if f is None else (max(0, f - p90), f + p90)
    fs = [p["forecast"] for p in pts if p["forecast"] is not None]
    pubs = [p["publishTime"] for p in pts if p["publishTime"]]
    return {"day": str(day), "cutoff": cutoff_for(day, cutoff_hour), "p90_abs_error": p90,
            "forecast_published": [min(pubs), max(pubs)] if pubs else None,
            "mean_forecast": sum(fs) / len(fs) if fs else None, "points": pts}


@app.get("/api/accuracy")
def accuracy_ep(cutoff_hour: int = Query(9, ge=0, le=23)):
    return {**accuracy(cutoff_hour), "by_horizon": horizon_accuracy()}


dist = ROOT / "frontend/dist"
if dist.exists():  # Docker image serves the built UI; on Vercel the CDN does
    app.mount("/", StaticFiles(directory=dist, html=True))
