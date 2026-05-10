// ─── RANGER V3 START: protected route ───
/**
 * Wraps protected pages. Behavior:
 *  - While auth store is hydrating: render nothing (caller can pass a
 *    fallback if needed). Avoids the "flash of unauthenticated" where
 *    the user briefly sees /login before silent refresh resolves.
 *  - If unauthenticated after hydration: redirect to /login?next=<current>
 *    so post-login lands them where they tried to go.
 *  - If authenticated: render children.
 *
 * NOTE: This checkpoint only checks isAuthenticated. Permission-gating
 * (requiredPermission prop) is deferred to whenever a feature actually
 * needs it — currently no route does.
 */
import type { ReactNode } from "react"
import { Navigate, useLocation } from "react-router-dom"
import { useAuthStore } from "@/stores/authStore"

interface ProtectedRouteProps {
  children: ReactNode
  /** Optional element to render while hydrating. Defaults to nothing. */
  fallback?: ReactNode
}

export default function ProtectedRoute({
  children,
  fallback = null,
}: ProtectedRouteProps) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const isHydrating = useAuthStore((s) => s.isHydrating)
  const location = useLocation()

  if (isHydrating) {
    return <>{fallback}</>
  }

  if (!isAuthenticated) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  return <>{children}</>
}
// ─── RANGER V3 END: protected route ───