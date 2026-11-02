// ─── RANGER V3 START: 14-teleop ───
/**
 * Teleop helpers for DrivePanel (F14 5a). Pure, no React.
 *
 * Commands are NORMALISED (ros_bridge/teleop.py): lin and ang in [-1, 1] of the
 * robot's speed cap, +ang turns left (REP-103). uno_bridge maps them to PWM.
 */

export const DRIVE_KEYS: Record<string, "fwd" | "back" | "left" | "right"> = {
  w: "fwd", ArrowUp: "fwd",
  s: "back", ArrowDown: "back",
  a: "left", ArrowLeft: "left",
  d: "right", ArrowRight: "right",
}

export type Dir = "fwd" | "back" | "left" | "right"

/** Turning while moving is softened so forward+left is an arc, not a pivot. */
export const ARC_TURN = 0.5

const round2 = (v: number) => Math.round(v * 100) / 100
const clamp1 = (v: number) => Math.max(-1, Math.min(1, v))

export function commandFrom(held: ReadonlySet<Dir>, speed: number): { lin: number; ang: number } {
  const s = clamp1(Math.abs(speed))
  const lin = (held.has("fwd") ? 1 : 0) - (held.has("back") ? 1 : 0)
  const turn = (held.has("left") ? 1 : 0) - (held.has("right") ? 1 : 0)
  const ang = lin === 0 ? turn : turn * ARC_TURN
  return { lin: round2(clamp1(lin * s)), ang: round2(clamp1(ang * s)) }
}

export const isZero = (c: { lin: number; ang: number }) => c.lin === 0 && c.ang === 0

/** ros_bridge/teleop_consumer.py close codes, as the operator should read them. */
export const CLOSE_TEXT: Record<number, string> = {
  4401: "Session expired. Sign in again, then arm.",
  4403: "Your account has no organization.",
  4404: "That robot is not in your organization.",
  4405: "This account is not authorized to drive.", // 18-polish: no group name
  4409: "Someone else is driving this robot.",
  1006: "Server unreachable.",
}

export const ERROR_TEXT: Record<string, string> = {
  // 18-polish: the command name is a dev hint; the user sees the state.
  relay_offline: import.meta.env.DEV ? "Relay not running: start teleop_relay." : "Drive link to the robot is offline.",
  rate: "Sending too fast: commands dropped.",
  value: "Command rejected (out of range).",
  bad_message: "Command rejected (malformed).",
}

export function teleopUrl(robotId: string): string {
  // Same origin: Vite proxies /ws in dev; nginx will in prod (as LiveFeed).
  const scheme = window.location.protocol === "https:" ? "wss" : "ws"
  return `${scheme}://${window.location.host}/ws/teleop/${encodeURIComponent(robotId)}/`
}
// ─── RANGER V3 END: 14-teleop ───
