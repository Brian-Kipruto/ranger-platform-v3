// ─── RANGER V3 START: home page (placeholder) ───
export default function HomePage() {
  return (
    <div className="p-8 max-w-3xl mx-auto">
      <h1 className="text-4xl font-bold text-sky-400">R.A.N.G.E.R. Platform V3</h1>
      <p className="mt-3 text-slate-400 text-lg">
        Robot-as-a-Service platform for autonomous environmental reconnaissance.
      </p>
      <div className="mt-8 p-6 rounded-lg bg-slate-800 border border-slate-700">
        <h2 className="text-xl font-semibold text-slate-200">Phase 1 — Foundation Scaffold</h2>
        <ul className="mt-3 space-y-1 text-sm text-slate-400">
          <li>✅ Django backend with split settings, 13 apps, custom user model</li>
          <li>✅ PostgreSQL 16 + Redis 7 in Docker</li>
          <li>✅ React 19 + TypeScript + Vite + Tailwind v4</li>
          <li>⏳ Auth feature — next</li>
        </ul>
      </div>
      <p className="mt-6 text-xs text-slate-500">
        Backend health check: <code className="bg-slate-800 px-2 py-1 rounded">GET /api/</code>
      </p>
    </div>
  )
}
// ─── RANGER V3 END: home page (placeholder) ───