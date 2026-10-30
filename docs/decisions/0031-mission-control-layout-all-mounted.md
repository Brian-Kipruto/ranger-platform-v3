# ADR-0031: `/mission` layout — map | camera, plan | drive, nothing unmounts

- **Status:** Accepted
- **Date:** 2026-10-29 (layout), 2026-10-30 (height match)
- **Feature:** F15 (fork 7)
- **Related:** ADR-0024 (MJPEG video and the frozen-feed watchdog)

## Context

F14 filled `/mission` with the camera and `DrivePanel`. Pass 6 adds a map and a
waypoint list; during a run the operator needs the camera (teleop), the blip and the
waypoints at once.

## Decision

- Top row: **map | camera**, equal halves. Bottom row: **mission plan | drive**.
- Everything stays mounted. The map's viewport height follows the camera panel's
  (`ResizeObserver`, two-column layout only; 45vh stacked). Planning on a bigger map
  uses `FieldMap`'s existing EXPAND.

## Rejected

- **Tabs or a map/camera toggle:** unmounting `CameraPanel` closes the MJPEG and
  reconnects on every toggle; hiding it keeps the Orin encoding for nobody. Both hurt
  on a link that already stalls outdoors (TS-044).
- **Map large, camera picture-in-picture:** shrinks the image the operator drives by.

## Consequences

Signed off on the bench (6c). Panels within 1 px. MapLibre's own `ResizeObserver`
redraws the canvas when the height changes.
