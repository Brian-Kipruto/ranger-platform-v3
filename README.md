# R.A.N.G.E.R. Platform V3

Robot-as-a-Service platform for autonomous environmental reconnaissance, built around a ROS 2 Jetson-powered field robot operating in Kenya.

## Stack

- **Backend:** Django 5 + DRF + Channels + PostgreSQL 16 + Redis 7
- **Frontend:** React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui
- **Robot:** ROS 2 Humble on Jetson Orin Nano (rosbridge_server bridge)

## Status

🚧 Phase 1 — foundation scaffold in progress.

## Quick Start (Development)

```bash
# Terminal 1 — services (Postgres + Redis)
docker compose up

# Terminal 2 — backend
source .venv/bin/activate
cd ranger_backend
daphne -p 8000 ranger_backend.asgi:application

# Terminal 3 — frontend
cd ranger_frontend
npm run dev
```

Open http://localhost:5173

## Documentation

Architecture, build phases, and feature specs live in `docs/` (TBD).

## License

TBD
