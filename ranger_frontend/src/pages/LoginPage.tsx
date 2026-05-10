// ─── RANGER V3 START: login page ───
/**
 * Login form. Posts to authStore.login, which posts to /api/auth/token/.
 * On success, redirects to ?next= param or /dashboard.
 *
 * Validation:
 *  - Username: required, non-empty
 *  - Password: required, min 1 char (real strength rules are server-side
 *    via Django's AUTH_PASSWORD_VALIDATORS — frontend just enforces presence)
 *
 * Error display:
 *  - Field errors from zod show inline under each input
 *  - Server errors (401 wrong credentials, 400 bad input, network) show
 *    in a banner above the form
 */
import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useNavigate, useSearchParams, Navigate } from "react-router-dom"
import { useAuthStore } from "@/stores/authStore"

const loginSchema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
})

type LoginFormData = z.infer<typeof loginSchema>

export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const login = useAuthStore((s) => s.login)
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  // If user lands on /login while already authed, bounce them to wherever
  // they were trying to go (or /dashboard). Avoids a useless re-login.
  if (isAuthenticated) {
    const next = searchParams.get("next") || "/dashboard"
    return <Navigate to={next} replace />
  }

  const onSubmit = async (data: LoginFormData) => {
    setServerError(null)
    try {
      await login(data.username, data.password)
      const next = searchParams.get("next") || "/dashboard"
      navigate(next, { replace: true })
    } catch (err: unknown) {
      // Translate axios errors into user-facing messages.
      // We deliberately don't leak server-side specifics for 401s.
      if (typeof err === "object" && err !== null && "response" in err) {
        const response = (err as { response?: { status?: number } }).response
        if (response?.status === 401) {
          setServerError("Invalid username or password.")
          return
        }
        if (response?.status === 400) {
          setServerError("Please check your input and try again.")
          return
        }
      }
      setServerError("Could not reach the server. Please try again.")
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <header className="text-center">
          <h1 className="text-2xl font-semibold">R.A.N.G.E.R.</h1>
          <p className="text-sm text-gray-500 mt-1">Sign in to continue</p>
        </header>

        {serverError ? (
          <div
            role="alert"
            className="p-3 text-sm border border-red-300 bg-red-50 text-red-800 rounded dark:bg-red-950 dark:border-red-800 dark:text-red-200"
          >
            {serverError}
          </div>
        ) : null}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div>
            <label htmlFor="username" className="block text-sm mb-1">
              Username
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              autoFocus
              {...register("username")}
              className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {errors.username ? (
              <p className="text-xs text-red-600 mt-1">{errors.username.message}</p>
            ) : null}
          </div>

          <div>
            <label htmlFor="password" className="block text-sm mb-1">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register("password")}
              className="w-full px-3 py-2 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {errors.password ? (
              <p className="text-xs text-red-600 mt-1">{errors.password.message}</p>
            ) : null}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full py-2 text-sm font-medium bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: login page ───