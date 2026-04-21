# Plan: Patchwright v0.1 — Scaffold + M2-M5 (M1 Deferred)

## Context

Build **Patchwright v0.1**, a Python CLI that turns natural-language musical
intent into a valid MiRack / VCV Rack 0.6 `.vcv` patch file. Full spec is in
the conversation thread and will be committed as `docs/spec.md` on day 1.

### Key v0.1 properties
- Offline only (no live MIDI, no GUI, no DAW).
- 4/4 electronic only (techno, house, dub, ambient).
- Structural validity is a hard guarantee; audibility a soft one.
- LLM = Anthropic API (Opus 4.7 for generation, Haiku 4.5 for cheap passes).
  Exact IDs: `claude-opus-4-7`, `claude-haiku-4-5-20251001`.

### Decisions locked with user
1. **Location:** new branch `patchwright/v0.1` off `main` in `something_groovy`.
2. **M1 deferred:** no MiRack export available yet, so the patch-format
   investigation is postponed. Build M2+ against an in-memory pydantic model
   with a stub emitter; swap the real `emit/patch.py` in when a real `.vcv`
   is available.
3. **Headless VCV Rack 0.6:** user will install it; keep
   `validate/headless.py` in v0.1 scope.

## Recommended Approach

Work milestone-by-milestone. Each milestone lands on its own PR-sized commit
series. Nothing merges to `main` until v0.1 success metric is met.

### Phase 0 — Repo scaffold (half day)
- Create branch `patchwright/v0.1` off `main`.
- Generate `pyproject.toml` (deps: `anthropic`, `pydantic>=2`, `networkx`,
  `click`, `pytest`).
- Create full directory layout from the spec (`patchwright/`, `corpus/`,
  `tests/`, `docs/`).
- Commit spec verbatim as `docs/spec.md`; commit this file as `docs/plan.md`.
- Add `docs/patch-format.md` as a placeholder with a `TODO(M1)` banner.
- `.gitignore` for `corpus/patchstorage/`, `__pycache__`, `.venv/`, `patches/`.

### Phase 1 — Stage 1 intent parsing (M3 prep)
- `patchwright/generate/intent.py` — pydantic `Intent`, `VoiceSpec` models.
- `patchwright/generate/prompts/intent.md` — system prompt + 2 few-shot
  examples, fenced-JSON output contract.
- Anthropic client wrapper in `patchwright/generate/client.py`. Haiku model.
- Tests: mock the API, verify parse failure path prints raw response and
  non-zero-exits.

### Phase 2 — Module catalog (M2)
- `patchwright/catalog/modules.json` — seed ~40 modules sufficient for techno:
  Clocked, Marbles, Plaits, Rings, Clouds, Plateau, Bogaudio filters/VCAs,
  Fundamental utilities, Impromptu sequencers.
- `patchwright/catalog/build_catalog.py` — script to regenerate. Data sources:
  VCV Rack 0.6 plugin source repos (Fundamental, AudibleInstruments, Bogaudio,
  Befaco, Impromptu, JW, mscHack) cross-checked against MiRack's bundled list.
- Pydantic `Module`, `Port`, `Param` models for the registry.
- Tests: load the JSON, assert schema conforms, assert signal types are in
  the closed set {`audio`, `cv`, `gate`, `trigger`, `clock`}.

### Phase 3 — Grammar + skeleton (M3, M4)
- `patchwright/grammar/roles.py` — `Clock`, `Generator`, `Voice`, `Mod`, `FX`,
  `Output` dataclasses with typed port specs (no concrete module).
- `patchwright/grammar/skeleton.py` — one `TECHNO_SKELETON` rule first.
  Rule = roles + edges with port-type constraints.
- `patchwright/grammar/expand.py` — apply the rule given an `Intent`; return a
  `networkx.DiGraph` annotated with role/port metadata.
- Pure Python, no LLM. Deterministic given seed.
- Tests: every expansion produces a graph where (a) every non-output role
  has a path to `Output`, (b) every input expecting gate/trigger has a
  compatible source.

### Phase 4 — Stage 3 module binding (M3)
- `patchwright/generate/fill.py` — take `Skeleton + Intent + filtered catalog`,
  call Opus, receive `{role_id: {plugin, model, params}}`. LLM does **not**
  emit graph structure.
- `patchwright/generate/prompts/fill.md` — prompt with schema + 3-5 few-shot
  exemplars loaded from `corpus/exemplars/`.
- Semantic catalog filter in Python: given a role's port spec, return
  ≤20 candidate modules. Don't dump the whole registry to the LLM.
- Tests: mock Opus, assert fill errors when LLM hallucinates a module not in
  the catalog.

### Phase 5 — Stub emitter (unblocks end-to-end until M1)
- `patchwright/emit/patch.py` — write a best-guess `.vcv` JSON matching the
  public VCV Rack 0.6 schema. Flag in comments/docstring that MiRack-specific
  fields are unknown until M1.
- Grid layout: topological sort left-to-right, fixed spacing.
- `corpus/exemplars/` gets 3 hand-typed example patches (pydantic, not `.vcv`)
  with annotated intents, for use as Stage 3 few-shots.

### Phase 6 — Validation (M5)
- `validate/graph.py` — all the structural checks from the spec.
- `validate/audibility.py` — audio-graph trace from Output; flag dead VCAs.
- `validate/headless.py` — shell out to `Rack -r patch.vcv`, capture WAV,
  RMS threshold. Gate behind `--headless` flag; skipped if binary missing.

### Phase 7 — CLI (M5)
- `patchwright/cli.py` — `click` group with the flags from spec: `--seed`,
  `--bpm`, `--bars`, `--polyphony`, `--dry-run`, `--explain`,
  `--validate-only`, `--headless`.
- Friendly stepwise output (`✓ parsed intent`, `✓ skeleton expanded`, ...).
- Retry loop: on validation failure, regenerate up to N=3, then error with
  diagnostics.

### Phase 8 — M4 broaden to 4 genres
- Add house, dub, ambient skeletons following the techno template.
- Expand catalog as needed (likely +10-15 modules for ambient/dub textures).
- 20-prompt smoke test across genres.

### Phase 9 — Unblock M1 (when patch available)
- User exports minimal MiRack patch (VCO → VCA → Audio) and drops it in
  `corpus/exemplars/raw/`.
- Diff it against a reference VCV Rack 0.6 patch.
- Fill in `docs/patch-format.md` with the delta.
- Update `emit/patch.py` to match; run round-trip test
  (parse → serialize → open in MiRack).

## Critical Files (to be created)

- `pyproject.toml` — deps and entry point.
- `patchwright/cli.py` — click entrypoint.
- `patchwright/generate/intent.py`, `fill.py`, `client.py`.
- `patchwright/generate/prompts/intent.md`, `fill.md`, `explain.md`.
- `patchwright/grammar/roles.py`, `skeleton.py`, `expand.py`.
- `patchwright/catalog/modules.json`, `build_catalog.py`.
- `patchwright/validate/graph.py`, `audibility.py`, `headless.py`.
- `patchwright/emit/patch.py` — stub first, real after M1.
- `corpus/exemplars/*.json` — 3 hand-curated patches + intent annotations.
- `docs/spec.md`, `docs/plan.md`, `docs/patch-format.md`.

## Open Questions Parked for Later (not blockers)

- **Anthropic structured output vs. JSON mode** — test both during Phase 4;
  pick whichever errors less on malformed cases.
- **patchstorage scraping** — deferred to v0.2. v0.1 relies on hand-curated
  exemplars only.
- **MiRack schema drift** — blocked on M1, user-supplied artifact.

## Verification

Per-phase:
- `pytest` green for every phase's unit tests.
- `ruff` / `mypy --strict` clean (set up in Phase 0).

End-to-end v0.1 acceptance (spec's success metric):
1. Run `patchwright "deep dub techno with Plaits, slow morph, long tail
   reverb, 125 bpm"` on a laptop.
2. `.vcv` file appears in `~/Patchwright/patches/`.
3. User copies to iCloud Drive → MiRack folder.
4. Patch opens in MiRack without errors.
5. Audible sound within 5 seconds of clock start.
6. Prompt → sound elapsed time <30 seconds.
7. Repeat for 20 prompts across 4 genres; all pass.

Headless CI verification (when VCV 0.6 installed):
- `Rack -r patches/<file>.vcv` for N seconds, capture WAV, assert RMS > threshold.
