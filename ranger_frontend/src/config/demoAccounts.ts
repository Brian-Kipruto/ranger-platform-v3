// ─── RANGER V3 START: demo accounts config ───
/**
 * Demo accounts for the Field Console role-demo login buttons.
 *
 * DEV ONLY. These credentials are created by the backend `seed_demo`
 * management command and are throwaway demo logins — not secrets. Each
 * button logs in for real via useAuthStore.login() against these accounts,
 * exercising the exact same auth path as the main form.
 *
 * username === email by design: simplejwt authenticates on `username`, and
 * the login form displays the email in the Operator ID field, so the thing
 * shown is the thing submitted.
 *
 * To (re)create these accounts:  python manage.py seed_demo
 */
export interface DemoAccount {
  /** short code shown on the button (OP / CL / PUB) */
  code: string
  /** role label under the code */
  label: string
  /** login username (== email) */
  username: string
  password: string
  /** semantic accent for the button's hover/border, by role */
  tone: "accent" | "ok" | "info"
}

export const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    code: "OP",
    label: "OPERATOR",
    username: "operator@byteanza.com",
    password: "RangerDemo1234!",
    tone: "accent",
  },
  {
    code: "CL",
    label: "CLIENT",
    username: "client@magadi.com",
    password: "RangerDemo1234!",
    tone: "ok",
  },
  {
    code: "PUB",
    label: "COMMUNITY",
    username: "community@public.com",
    password: "RangerDemo1234!",
    tone: "info",
  },
]
// ─── RANGER V3 END: demo accounts config ───