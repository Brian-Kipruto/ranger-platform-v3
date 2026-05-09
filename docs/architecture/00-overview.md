# 00 — System Architecture Overview

**Audience:** anyone who needs the big picture. Read this before diving into specific features or apps.
**Last updated:** 2026-05-09 (Phase 1 complete)

---

## What R.A.N.G.E.R. is

A **Robot-as-a-Service (RaaS)** platform. ByteAnza (the operator) owns and deploys autonomous environmental reconnaissance robots; client organizations pay for missions and data access without ever owning the hardware.

Three distinct user types:

1. **ByteAnza staff** (us) — manage the entire fleet, all organizations, all data
2. **Commercial clients** (mining co., NGO, environmental firm) — pay for deployments, control their robots, get compliance reports, scoped strictly to their organization's data
3. **Community / NGO viewers** — read-only access to public environmental data, can submit survey requests, cannot control robots

---

## Three-tier system

```
┌──────────────────────────────────────────────────────────────────────┐
│                         WEB CLIENTS                                  │
│  Commercial dashboard | Community portal | Admin console (us)        │
│              React 19 + TS + Vite + Tailwind v4                      │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │
                  HTTP /api/*  +  WebSocket /ws/*
                                  │
┌─────────────────────────────────▼────────────────────────────────────┐
│                       PLATFORM BACKEND                               │
│                                                                      │
│  Django 5 + DRF (REST API)                                           │
│  Channels + Daphne (WebSocket)                                       │
│  PostgreSQL 16 (data) + Redis 7 (channels, cache, queues)            │
│  Celery (async tasks — reports, ML, OTA)                             │
│  Stripe (subscription billing)                                       │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │
                       rosbridge over WebSocket
                                  │
┌─────────────────────────────────▼────────────────────────────────────┐
│                    ROBOT (Jetson Orin Nano)                          │
│                                                                      │
│  Ubuntu 22.04 + ROS 2 Humble                                         │
│  Nav2 (autonomous navigation)                                        │
│  RTABMap (SLAM)                                                      │
│  rosbridge_server (WebSocket bridge to platform)                     │
│  Ollama + Gemma 2 (on-device AI for offline ops)                     │
│  micro-ROS on Arduino Mega (low-level sensor interface)              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Backend application structure

13 Django apps, each owning one bounded concern:

| App | Owns |
|-----|------|
| **accounts** | Organization (tenant), CustomUser, auth |
| **core** | Robot, SensorType, lean SensorLog, decoupled per-sensor logs (RadiationLog, AirQualityLog, ImuBaroLog) |
| **missions** | Mission, Waypoint, ActionType, MissionAction |
| **ros_bridge** | rosbridge integration — subscribes to robot topics, publishes commands |
| **visualization** | Saved layouts, dashboard widgets, panel configs |
| **alerts** | AlertRule, AlertEvent, Notification |
| **reports** | ComplianceReport, ReportTemplate, PDF generation |
| **billing** | Subscription, UsageRecord, Invoice (Stripe-backed) |
| **platform_config** | SavedView, branding, tenant config |
| **ai_assistant** | ConversationSession, MissionPlanRequest (Gemma 2 chat) |
| **community** | SurveyRequest, PublicDataset (community portal) |
| **fleet** | SoftwareRelease, UpdateDeployment (OTA updates) |
| **audit** | AuditLog (every API action tracked) |

Pattern: each app exposes its API under `/api/<app>/` (mostly), declares its models, defines its admin, and ships migrations that don't depend on other apps' migration history.

---

## Data flow patterns

### Read flow (client viewing data)

```
Browser
  ↓ GET /api/missions/  (with JWT)
Vite dev proxy (in dev) → Django :8000
  ↓
DRF view authenticates, filters by request.user.organization
  ↓
PostgreSQL query
  ↓
Serializer → JSON
  ↓
Browser updates state (Zustand) → re-renders
```

### Live data flow (robot → frontend)

```
Robot publishes ROS topic /ranger/radiation
  ↓
rosbridge_server (port 9090 on Jetson)
  ↓ WebSocket
Django ros_bridge app (roslibpy client) [subscribes]
  ↓ saves to RadiationLog
  ↓ broadcasts via Channels group "dashboard"
Channels Redis layer
  ↓
DashboardConsumer (per connected client)
  ↓ filters by user's org
WebSocket
  ↓
Frontend useWebSocket hook → updates Zustand → re-renders
```

### Write flow (client commanding a mission)

```
Browser: user clicks "Launch Mission"
  ↓ WebSocket message {type: "mission_command", action: "START", mission_id: 42}
DashboardConsumer.receive_json
  ↓ verify user has missions.launch_mission permission
  ↓ verify mission belongs to user's org
  ↓ update Mission.status to IN_PROGRESS in DB
  ↓ broadcast via Channels group "robot_control"
Robot listener (or rosbridge publisher)
  ↓ publishes /goal_pose ROS topic
Nav2 receives goal, robot starts moving
```

---

## Multi-tenancy

Single Postgres database. Every tenant-scoped row has an `organization_id` FK. Every query filters by `request.user.organization`. Authorization via Django Groups, not a `role` enum.

ADR: [`decisions/0002-multi-tenant-via-organization-fk.md`](../decisions/0002-multi-tenant-via-organization-fk.md)

---

## Why this stack

| Choice | Why |
|---|---|
| Django over FastAPI/Node | Mature ORM, built-in admin, auth, migrations, permissions. RaaS = lots of CRUD + admin work. |
| DRF | Best-in-class REST framework on Django |
| Channels + Daphne | Real-time data is core to robotics. Channels integrates with Django without forcing async-everywhere. |
| PostgreSQL + PostGIS (later) | Need geospatial queries for missions. PostGIS is the gold standard. |
| Redis | Channels layer + Celery broker + cache. One service, three jobs. |
| React + TypeScript | TypeScript catches refactor bugs early; React's ecosystem is unmatched for data visualization. |
| Vite | Fast dev server. Native ESM. |
| Tailwind v4 | Utility classes. v4's plugin pipeline is much faster than v3's PostCSS. |
| Zustand | Lighter than Redux for app state; cleaner than Context for non-trivial state. |
| ROS 2 + rosbridge | Industry standard for robotics. rosbridge gives us a stable WebSocket interface to any ROS topic. |

---

## Security architecture (high-level)

| Layer | Mechanism |
|---|---|
| Auth | JWT (15-min access + 7-day refresh, refresh rotates) + 2FA (later phase) |
| Authorization | Django Groups + Permissions, enforced in DRF views and Channels consumers |
| Tenant isolation | `organization` FK + filtered querysets in every view |
| Transport | TLS 1.3 (production); HTTPS-only enforced |
| Robot ↔ cloud | mTLS planned; signed OTA updates (later phase) |
| Audit | Every API action logged with user, action, IP, timestamp |
| Secrets | `.env` files (dev), env vars (prod), never in code |

---

## Phase plan

| Phase | Status | Scope |
|---|---|---|
| 1 | ✅ done | Foundation scaffold |
| 2 | 🔜 next | Auth feature |
| 3 | | Live ROS 2 data |
| 4 | | Visualization panels |
| 5 | | Mission control |
| 6 | | Bag recording + playback |
| 7 | | Alerts + monitoring |
| 8 | | Compliance reporting |
| 9 | | Business features (billing, audit) |
| 10 | | AI assistant |
| 11 | | Community portal |

---

## Where to look for more detail

- **Specific feature:** `docs/features/<XX>-<name>.md`
- **Specific decision:** `docs/decisions/<NNNN>-<topic>.md`
- **Setup or env:** `docs/setup/<NN>-<step>.md`
- **Specific bug or weird thing:** `docs/troubleshooting/<NNN>-<symptom>.md`

---

*Document last updated: 2026-05-09*