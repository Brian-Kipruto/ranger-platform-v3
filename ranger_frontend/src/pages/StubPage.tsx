// ─── RANGER V3 START: stub page ───
/**
 * StubPage — placeholder for nav screens not yet implemented (Mission Control,
 * Fleet, Alerts, Reports, AI, Admin, Community, Workspace). Rendered inside the
 * app shell so the nav looks complete and nothing breaks on click. Each gets
 * replaced by its real feature in a later build.
 */
import { useLocation } from "react-router-dom"
import { MonoLabel } from "@/components/console/MonoLabel"
import { Panel } from "@/components/console/Panel"
import { VIEW_META } from "@/config/navConfig"

export default function StubPage() {
  const { pathname } = useLocation()
  const meta = VIEW_META[pathname] ?? { code: "—", label: "Screen", sub: "" }

  return (
    <div className="p-[18px]">
      <Panel title={`${meta.code} · ${meta.label}`} right={<MonoLabel size="xs" tone="warn">NOT BUILT</MonoLabel>}>
        <div className="px-[18px] py-[60px] flex flex-col items-center justify-center text-center gap-3">
          <div
            className="w-12 h-12 rounded-lg border flex items-center justify-center font-mono text-[15px] font-semibold"
            style={{ borderColor: "var(--accent)", color: "var(--accent)", boxShadow: "inset 0 0 14px var(--accent-weak)" }}
          >
            {meta.code}
          </div>
          <MonoLabel size="md" tone="soft" tracking="0.13em">
            {meta.label}
          </MonoLabel>
          <p className="font-mono text-[11px] text-fg-faint max-w-[360px] leading-[1.7]">
            This screen isn't built yet. It ships in a later feature of the V3
            roadmap. The navigation and shell are in place so it's ready to drop in.
          </p>
        </div>
      </Panel>
    </div>
  )
}
// ─── RANGER V3 END: stub page ───