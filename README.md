# Wind forecast decision desk (GB day-ahead)

Helps a day-ahead power buyer see the latest wind forecast available at decision time and quantify how wrong those forecasts have been. Data: Elexon BMRS `WINDFOR` (forecast) and `FUELHH` (`WIND` actuals), January 2026 decisions only.

**AI use:** this project was built with Claude Code (AI assistant).

**Live app:** _add Vercel URL here after deploying_

## Layout

| Path | What |
|---|---|
| `backend/app.py` | FastAPI app: `/api/days`, `/api/decision`, `/api/accuracy`; also serves the built UI in Docker |
| `api/index.py` | Vercel serverless entry point (re-exports the FastAPI app) |
| `scripts/fetch_data.py` | One-off download of the Elexon data into `data/wind.json` |
| `data/wind.json` | Committed snapshot (decisions 1–31 Jan 2026, so deliveries 2 Jan–1 Feb) |
| `frontend/` | React (Vite + Recharts) UI: Decision view and Forecast accuracy |
| `tests/test_api.py` | Pytest: no look-ahead, metric maths, endpoints |
| `Dockerfile`, `vercel.json` | Container and Vercel deployment |

## Run

Docker:
```bash
docker build -t wind . && docker run -p 8000:8000 wind   # http://localhost:8000
```
Local dev:
```bash
pip install -r requirements.txt -r requirements-dev.txt
uvicorn backend.app:app --reload          # API on :8000
cd frontend && npm install && npm run dev # UI on :5173, proxies /api
python -m pytest                          # tests
```
Deploy: `vercel --prod` from the repo root (config in `vercel.json`).

## Method (key assumptions)

- A decision for delivery day D is made on D-1 at a **cut-off, default 09:00 UTC** (= UK time in January; adjustable in the UI). For each hour of D we use the **most recent WINDFOR forecast published at or before the cut-off**, so nothing published later leaks in.
- Forecast and actual are compared at the same `startTime` (WINDFOR is hourly; the actual is the FUELHH half-hour value starting at that time).
- Metrics: MAE, RMSE, bias (forecast − actual), MAPE, P90 absolute error; also split per day, per hour of day and per forecast horizon.
- The decision-view uncertainty band is forecast ± January's P90 absolute error. It is in-sample, so indicative only.
- Demand and other generation are out of scope (wind data only), so the app shows wind, not the net buy volume.
