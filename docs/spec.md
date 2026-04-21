# Patchwright v0.1 — Spec Sheet

A CLI tool that turns natural-language musical intent into a valid MiRack / VCV Rack 0.6 patch file.

This is the **v0.1 scope**: offline generation only, single-genre focus (techno / house), deterministic validation before emission. No real-time control. No DAW integration. The live MIDI-CC agent ("Conductor") is a separate project.

-----

## Goals

1. Accept a natural-language prompt describing a patch (voice, vibe, constraints).
1. Emit a `.vcv` file that opens cleanly in MiRack on iOS and in VCV Rack 0.6 on desktop.
1. Guarantee structural validity: no dangling cables, no port-type mismatches, no missing modules, no zero-output patches.
1. Produce patches that are *playable* — i.e. actually emit sound at sensible levels when the clock is running — not just syntactically valid.

## Non-goals (v0.1)

- No GUI. CLI only.
- No live control / MIDI streaming.
- No training of custom models. Use a frontier LLM (Claude via Anthropic API) for generation.
- No attempt to emulate proprietary modules that aren't in the MiRack bundled set.
- No iOS app. Output is a file on disk; user syncs via iCloud Drive manually.
- No arbitrary genre. Scope v0.1 to 4/4 electronic (techno, house, dub, ambient). Broader genres are v0.2.

-----

## Stack

- **Language:** Python 3.11+
- **LLM:** Anthropic API, `claude-opus-4-7` for generation, `claude-haiku-4-5` for cheap validation passes
- **Patch validation:** headless VCV Rack 0.6 (desktop), invoked as a subprocess for final integration test. Structural validation done in-process with a typed graph model.
- **Dependencies:** `anthropic`, `pydantic`, `networkx`, `click` (CLI), `pytest`
- **No web server** in v0.1. Just a CLI.

## Repo layout

```
patchwright/
├── pyproject.toml
├── README.md
├── patchwright/
│   ├── __init__.py
│   ├── cli.py                    # click entrypoint
│   ├── catalog/
│   │   ├── __init__.py
│   │   ├── modules.json          # module registry (see §Data model)
│   │   └── build_catalog.py      # script to regenerate from reference patches
│   ├── grammar/
│   │   ├── __init__.py
│   │   ├── roles.py              # role types: Clock, Generator, Voice, Mod, FX, Output
│   │   ├── skeleton.py           # skeleton templates per genre
│   │   └── expand.py             # skeleton → concrete module picks
│   ├── generate/
│   │   ├── __init__.py
│   │   ├── intent.py             # prompt → structured intent
│   │   ├── fill.py               # LLM call to fill parameters and wire
│   │   └── prompts/              # system prompts as .md files
│   ├── validate/
│   │   ├── __init__.py
│   │   ├── graph.py              # connectivity / type / orphan checks
│   │   ├── audibility.py         # does the graph terminate at an Audio output?
│   │   └── headless.py           # optional VCV Rack subprocess integration test
│   └── emit/
│       ├── __init__.py
│       └── patch.py              # pydantic models → .vcv JSON
├── corpus/
│   ├── patchstorage/             # scraped reference patches (gitignored)
│   └── exemplars/                # 10-20 hand-curated known-good patches
└── tests/
```

-----

## Data model

### 1. Patch schema

MiRack opens VCV Rack 0.6 patch files. Before writing anything, **Claude Code must inspect at least three real patches** (one hand-made in MiRack, one from patchstorage, one from desktop VCV Rack 0.6) to confirm the exact schema. The approximate shape is:

```json
{
  "version": "0.6.x",
  "modules": [
    {
      "id": 1,
      "plugin": "Fundamental",
      "model": "VCO",
      "pos": [0, 0],
      "params": [{"paramId": 0, "value": 0.0}, ...],
      "data": { ... }
    }
  ],
  "wires": [
    {
      "outputModuleId": 1, "outputId": 0,
      "inputModuleId": 2, "inputId": 0,
      "color": "#ffcc00"
    }
  ]
}
```

**Day 1 task:** export a minimal patch from MiRack (e.g. VCO → VCA → Audio), open it as text, diff against the VCV Rack 0.6 schema, and write down any MiRack-specific fields in `docs/patch-format.md`. Do not proceed until this is done.

### 2. Module registry (`catalog/modules.json`)

Each module gets an entry:

```json
{
  "plugin": "AudibleInstruments",
  "model": "Plaits",
  "semantic_tags": ["voice", "oscillator", "macro"],
  "inputs": [
    {"id": 0, "name": "V/OCT", "signal": "cv", "poly": true},
    {"id": 1, "name": "TRIG", "signal": "gate", "poly": true},
    {"id": 2, "name": "MODEL", "signal": "cv", "poly": false}
  ],
  "outputs": [
    {"id": 0, "name": "OUT", "signal": "audio", "poly": true},
    {"id": 1, "name": "AUX", "signal": "audio", "poly": true}
  ],
  "params": [
    {"id": 0, "name": "FREQ", "min": -4, "max": 4, "default": 0, "unit": "v_oct"},
    {"id": 1, "name": "MORPH", "min": 0, "max": 1, "default": 0.5}
  ],
  "notes": "Mutable Instruments Plaits clone. Model CV selects engine."
}
```

**Signal types:** `audio`, `cv`, `gate`, `trigger`, `clock`. Grammar refuses to wire incompatible types (e.g. audio → gate input is a warning, not a hard error — analog modular allows it — but `cv` and `audio` are treated as interchangeable at the rail level).

**How to build the catalog:** scrape module metadata from VCV Rack 0.6 source plugins (Fundamental, Audible Instruments, Bogaudio, Befaco, Impromptu, JW, mscHack) and cross-check against MiRack's bundled pack list (documented on the MiRack website and in-app module browser). Start with ~60 modules covering the cores. Don't try to enumerate everything.

-----

## Generation pipeline

Three stages. Each stage has typed input/output. No stage writes raw JSON directly; they build pydantic models that get serialized at the end.

### Stage 1: Intent parsing

**Input:** user prompt (free text) + optional flags (`--bpm`, `--bars`, `--polyphony`, `--seed`).

**Output:** a structured `Intent` object:

```python
class Intent(BaseModel):
    genre: Literal["techno", "house", "dub", "ambient"]
    bpm: int = 128
    energy: Literal["low", "medium", "high"] = "medium"
    voices: list[VoiceSpec]   # what sound sources
    modulation: list[str]     # "slow morph", "LFO on filter", "random S&H"
    fx: list[str]             # "tape delay", "reverb", "bitcrush"
    constraints: list[str]    # "no more than 12 modules", "polyphonic"
```

LLM call with a small, focused system prompt. Cheap model (Haiku) is fine. Output must parse into the schema or the CLI errors out and prints the raw response for debugging.

### Stage 2: Skeleton expansion (graph grammar)

**Input:** `Intent`.

**Output:** a `Skeleton` — a directed graph where nodes are *roles*, not modules:

```
Clock → Sequencer ─┬─→ Voice₁ ─┐
                   │            ├─→ Mixer → FX Chain → Audio Out
                   └─→ Voice₂ ─┘
       Modulator₁ ──→ (Voice₁.MORPH, Voice₂.CUTOFF)
```

The grammar is a set of rewriting rules that expand a genre template into a skeleton consistent with the intent. Rules live in `grammar/skeleton.py`:

```python
TECHNO_SKELETON = Rule(
    roles=[Clock(), Sequencer(steps=16), Voice(type="kick"),
           Voice(type="lead"), Modulator(rate="slow"),
           FXChain(["filter", "delay", "reverb"]), Output()],
    edges=[...]
)
```

Roles carry *typed port specs* but no concrete module. Stage 2 output is validated before moving on: every non-output role must have a path to Output; every input that expects gate/trigger must have a source that can emit one; etc. This is where the topology correctness guarantees come from — pure graph reasoning, no LLM.

### Stage 3: Module binding and parameter fill

**Input:** `Skeleton` + `Intent`.

**Output:** a concrete `Patch` — each role bound to a specific module from the catalog, with all params set and all wires concrete.

This is the LLM-heavy stage. Opus call with:

- The skeleton (as JSON)
- The intent (as JSON)
- The module catalog (filtered to modules tagged compatible with each role)
- 3-5 few-shot exemplar patches from `corpus/exemplars/` (hand-curated, one per genre)
- A strict output schema requesting `{"role_id": {"plugin": ..., "model": ..., "params": {...}}}` bindings only

The LLM does **not** output graph structure — only module choices and parameter values for pre-existing roles and edges. This constraint is what keeps generation reliable. Graph structure is the grammar's job.

After the LLM returns, `emit/patch.py` assembles the final JSON, positions modules on a grid (simple left-to-right topological sort), and writes the `.vcv` file.

-----

## Validation

Runs after Stage 3, before file write. Patch fails validation → regenerate (up to N=3 attempts) → error out with diagnostics.

### Structural checks (`validate/graph.py`)

- Every declared wire references real modules and real port IDs.
- No port has more than one cable into it (VCV inputs are single-source).
- No orphaned modules (every module has at least one connected input or output).
- Clock signal reaches every module that expects a clock.
- At least one wire terminates at an Audio Output module.

### Audibility check (`validate/audibility.py`)

- Trace the audio graph from output backwards. Ensure at least one Voice role reaches output through a live VCA (i.e. VCA has a non-zero CV source or a patched envelope).
- Flag silent patches before the user ever hears them.

### Headless integration (`validate/headless.py`, optional in CI)

- Shell out to desktop VCV Rack 0.6 in headless mode: `Rack -r patch.vcv` for N seconds, capture audio to WAV, check RMS > threshold.
- Skip in day-to-day dev if VCV isn't installed; run in CI.

-----

## CLI

```
$ patchwright "deep dub techno with Plaits, slow morph, long tail reverb, 125 bpm"
✓ parsed intent (techno, 125 bpm, medium energy)
✓ skeleton expanded (7 roles, 11 edges)
✓ modules bound (Plaits, Clouds, Clocked, Marbles, Plateau, ...)
✓ structural validation passed
✓ audibility check passed
  → wrote patches/2026-04-21_deep-dub-techno.vcv

$ patchwright --seed 42 --dry-run "acid house bassline"
[prints the patch structure without writing]

$ patchwright --explain patches/2026-04-21_deep-dub-techno.vcv
[prints a performance recipe: "start with MORPH at 0.3, slowly open filter over 32 bars..."]
```

Flags:

- `--seed N` — deterministic generation (pass through to LLM via `metadata`; separately seed Python RNG for grammar choices)
- `--bpm N`, `--bars N`, `--polyphony N`
- `--dry-run` — don't write file, print graph
- `--explain PATCH` — second LLM call that generates human-readable performance notes for an existing patch
- `--validate-only PATCH` — run the validators against a user-supplied patch

-----

## System prompts

Live in `generate/prompts/` as `.md` files, loaded at runtime. Don't inline them in Python. Each has a header documenting its purpose, expected input/output, and model choice.

Required prompts for v0.1:

- `intent.md` — prompt → Intent JSON
- `fill.md` — Skeleton + Intent + catalog → module bindings
- `explain.md` — Patch → performance recipe

Prompt engineering rules:

- Always demand JSON output in a fenced block, with a schema in the prompt.
- Include at least 2 few-shot examples in each prompt.
- For `fill.md`, the catalog must be filtered down to ~20 candidate modules per role before sending — don't dump the whole registry every call. Do semantic filtering in Python first.

-----

## Corpus

`corpus/exemplars/` — 10-20 patches, hand-selected, each annotated with the intent that would have produced it. These are the few-shot examples. Keep them small (< 15 modules) so they fit cleanly in context.

`corpus/patchstorage/` — scraped from patchstorage.com/platform/mirack, gitignored. Used for evaluation and eventual fine-tuning, not in the v0.1 generation path.

-----

## Milestones

**M1 — Patch format nailed (day 1).** Export and diff a real MiRack patch. Document the schema. Write `emit/patch.py` such that it can round-trip a hand-written patch: parse → serialize → open in MiRack → still works.

**M2 — Catalog for one genre (day 2-3).** Build registry entries for ~40 modules sufficient for techno: Clocked, Marbles, Plaits, Rings, Clouds, Plateau, Bogaudio filters/VCAs, Fundamental utilities, Impromptu sequencers.

**M3 — End-to-end on one prompt (day 4-5).** Hardcode a techno skeleton. Run the pipeline for "techno, 128 bpm, Plaits + Rings, delay + reverb." Produce a patch that opens and plays.

**M4 — Grammar generalized (week 2).** Add house, dub, ambient skeletons. Validate structural correctness across all four.

**M5 — Validation + CLI polish (week 2).** Full validator suite, `--explain`, `--validate-only`, useful error messages.

**v0.1 done when:** 20 prompts across 4 genres all produce patches that (a) open in MiRack without errors, (b) make audible sound within 5 seconds of clock start, (c) are not embarrassing to demo.

-----

## Open questions / day-1 investigations

Claude Code should resolve these before committing to the architecture:

1. **Does MiRack's `.vcv` format drift from VCV Rack 0.6?** Export a patch, diff against a known-good VCV 0.6 patch, document the delta.
1. **How does MiRack report its bundled module set?** Check the app's documentation and the module browser UI. Confirm which of the VCV 0.6 plugin packs are actually available on iOS.
1. **Can desktop VCV Rack 0.6 still be built/installed?** Version 0.6 is old. If headless validation is infeasible, drop it from v0.1 and rely on structural checks only.
1. **Does the Anthropic API's structured output (tool use) work reliably for the Skeleton fill step, or should we use plain JSON mode?** Test both.
1. **What's the patchstorage API / scraping situation?** If there's no clean API, scraping is a weekend in itself — defer to v0.2 and rely on hand-curated exemplars for now.

-----

## Explicit non-requirements

- No web UI, no Electron app, no mobile app.
- No authentication, no multi-user, no database. Files on disk.
- No real-time anything.
- No training of bespoke models. The LLM is a dependency, not a research contribution.
- No module creation — we only emit patches using modules that exist in the MiRack bundled set.

-----

## Success metric

A user types a prompt on their laptop, a `.vcv` file appears in `~/Patchwright/patches/`, they move it into iCloud Drive → MiRack folder, and on the phone the patch opens and sounds like what they asked for. End-to-end time from prompt to sound: under 30 seconds.
