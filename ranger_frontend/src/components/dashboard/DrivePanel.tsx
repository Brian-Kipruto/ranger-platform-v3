// ─── RANGER V3 START: 14-teleop ───
/**
 * DrivePanel: drive the selected robot from the console (F14 5a).
 *
 * Owns its own /ws/teleop/<robot>/ socket, opened only when the operator ARMS.
 * The token is read once, at arm (ADR-0016: checked at connect only), so a token
 * refresh never drops a drive session. No auto-reconnect: after any close the
 * operator re-arms deliberately.
 *
 * Deadman: commands are sent only while a key or button is HELD, 20 Hz. Release
 * sends one "stop"; idle sends "hold" (keeps the server's one-driver lease) and no
 * drive. Window blur, a hidden tab, pointer leave/cancel and unmount all count as
 * release. Below this: uno_bridge stops 250 ms after the last command, the Uno 250 ms
 * after the last M line, and the RC switch (SwA) must be in NET for any of it.
 */
import { useCallback, useEffect, useRef, useState } from "react"
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { useAuthStore } from "@/stores/authStore"
import {
  CLOSE_TEXT, DRIVE_KEYS, ERROR_TEXT, commandFrom, isZero, teleopUrl, type Dir,
} from "@/lib/teleop"

const SUBPROTOCOL = "ranger.v1"
const SEND_MS = 50        // 20 Hz while held
const HOLD_MS = 1000      // idle keepalive, well inside the 3 s lease

type Phase = "idle" | "connecting" | "armed" | "closed"

export function DrivePanel({ robotId }: { robotId: string }) {
  const [phase, setPhase] = useState<Phase>("idle")
  const [note, setNote] = useState<string>("")
  const [speed, setSpeed] = useState(0.6)
  const [held, setHeld] = useState<ReadonlySet<Dir>>(new Set())

  const ws = useRef<WebSocket | null>(null)
  const heldRef = useRef<Set<Dir>>(new Set())
  const speedRef = useRef(speed)
  useEffect(() => { speedRef.current = speed }, [speed])

  const press = useCallback((d: Dir) => {
    heldRef.current.add(d)
    setHeld(new Set(heldRef.current))
  }, [])
  const release = useCallback((d?: Dir) => {
    if (d) heldRef.current.delete(d)
    else heldRef.current.clear()
    setHeld(new Set(heldRef.current))
  }, [])

  const disarm = useCallback(() => {
    release()
    ws.current?.close(1000)
    ws.current = null
  }, [release])

  const arm = useCallback(() => {
    const token = useAuthStore.getState().accessToken
    if (!token || ws.current) return
    setPhase("connecting")
    setNote("")
    const sock = new WebSocket(teleopUrl(robotId), [SUBPROTOCOL, `jwt.${token}`])
    ws.current = sock
    sock.onmessage = (e) => {
      let msg: { type?: string; reason?: string }
      try { msg = JSON.parse(e.data) } catch { return }
      if (msg.type === "ready") setPhase("armed")
      else if (msg.type === "error") setNote(ERROR_TEXT[msg.reason ?? ""] ?? `Error: ${msg.reason}`)
    }
    sock.onclose = (e) => {
      if (ws.current === sock) ws.current = null
      heldRef.current.clear()
      setHeld(new Set())
      setPhase("closed")
      setNote(e.code === 1000 ? "Disarmed." : CLOSE_TEXT[e.code] ?? `Closed (${e.code}).`)
    }
  }, [robotId])

  // Changing robot or leaving the page disarms.
  useEffect(() => disarm, [robotId, disarm])

  // Send loop: drive while held, one stop on release, hold while idle.
  useEffect(() => {
    if (phase !== "armed") return
    let wasDriving = false
    let lastSent = 0
    const tick = setInterval(() => {
      const sock = ws.current
      if (!sock || sock.readyState !== WebSocket.OPEN) return
      const cmd = commandFrom(heldRef.current, speedRef.current)
      const now = Date.now()
      if (!isZero(cmd)) {
        sock.send(JSON.stringify({ type: "drive", ...cmd }))
        wasDriving = true
        lastSent = now
      } else if (wasDriving) {
        sock.send(JSON.stringify({ type: "stop" }))
        wasDriving = false
        lastSent = now
      } else if (now - lastSent >= HOLD_MS) {
        sock.send(JSON.stringify({ type: "hold" }))
        lastSent = now
      }
    }, SEND_MS)
    return () => clearInterval(tick)
  }, [phase])

  // Keyboard, plus the deadman triggers, only while armed.
  useEffect(() => {
    if (phase !== "armed") return
    const typing = (t: EventTarget | null) =>
      t instanceof HTMLElement && (t.tagName === "INPUT" && (t as HTMLInputElement).type !== "range"
        || t.tagName === "TEXTAREA" || t.isContentEditable)
    const down = (e: KeyboardEvent) => {
      if (typing(e.target)) return
      if (e.key === " ") { e.preventDefault(); release(); return }
      const d = DRIVE_KEYS[e.key.length === 1 ? e.key.toLowerCase() : e.key]
      if (!d) return
      e.preventDefault()
      press(d)
    }
    const up = (e: KeyboardEvent) => {
      const d = DRIVE_KEYS[e.key.length === 1 ? e.key.toLowerCase() : e.key]
      if (d) release(d)
    }
    const stopAll = () => release()
    const onVis = () => { if (document.hidden) release() }
    window.addEventListener("keydown", down)
    window.addEventListener("keyup", up)
    window.addEventListener("blur", stopAll)
    document.addEventListener("visibilitychange", onVis)
    return () => {
      window.removeEventListener("keydown", down)
      window.removeEventListener("keyup", up)
      window.removeEventListener("blur", stopAll)
      document.removeEventListener("visibilitychange", onVis)
      release()
    }
  }, [phase, press, release])

  const armed = phase === "armed"
  const cmd = commandFrom(held, speed)
  const tone = armed ? (isZero(cmd) ? "ok" : "warn") : phase === "connecting" ? "info" : "dim"

  const padBtn = (d: Dir, label: string) => (
    <button
      type="button"
      disabled={!armed}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); press(d) }}
      onPointerUp={() => release(d)}
      onPointerCancel={() => release(d)}
      onLostPointerCapture={() => release(d)}
      className={
        "h-10 rounded-md border font-mono text-[11px] select-none touch-none " +
        (held.has(d)
          ? "bg-[var(--accent)] text-white border-transparent"
          : "bg-surface-3 border-border-soft text-fg-soft") +
        (armed ? "" : " opacity-40 cursor-not-allowed")
      }
    >
      {label}
    </button>
  )

  return (
    <Panel
      title="DRIVE"
      right={<MonoLabel size="xs" tone="accent">{robotId}</MonoLabel>}
    >
      <div className="p-[13px] flex flex-col gap-[11px]">
        <div className="flex items-center justify-between">
          <MonoLabel size="sm" tone={tone}>
            {armed ? (isZero(cmd) ? "ARMED · IDLE" : `DRIVING · ${cmd.lin} / ${cmd.ang}`) : phase.toUpperCase()}
          </MonoLabel>
          {armed || phase === "connecting" ? (
            <button type="button" onClick={disarm}
              className="px-3 py-1 rounded-md border border-border text-[11px] font-mono text-fg-soft">
              DISARM
            </button>
          ) : (
            <button type="button" onClick={arm}
              className="px-3 py-1 rounded-md bg-[var(--accent)] text-white text-[11px] font-mono">
              ARM
            </button>
          )}
        </div>

        <div className="grid grid-cols-3 gap-[6px] w-[180px] self-center">
          <span />{padBtn("fwd", "▲ W")}<span />
          {padBtn("left", "◀ A")}{padBtn("back", "▼ S")}{padBtn("right", "D ▶")}
        </div>

        <label className="flex items-center gap-2">
          <MonoLabel size="xs" tone="dim">SPEED</MonoLabel>
          <input type="range" min={0.2} max={1} step={0.1} value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))} className="flex-1" />
          <MonoLabel size="xs" tone="soft">{Math.round(speed * 100)}%</MonoLabel>
        </label>

        <MonoLabel size="xs" tone="faint">
          Hold W A S D / arrows or the pad. Release, Space, or leaving the tab stops. RC SwA must be in NET.
        </MonoLabel>
        {note ? <MonoLabel size="xs" tone={phase === "closed" && note !== "Disarmed." ? "alert" : "muted"}>{note}</MonoLabel> : null}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: 14-teleop ───
