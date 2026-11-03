# ADR-0040: Delete placeholder data rather than label it; per-org status from per-org data

- **Status:** Accepted
- **Date:** 2026-11-02
- **Feature:** F18 (Pass S1, checkpoints 2 and 4)
- **Related:** ADR-0006, ADR-0012, ADR-0017, ADR-0035; supersedes the F07 swap contract
  in `config/dashboardPlaceholders.ts`

## Context

F07 shipped the Dashboard visually complete with DEMO data centralised in
`dashboardPlaceholders.ts`: five of six KPIs, fleet missions and battery, Nairobi blip
coordinates, an alerts list, a comms stack naming MQTT and LoRa. Some carried a DEMO tag;
the fleet overlay did not. A hardcoded `HDG 142° · 1.4 m/s` readout sat outside that file.
The one "real" KPI was `chart-data` length, capped at 5,000, so KNRA's 12,081 rows showed
as 5,000.

Separately, Satellite provider status read `SatelliteDataset.is_verified`, which is
global (the dataset has no organization): one tenant's retrieval showed as RETRIEVED to
every tenant, including orgs with no scenes.

## Decision

- **Fake data is deleted, not labelled.** A DEMO tag beside a confident number is still a
  number on screen. Where a real source exists the UI reads it; where none exists the
  element is removed. `dashboardPlaceholders.ts`, `ActiveAlerts.tsx` and
  `CommsLayers.tsx` are deleted (git keeps them).
- **Dashboard sources:** robots = stored data ∪ missions ∪ live pushes; status and blips
  from the live feed only (no fix → `OFFLINE · NO FIX`, no blip); missions from
  `/api/missions/`; records from the paginated `count`, never a capped list's length.
- **Absence is stated as absence.** Empty copy says what is known ("NO READINGS IN THIS
  ORGANIZATION", "NO IMU READINGS FOR THIS SELECTION"), never a cause the data cannot
  support ("this robot has no IMU sensor installed").
- **A capped view says it is capped** (Visualizations: "most recent 5,000 of 12,081").
- **Per-org status derives only from per-org rows.** Provider status is CONNECTED (this
  org has a scene on disk) or CATALOGED; the global RETRIEVED tier is dropped.

## Consequences

- Without a live robot the Dashboard is sparse: four real tiles, NO FIX rows, an empty
  map. That is the honest state; the demo fills it with the robots.
- There is no `/api/robots/`: a registered robot that has never logged, planned or
  pushed does not appear.
- `is_verified` still means "someone has pulled from this product" and stays useful to
  operators of the platform, not to tenants.
