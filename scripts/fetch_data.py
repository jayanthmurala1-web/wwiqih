"""Download Jan-2026 decision data from Elexon BMRS into data/wind.json (run once; the snapshot is committed)."""
import json, urllib.request
from datetime import date, timedelta
from pathlib import Path

B = "https://data.elexon.co.uk/bmrs/api/v1/datasets"


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def days(a, b):
    while a <= b:
        yield a
        a += timedelta(days=1)


# Decisions are made on 1..31 Jan 2026, so we need forecasts published in that window
# and actuals for the delivery days 2 Jan..1 Feb.
forecast = []
for d in days(date(2026, 1, 1), date(2026, 1, 31)):
    n = d + timedelta(days=1)
    rows = get(f"{B}/WINDFOR/stream?publishDateTimeFrom={d}T00:00:00Z&publishDateTimeTo={n}T00:00:00Z&format=json")
    forecast += [[r["publishTime"], r["startTime"], r["generation"]] for r in rows]

actual = {}
for d in days(date(2026, 1, 2), date(2026, 2, 1)):
    n = d + timedelta(days=1)
    rows = get(f"{B}/FUELHH/stream?settlementDateFrom={d}&settlementDateTo={n}&fuelType=WIND&format=json")
    # the API range is inclusive of the end date, so drop anything past the last delivery day
    actual.update({r["startTime"]: r["generation"] for r in rows if r["fuelType"] == "WIND" and r["startTime"] < "2026-02-02"})

Path(__file__).parents[1].joinpath("data/wind.json").write_text(json.dumps({"forecast": forecast, "actual": actual}, separators=(",", ":")))
print(len(forecast), "forecast rows,", len(actual), "actual rows")
