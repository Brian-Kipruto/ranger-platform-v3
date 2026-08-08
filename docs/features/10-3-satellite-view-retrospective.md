# F10.3 — Retrospective

*Date: 2026-08-07*

---

## What worked

**Doing CP0 before any satellite UI.** The handoff called the provenance gap
"the highest-priority item in the epic" and it was right, but the reason only
became clear while building it: every later checkpoint inherited the discipline.
The layer captions, the CATALOGED relabelling, the "colour is relative to this
scene" line, the empty-track message — none of those were planned. They came
from having spent CP0 asking *what does this actually claim* about every number
on screen.

**Keying the layer registry on `(dataset, layer)`.** This corrected the F10.2
handoff, which recorded NDVI as "correct from raw DN — the scale factor cancels
in a normalised ratio". True of Sentinel-2; false of Landsat, whose Collection 2
calibration carries an additive offset that survives in the denominator. The
resulting image is not wrong in any visible way — it is a plausible number in
the right range over a 38×41 px scene. Nothing downstream could have caught it,
and no amount of care at the call site would have helped, because the call site
is where the mistake is made. Putting the difference in the *type* — a
`Calibration` that carries scale and offset together — is what made it
impossible to forget.

**The registry-wide test.** Any layer setting `apply_calibration=False` must
either be a display stretch or have a calibration that provably cancels. That
one assertion protects every layer not yet written, which is more than the
specific L9 regression test does.

**Extracting the paint expressions to module scope.** `trackColorExpression`
is consumed by the add path and the refresh path. Two call sites that must not
drift, with one definition — and the refresh path only exists because
idempotence turned out to be insufficient: the add-guards prevent re-adding but
never update a layer whose paint props changed.

**Fixing `installLayers`'s closure in CP0, before it bit.** It was harmless
while only `accent` varied. By CP4 the installer read the active layer, the
image id and the opacity, all changing constantly, and `styledata` fires on
every basemap switch. Fixing it early cost ten lines; retrofitting it after four
layers existed would have been ugly and the symptom — "the raster reverts when
I change basemap" — would have looked like a MapLibre quirk.

**Sidecar files that prove execution.** The JSON sidecar was added so the legend
survives a cache hit. It ended up diagnosing 020: a missing sidecar meant
`render_png` had never run, which ruled out the renderer in one `ls`. Cheap
side effects that prove a code path executed are worth more than they look.

---

## What went wrong

**The same bug three times: a count describing a set it did not count.**

1. The provenance banner counted `trackFc.features`, capped at 5,000, and
   announced it as the total beside a record count of 12,081.
2. `getImages` returned a pagination envelope typed as an array; unwrapping to
   `.results` alone would have made the KPI tiles count page one.
3. SITES COVERED counted distinct queries, showing 2 when both retrievals were
   over Forole.

Three different mechanisms — a point cap, a page size, a wrong key — and one
failure. None was caught by a test; all three were caught by looking at a
screen and doing arithmetic against a number printed elsewhere on it. The
lesson is not "be careful with counts" but that a figure labelled as a total
needs its denominator checked against something independent, every time.

**A `.distinct()` chained onto an ordered queryset.** 1,819 Forole points
sharing one citation came back as 1,819 distinct citations, and the banner read
`12+ distinct citations` where it should have quoted Table 3.1. Django adds the
ordering column to the SELECT for DISTINCT, so every row differs by timestamp.

The test that should have caught it used two rows with two different notes —
where the correct and incorrect answers are both 2. The replacement uses eight
rows and one note. **A test whose right and wrong answers coincide on the
fixture is not a test.**

**`max-age=3600` made a code change invisible for an hour** (020). No error, no
log line, no failed request. And the standard remedy genuinely does not apply:
`Ctrl+Shift+R` covers the document and the subresources the reload fetches, not
an XHR fired later by JS on a layer click. Every piece of evidence pointed at
the renderer, which was the only thing that had just changed and was in fact
correct.

**Misreading `is_verified` off a field name.** I asserted the database had
drifted; the database was right and my model of it was not. `check_gee` proves
a collection ID resolves and *deliberately* does not set the flag — it means a
scene landed. The name invites the misreading, and I made it despite having the
handoff in front of me. Renaming to `has_retrieved_scene` isn't worth the churn
now, but it should happen.

**Four of my own test bugs**, in order of how much they cost: a marker string
with three box-drawing characters where the file used two, so a `.replace` for
six tests silently no-oped and only a test-count check caught it; `float()` on
a size-1 ndarray, which numpy 2.x refuses; a band-order test comparing two
rendered files, which cannot work because the fixture fills each band from its
position; and an ETag test asking a two-band fixture for a three-band layer.
Two of the four would have *failed while the code was correct* — the more
dangerous direction is the other one, and it is worth remembering that a green
suite proves nothing about tests that were never inserted.

---

## What we would do differently

**Assert on every string replacement.** Three separate incidents in this feature
came from a silent no-op or a mis-targeted paste. `assert s.count(old) == 1`
before every replace, and a test-count arithmetic check after every test-file
change.

**One file per folder when handing files over.** Downloads strip extensions, and
two files named `views.py` — one for `core`, one for `satellite_integration` —
crossed once and took the entire test suite from 277 to 199. `head -1` on a
file whose first line is its own marker settles it in one command, and that
check now belongs in every placement step.

**Reach for `no-cache` + ETag by default** on any authenticated regenerable
artefact. The bandwidth argument for `max-age` is worth almost nothing — a 304
is a few hundred bytes — and the cost is a bug class that hides itself.

---

## Carry-forwards

**New in this feature:**

- `/api/robots/` and `/api/missions/` — the real fix for the Data Explorer's
  dropdown fetch. Two deprecated wrappers in `dataLogs.ts` go when they land.
- `SOURCE_META` (TS) mirrors `SensorLog.Source` (Python) with nothing binding
  them. `LAYERS_BY_DATASET` mirrors `render.LAYERS` the same way. A tier or
  layer added on one side is silently missing on the other.
- Rename `SatelliteDataset.is_verified` → `has_retrieved_scene`.
- The render path holds no lock, so two concurrent requests for an uncached
  layer both render. Harmless (atomic replace, identical output), wasteful.
- `test_api.py` still defines local copies of `s2`, `make_scene` and
  `other_client` that shadow the conftest versions. Delete when next in there.
- `seed_marsabit`'s `--append` exists but nothing uses it; keep or drop at F10.5.

**Still open from F10.2:**

- **Chumvi has no coordinates.** Blocks CP5. The `bsi` layer is built and
  waiting.
- GEE noncommercial registration vs the F10.5 business model.
- KNRA data authorization — the report PDF is deliberately not committed.
- Lab results have no schema home — 16 soil + 4 water rows.
- `Mission.robot` is non-null, so a satellite-only AOI cannot carry a mission.
  No longer theoretical: CP4.2's empty-track path exists specifically for it.
- Two queries can claim the same COG; the second silently invalidates the
  first's metadata — and now its render cache too.
- No drift check between the database and the `DATASETS` spec.
- ADR-0007 (no route guards) — first real enforcement in F10.5.
- ADR-0009 (demo login buttons) must be stripped before public deployment.
- Duplicate demo users: `knra.demo` was created by hand and still exists
  alongside the seeded `operator@knra.go.ke`. Delete before the pitch.
- TimescaleDB deferred, not rejected.

---

## The number that matters

Twelve days out, the console showed 12,081 modelled points with real instrument
names and real dose values, and nothing said they were modelled.

Today the same screen states the tier on every row, colours every marker by it,
banners the whole filtered set, cites Table 3.1 with the site's own `n` and
mean, and — on the satellite screen — draws those points over an NDVI layer
whose legend says the colour is relative to that one scene and not comparable
across dates.

That is the pitch. Not that the imagery is pretty, but that every number on
screen can say where it came from.
