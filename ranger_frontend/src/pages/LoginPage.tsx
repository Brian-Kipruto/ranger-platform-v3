// ─── RANGER V3 START: login page (Field Console retrofit) ───
/**
 * Login — Field Console "Secure Access" rebuild.
 *
 * This is a presentation rebuild over UNCHANGED auth logic. The markup now
 * matches the RANGER V3 Field Console mockup (radar-ring identity panel +
 * Secure Access card, corner ticks, footer telemetry strip), but everything
 * underneath is the same as the Feature 02 login:
 *   - useAuthStore.login(username, password)
 *   - ?next= redirect, isAuthenticated bounce
 *   - react-hook-form + zod validation
 *   - server-error banner (401 → invalid creds, 400 → bad input, else network)
 *
 * What's real vs. chrome:
 *   - Operator ID  → REAL username input (the mockup's static email display)
 *   - Passphrase   → REAL password input (the mockup's static dots)
 *   - AUTHENTICATE → submits the form
 *   - Role-demo buttons → REAL logins via seeded accounts (config/demoAccounts)
 *   - 2FA TOTP tiles → STATIC visual chrome (no logic; wired in a future 2FA feature)
 *   - Radar rings   → static decoration
 */
import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useNavigate, useSearchParams, Navigate } from "react-router-dom"
import { useAuthStore } from "@/stores/authStore"
import { MonoLabel } from "@/components/console/MonoLabel"
import { StatusDot } from "@/components/console/StatusDot"
import { CornerTicks } from "@/components/console/CornerTicks"
import { DEMO_ACCOUNTS, type DemoAccount } from "@/config/demoAccounts"
import byteanzaLogo from "@/assets/byteanza-logo.svg"

const loginSchema = z.object({
  username: z.string().min(1, "Operator ID is required"),
  password: z.string().min(1, "Passphrase is required"),
})

type LoginFormData = z.infer<typeof loginSchema>

// Static TOTP tile display (visual chrome only — no 2FA logic yet).
const TOTP_TILES = ["4", "1", "8", "2", "_", "_"]

export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const login = useAuthStore((s) => s.login)
  const [serverError, setServerError] = useState<string | null>(null)
  const [demoPending, setDemoPending] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  // Already authed → bounce to ?next= (or /dashboard).
  if (isAuthenticated) {
    const next = searchParams.get("next") || "/dashboard"
    return <Navigate to={next} replace />
  }

  const redirectNext = () => {
    const next = searchParams.get("next") || "/dashboard"
    navigate(next, { replace: true })
  }

  // Translate axios errors into user-facing banner text. Shared by the form
  // submit and the demo-button logins.
  const toBannerMessage = (err: unknown): string => {
    if (typeof err === "object" && err !== null && "response" in err) {
      const response = (err as { response?: { status?: number } }).response
      if (response?.status === 401) return "Invalid Operator ID or passphrase."
      if (response?.status === 400) return "Please check your input and try again."
    }
    return "Could not reach the server. Please try again."
  }

  const onSubmit = async (data: LoginFormData) => {
    setServerError(null)
    try {
      await login(data.username, data.password)
      redirectNext()
    } catch (err: unknown) {
      setServerError(toBannerMessage(err))
    }
  }

  const onDemoLogin = async (acct: DemoAccount) => {
    setServerError(null)
    setDemoPending(acct.code)
    try {
      await login(acct.username, acct.password)
      redirectNext()
    } catch (err: unknown) {
      setServerError(toBannerMessage(err))
      setDemoPending(null)
    }
  }

  const toneBorderHover: Record<DemoAccount["tone"], string> = {
    accent: "hover:border-[var(--accent)]",
    ok: "hover:border-ok",
    info: "hover:border-info",
  }
  const toneText: Record<DemoAccount["tone"], string> = {
    accent: "text-[var(--accent)]",
    ok: "text-ok",
    info: "text-info",
  }

  return (
    <div
      className="fixed inset-0 flex items-center justify-center overflow-hidden"
      style={{
        background:
          "radial-gradient(1200px 700px at 78% 18%, var(--accent-faint), transparent 60%), var(--color-surface-0)",
      }}
    >
      {/* graticule */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)",
          backgroundSize: "46px 46px",
        }}
      />

      {/* radar rings (static decoration) */}
      <div
        className="absolute rounded-full"
        style={{ top: 64, right: 90, width: 340, height: 340, border: "1px solid color-mix(in srgb, var(--accent) 16%, transparent)" }}
      />
      <div
        className="absolute rounded-full"
        style={{ top: 114, right: 140, width: 240, height: 240, border: "1px solid color-mix(in srgb, var(--accent) 12%, transparent)" }}
      />
      <div
        className="absolute rounded-full"
        style={{ top: 164, right: 190, width: 140, height: 140, border: "1px solid color-mix(in srgb, var(--accent) 10%, transparent)" }}
      />
      <div
        className="absolute"
        style={{
          top: 234,
          right: 259,
          width: 1,
          height: 1,
          boxShadow: "0 0 0 3px var(--accent), 0 0 22px 5px color-mix(in srgb, var(--accent) 70%, transparent)",
        }}
      />

      <CornerTicks />

      {/* brand mark — top-left corner */}
      <img
        src={byteanzaLogo}
        alt="ByteAnza"
        className="absolute top-[40px] left-[54px] h-[100px] w-auto select-none opacity-95"
        draggable={false}
      />

      <div
        className="relative grid items-center"
        style={{ gridTemplateColumns: "1.15fr 0.85fr", gap: 64, width: "min(1080px, 90vw)" }}
      >
        {/* ── LEFT: identity ── */}
        <div>
          <div className="flex items-center gap-2.5">
            <StatusDot status="ok" pulse size={7} />
            <MonoLabel size="md" tone="muted" tracking="0.18em">
              BYTEANZA · FIELD INTELLIGENCE PLATFORM
            </MonoLabel>
          </div>

          <div
            className="mt-[22px] font-bold flex items-baseline gap-1.5 text-fg-bright"
            style={{ fontSize: 84, lineHeight: 0.94, letterSpacing: "-0.03em" }}
          >
            R.A.N.G.E.R.
            <span
              className="inline-block animate-rng-blink"
              style={{ width: 34, height: 64, background: "var(--accent)", boxShadow: "0 0 26px color-mix(in srgb, var(--accent) 60%, transparent)" }}
            />
          </div>

          <MonoLabel size="md" tone="dim" tracking="0.14em" className="block mt-[18px] max-w-[520px] leading-[1.7] normal-case">
            <span className="uppercase">
              Robotic Autonomous Navigator for
              <br />
              Geospatial Environmental Reconnaissance
            </span>
          </MonoLabel>

          <div className="mt-[30px] flex gap-2.5 items-center">
            <span className="font-mono text-[11px] tracking-[0.16em] text-fg-soft border border-border-strong-2 px-3 py-[7px] rounded">
              V3 · FIELD CONSOLE
            </span>
            <span className="font-mono text-[11px] tracking-[0.16em] text-fg-dim border border-border-strong-2 px-3 py-[7px] rounded">
              ROS 2 HUMBLE
            </span>
            <span className="font-mono text-[11px] tracking-[0.16em] text-fg-dim border border-border-strong-2 px-3 py-[7px] rounded">
              RaaS
            </span>
          </div>
        </div>

        {/* ── RIGHT: secure access card ── */}
        <div
          className="rounded-[10px] overflow-hidden border border-border"
          style={{ background: "linear-gradient(180deg, #13161c, #0f1217)", boxShadow: "0 30px 80px -30px rgba(0,0,0,0.8)" }}
        >
          <div
            className="flex items-center justify-between px-4 py-[13px] border-b border-border"
            style={{ background: "var(--accent-faint)" }}
          >
            <MonoLabel size="md" tone="soft" tracking="0.16em">
              SECURE ACCESS
            </MonoLabel>
            <span className="font-mono text-[10px] tracking-[0.14em] text-ok flex items-center gap-1.5">
              <StatusDot status="ok" size={6} />
              mTLS · TLS 1.3
            </span>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="px-5 pt-[22px] pb-5" noValidate>
            {serverError ? (
              <div
                role="alert"
                className="mb-4 px-3 py-2.5 rounded border border-alert/40 text-[12px] font-mono text-alert"
                style={{ background: "color-mix(in srgb, var(--color-alert) 10%, transparent)" }}
              >
                {serverError}
              </div>
            ) : null}

            {/* Operator ID */}
            <MonoLabel size="sm" tone="dim" tracking="0.16em">
              Operator ID
            </MonoLabel>
            <div className="mt-[7px] flex items-center gap-2.5 bg-surface-input border border-border-strong rounded-md px-3 py-[11px] focus-within:border-[var(--accent)] transition-colors">
              <StatusDot status="accent" size={6} />
              <input
                type="text"
                autoComplete="username"
                autoFocus
                placeholder="operator@byteanza.com"
                {...register("username")}
                className="flex-1 bg-transparent border-none outline-none font-mono text-[13px] text-fg placeholder:text-fg-faint"
              />
            </div>
            {errors.username ? (
              <p className="mt-1 font-mono text-[10px] text-alert">{errors.username.message}</p>
            ) : null}

            {/* Passphrase */}
            <div className="mt-[15px]">
              <MonoLabel size="sm" tone="dim" tracking="0.16em">
                Passphrase
              </MonoLabel>
            </div>
            <div className="mt-[7px] flex items-center gap-2 bg-surface-input border border-border-strong rounded-md px-3 py-[11px] focus-within:border-[var(--accent)] transition-colors">
              <input
                type="password"
                autoComplete="current-password"
                placeholder="••••••••••••"
                {...register("password")}
                className="flex-1 bg-transparent border-none outline-none font-mono text-[14px] tracking-[0.2em] text-fg-soft placeholder:text-fg-faint placeholder:tracking-[0.3em]"
              />
            </div>
            {errors.password ? (
              <p className="mt-1 font-mono text-[10px] text-alert">{errors.password.message}</p>
            ) : null}

            {/* 2FA TOTP — static visual chrome (no logic yet) */}
            <div className="mt-[15px] flex items-center justify-between">
              <MonoLabel size="sm" tone="dim" tracking="0.16em">
                2FA · TOTP
              </MonoLabel>
              <span className="font-mono text-[10px] text-fg-faint">GOOGLE AUTH</span>
            </div>
            <div className="mt-2 flex gap-[7px]" aria-hidden="true">
              {TOTP_TILES.map((d, i) => {
                const active = i === 3
                const filled = d !== "_"
                return (
                  <div
                    key={i}
                    className="flex-1 text-center bg-surface-input border rounded-[5px] py-[9px] font-mono text-[16px]"
                    style={{
                      borderColor: active ? "var(--accent)" : "var(--color-border-strong)",
                      color: active ? "var(--accent)" : filled ? "var(--color-fg)" : "var(--color-fg-faint)",
                    }}
                  >
                    {d}
                  </div>
                )
              })}
            </div>

            {/* AUTHENTICATE */}
            <button
              type="submit"
              disabled={isSubmitting || demoPending !== null}
              className="mt-5 w-full border-none cursor-pointer text-white font-mono text-[12px] tracking-[0.16em] py-3.5 rounded-md flex items-center justify-center gap-2.5 disabled:opacity-60 disabled:cursor-not-allowed transition-opacity"
              style={{ background: "var(--accent)", boxShadow: "0 8px 24px -8px color-mix(in srgb, var(--accent) 80%, transparent)" }}
            >
              {isSubmitting ? "AUTHENTICATING…" : "AUTHENTICATE"}
              <span className="text-[14px]">→</span>
            </button>

            {/* divider */}
            <div className="mt-[18px] flex items-center gap-2.5">
              <div className="flex-1 h-px bg-border" />
              <MonoLabel size="xs" tone="faint" tracking="0.16em">
                OR ENTER DEMO AS
              </MonoLabel>
              <div className="flex-1 h-px bg-border" />
            </div>

            {/* role-demo buttons — REAL logins */}
            <div className="mt-[13px] grid grid-cols-3 gap-2">
              {DEMO_ACCOUNTS.map((acct) => (
                <button
                  key={acct.code}
                  type="button"
                  onClick={() => onDemoLogin(acct)}
                  disabled={isSubmitting || demoPending !== null}
                  className={`cursor-pointer bg-surface-3 border border-border-strong rounded-md px-1.5 py-[11px] text-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${toneBorderHover[acct.tone]}`}
                >
                  <div className={`font-mono text-[13px] font-semibold ${toneText[acct.tone]}`}>
                    {demoPending === acct.code ? "…" : acct.code}
                  </div>
                  <div className="font-mono text-[8.5px] tracking-[0.08em] text-fg-muted mt-1">
                    {acct.label}
                  </div>
                </button>
              ))}
            </div>
          </form>
        </div>
      </div>

      {/* footer telemetry strip */}
      <div className="absolute bottom-[30px] left-0 right-0 flex items-center justify-center gap-6 font-mono text-[10px] tracking-[0.1em] text-fg-faint">
        <span>LAT -1.8901° · LON 36.2731° · MAGADI, KE</span>
        <span className="text-border-strong-2">|</span>
        <span>BUILD 3.0.0-rc4 · a7f2e9c</span>
        <span className="text-border-strong-2">|</span>
        <span className="text-ok">● ENCRYPTED</span>
        <span className="text-border-strong-2">|</span>
        <span>© 2026 BYTEANZA LTD</span>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: login page (Field Console retrofit) ───