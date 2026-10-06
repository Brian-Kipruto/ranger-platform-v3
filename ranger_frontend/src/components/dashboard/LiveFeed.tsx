// ─── RANGER V3 START: 09-live-console ───
/**
 * LiveFeed — owns the /ws/dashboard/ socket; renders nothing.
 *
 * Native WebSocket, not react-use-websocket: that package is CJS-only and
 * Vite's dev pre-bundle hands back the module object as its default export
 * ("useWebSocket is not a function"), while the production build resolves it
 * fine. One code path for dev and prod beats an interop workaround (TS-030).
 *
 * Auth: the access token rides in Sec-WebSocket-Protocol, never the URL
 * (ADR-0016). `token` is an effect dependency, so a refreshed token closes
 * the old socket and opens a fresh one.
 *
 * Close codes (see ros_bridge/consumers.py):
 *   4401 token rejected → no blind retry with the same token. One HTTP call
 *        lets the axios interceptor refresh; the new token reconnects us.
 *   4403 user has no org → stop. Retrying cannot fix it.
 *   other (1006 server gone, 1011 Redis gone) → reconnect, backoff ≤ 10 s.
 */
import { useEffect } from "react"
import { getMe } from "@/api/auth"
import { useLiveStore } from "@/stores/liveStore"

const SUBPROTOCOL = "ranger.v1"
const CLOSE_UNAUTHENTICATED = 4401
const CLOSE_NO_ORG = 4403
const MAX_BACKOFF_MS = 10_000

function socketUrl(): string {
  // Same origin: Vite proxies /ws in dev; nginx will in prod.
  const scheme = window.location.protocol === "https:" ? "wss" : "ws"
  return `${scheme}://${window.location.host}/ws/dashboard/`
}

export function LiveFeed({ token }: { token: string }) {
  const upsert = useLiveStore((s) => s.upsert)
  const setConnection = useLiveStore((s) => s.setConnection)

  useEffect(() => {
    let ws: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    let disposed = false

    const connect = () => {
      setConnection("connecting")
      ws = new WebSocket(socketUrl(), [SUBPROTOCOL, `jwt.${token}`])

      ws.onopen = () => {
        attempt = 0
        setConnection("open")
      }

      ws.onmessage = (e) => {
        let data: unknown
        try {
          data = JSON.parse(e.data)
        } catch {
          return
        }
        const pos = upsert(data)
        if (pos && import.meta.env.DEV) {
          // 2c latency check: browser receipt minus robot stamp.
          console.info(
            `[live] #${pos.id} ${pos.robot} ${pos.source} lag=${pos.receivedAt - Date.parse(pos.ts)}ms`
          )
        }
      }

      ws.onclose = (e) => {
        if (disposed) return
        setConnection("closed", e.code)
        if (e.code === CLOSE_UNAUTHENTICATED) {
          getMe().catch(() => {})
          return
        }
        if (e.code === CLOSE_NO_ORG) return
        retry = setTimeout(connect, Math.min(1000 * 2 ** attempt++, MAX_BACKOFF_MS))
      }
    }

    connect()
    return () => {
      disposed = true
      clearTimeout(retry)
      ws?.close(1000)
    }
  }, [token, upsert, setConnection])

  return null
}
// ─── RANGER V3 END: 09-live-console ───
