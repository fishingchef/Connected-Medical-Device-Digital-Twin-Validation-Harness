A connected-device test simulator that generates realistic wearable data and system failure conditions so developers and V&V can test device-gateway-cloud-dashboard behavior without needing a live wearer every time.
# Connected Medical Device Digital Twin — Validation Harness

End-to-end simulation platform that answers:

> **Under known patient activity + gateway/network failure conditions, does the connected device system preserve data integrity and show the right dashboard behavior?**

## Live Demo
Deploy to Railway in one click → see [Deployment](#deployment)

---

## Architecture

```
Physiology Generator → Wearable Simulator → Gateway Simulator
        → Network Fault Injector → Mock Cloud (FastAPI)
        → Dashboard (React) → Validation Report (Pytest)
```

## Modules

| Module | File | Description |
|--------|------|-------------|
| Physiology Generator | `core/generators/physiology.py` | Synthetic HR, RR, temp, motion time-series |
| Wearable Simulator | `core/simulators/wearable.py` | Firmware state, battery, BLE, local storage |
| Gateway Simulator | `core/simulators/gateway.py` | Wi-Fi, BLE scan, upload queue, retry logic |
| Fault Injector | `core/injectors/network.py` | Latency, packet loss, outages, TLS failures |
| Mock Cloud | `api/cloud.py` | FastAPI ingest, dedup, timestamp normalization |
| Validation Engine | `validation/engine.py` | Pytest-based scenario runner + report |

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Deployment

### Railway (recommended — free tier)
1. Push repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add two services: `backend/` and `frontend/`
4. Set env vars (see `.env.example`)
5. Railway auto-detects FastAPI + Vite and deploys

### Render (alternative)
- Backend: Web Service → `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- Frontend: Static Site → `npm run build` → publish `dist/`

## Running Scenarios

```bash
# Via API
POST /api/scenarios/run
{
  "scenario_id": "GW_WIFI_OUTAGE_01",
  "duration_minutes": 120,
  "outage_start": 40,
  "outage_end": 60
}

# Via CLI
cd backend
python -m validation.run --scenario GW_WIFI_OUTAGE_01

# Via pytest
pytest validation/tests/ -v --html=report.html
```
