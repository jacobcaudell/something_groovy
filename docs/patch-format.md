# MiRack / VCV Rack 0.6 `.vcv` Patch Format

> **TODO(M1):** Blocked on a real MiRack export. Once a user-provided
> `.vcv` file (minimal VCO → VCA → Audio patch) lands in
> `corpus/exemplars/raw/`, diff it against a reference VCV Rack 0.6
> patch and document the delta here.

## What goes here

- Top-level JSON schema (version, modules, cables).
- Module entry shape (plugin slug, model slug, pos, params, data).
- Cable entry shape (src module id, src output id, dst module id,
  dst input id, colors).
- MiRack-specific fields (if any) that diverge from upstream VCV 0.6.
- Coordinate system / grid units.
- Round-trip requirements (must open cleanly in MiRack on iPad).

## Status

Unknown until a patch export is available. `patchwright/emit/patch.py`
currently writes a best-guess VCV 0.6 JSON and is flagged as a stub.
