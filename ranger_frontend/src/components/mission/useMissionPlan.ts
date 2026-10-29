// ─── RANGER V3 START: 15-mission-plan ───
/**
 * Mission planning state for one robot (F15 / Pass 6a).
 *
 * The draft is local until Save. Save creates (POST) a new mission or fully
 * replaces (PUT) the selected one; the server re-validates everything
 * (tenancy, region, bounds) and its answer is what the panel shows. A mission
 * that is no longer PENDING is locked: the server would 409 any edit, so the
 * map stops taking clicks rather than letting the operator plan into a wall.
 */
import { useCallback, useEffect, useMemo, useState } from "react"
import { createMission, errorLines, listMissions, replaceMission } from "@/api/missions"
import type { FieldMapWaypoint } from "@/components/map/FieldMap"
import { MAX_WAYPOINTS, THRESHOLD_M, type LatLon, type Mission } from "@/types/mission.types"

/** 1e-7 deg ~ 1 cm. More digits are noise from the click, not precision. */
const round7 = (x: number) => Math.round(x * 1e7) / 1e7

export interface Draft {
  name: string
  threshold: string // string so the field can be mid-edit ("", "1.")
  points: LatLon[]
}

const EMPTY: Draft = { name: "", threshold: String(THRESHOLD_M.default), points: [] }

function draftOf(m: Mission): Draft {
  return { name: m.name, threshold: String(m.threshold_m), points: m.waypoints.map(({ lat, lon }) => ({ lat, lon })) }
}

export function useMissionPlan(robotId: string | null) {
  const [missions, setMissions] = useState<Mission[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [note, setNote] = useState<string | null>(null)
  const [fitKey, setFitKey] = useState<number | null>(null)

  const selected = missions.find((m) => m.id === selectedId) ?? null
  const locked = !robotId || (selected !== null && selected.status !== "PENDING")

  const reload = useCallback(async () => {
    if (!robotId) return []
    const list = await listMissions(robotId)
    setMissions(list)
    return list
  }, [robotId])

  // Initial load. Fetch inline (not via reload) so state is only set in the
  // async callback, and a robot change mid-flight can't land stale missions.
  useEffect(() => {
    if (!robotId) return
    let live = true
    listMissions(robotId).then(
      (list) => live && setMissions(list),
      (e) => live && setErrors(errorLines(e)),
    )
    return () => {
      live = false
    }
  }, [robotId])

  const edit = (next: Draft) => {
    setDraft(next)
    setDirty(true)
    setNote(null)
    setErrors([])
  }

  const confirmDiscard = () => !dirty || window.confirm("Discard unsaved changes to this plan?")

  const select = (id: number | null) => {
    if (!confirmDiscard()) return
    const m = missions.find((x) => x.id === id) ?? null
    setSelectedId(m ? m.id : null)
    setDraft(m ? draftOf(m) : EMPTY)
    setFitKey(m ? m.id : null)
    setDirty(false)
    setErrors([])
    setNote(null)
  }

  const addPoint = useCallback(
    (lng: number, lat: number) => {
      setDraft((d) => {
        if (d.points.length >= MAX_WAYPOINTS) return d
        return { ...d, points: [...d.points, { lat: round7(lat), lon: round7(lng) }] }
      })
      setDirty(true)
      setNote(null)
      setErrors([])
    },
    []
  )

  const move = (i: number, delta: -1 | 1) => {
    const j = i + delta
    if (j < 0 || j >= draft.points.length) return
    const pts = [...draft.points]
    ;[pts[i], pts[j]] = [pts[j], pts[i]]
    edit({ ...draft, points: pts })
  }

  const remove = (i: number) => edit({ ...draft, points: draft.points.filter((_, k) => k !== i) })

  const threshold = Number(draft.threshold)
  const thresholdOk = draft.threshold.trim() !== "" && threshold >= THRESHOLD_M.min && threshold <= THRESHOLD_M.max
  const canSave = !locked && !saving && dirty && draft.name.trim() !== "" && draft.points.length > 0 && thresholdOk

  const save = async () => {
    if (!robotId || !canSave) return
    setSaving(true)
    setErrors([])
    const body = {
      name: draft.name.trim(),
      description: selected?.description ?? "",
      robot_id_str: robotId,
      threshold_m: threshold,
      waypoints: draft.points,
    }
    try {
      const saved = selectedId === null ? await createMission(body) : await replaceMission(selectedId, body)
      await reload()
      setSelectedId(saved.id)
      setDraft(draftOf(saved))
      setDirty(false)
      setNote(`SAVED #${saved.id} · ${saved.waypoints.length} WAYPOINTS`)
    } catch (e) {
      setErrors(errorLines(e))
    } finally {
      setSaving(false)
    }
  }

  /** Display state per waypoint. A saved, non-PENDING mission shows its DB
   *  statuses; the first PENDING of a running mission is "active". */
  const mapWaypoints: FieldMapWaypoint[] = useMemo(() => {
    const showDb = selected && !dirty && selected.status !== "PENDING"
    const activeIdx =
      showDb && selected.status === "IN_PROGRESS" ? selected.waypoints.findIndex((w) => w.status === "PENDING") : -1
    return draft.points.map((p, i) => {
      let state: FieldMapWaypoint["state"] = "pending"
      if (showDb) {
        const st = selected.waypoints[i]?.status
        state = i === activeIdx ? "active" : st === "COMPLETED" ? "completed" : st === "SKIPPED" ? "skipped" : "pending"
      }
      return { lng: p.lon, lat: p.lat, label: String(i + 1), state }
    })
  }, [draft.points, selected, dirty])

  return {
    missions, selected, selectedId, draft, dirty, saving, errors, note, locked, canSave, thresholdOk, fitKey,
    mapWaypoints, select, edit, addPoint, move, remove, save,
  }
}
// ─── RANGER V3 END: 15-mission-plan ───
