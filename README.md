# Wind forecast decision desk (GB day-ahead)

Helps a day-ahead power buyer see the latest wind forecast available at decision time and quantify how wrong those forecasts have been. Data: Elexon BMRS `WINDFOR` (forecast) and `FUELHH` (`WIND` actuals), January 2026 decisions only.

**AI use:** this project was built with Claude Code (AI assistant).

**Live app:** https://wind-forecast-eight.vercel.app

## Layout

| Path | What |
|---|---|
| `backend/app.py` | FastAPI app: `/api/days`, `/api/decision`, `/api/accuracy`; also serves the built UI in Docker |
| `api/index.py` | Vercel serverless entry point (re-exports the FastAPI app) |
| `scripts/fetch_data.py` | One-off download of the Elexon data into `data/wind.json` |
| `data/wind.json` | Committed snapshot (decisions 1–31 Jan 2026, so deliveries 2 Jan–1 Feb) |
| `frontend/` | React (Vite + Recharts) UI: Decision view and Forecast accuracy |
| `tests/test_api.py` | Pytest regression suite (see Tests) |
| `.github/workflows/ci.yml` | CI: tests and frontend build on every push |
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

- **Scope:** decisions made 1–31 Jan 2026, so delivery days are **2 Jan – 1 Feb** (31 days, 744 hours). Anything outside is rejected (404).
- **Decision time:** delivery day D is decided on D-1 at a cut-off, default **09:50 UK time, the N2EX day-ahead auction gate closure** ([Nord Pool](https://support.nordpoolgroup.com/support/solutions/articles/8000088463-about-the-n2ex-day-ahead-auction)). January is GMT, so UK time = UTC. Other cut-offs in the UI (05:00, 08:00, 12:00) are what-if scenarios. WINDFOR is published at fixed times (02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30, 22:30 UTC), so each option picks up a different forecast run.
- **No look-ahead:** for each hour of D we use the most recent forecast published at or before the cut-off.
- **Comparison:** WINDFOR is hourly and FUELHH is half-hourly, so the actual for an hour is the **mean of its two half-hour readings**.
- **Metrics:** MAE, RMSE, bias (forecast − actual; positive = over-forecast), MAPE and P90 absolute error, overall and split by day and by hour of day.
- **Decision-view error range:** forecast ± the P90 absolute error from **delivery days already settled before the decision** (up to D-2). No later data is used. The first two days have no history, so no range is shown.
- **Lead-time chart:** uses every published forecast for in-scope hours, not just the decision-time one. It answers how error grows with lead time and is kept separate from the decision metrics.
- **Out of scope:** demand and other generation (wind data only), so the app shows wind, not the net volume to buy.

## Tests

`python -m pytest` runs 23 tests: scope boundaries, input validation, no look-ahead for every day and cut-off, a brute-force check of forecast selection, the error range ignoring future data (future actuals are tampered with and the range must not change), half-hour averaging, and an independent recompute of MAE and bias. GitHub Actions (`.github/workflows/ci.yml`) runs the tests and the frontend build on every push.
