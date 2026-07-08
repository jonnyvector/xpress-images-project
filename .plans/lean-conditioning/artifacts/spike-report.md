# lean-conditioning — Spike Report (2026-07-08)

Probes: Journey & Dylan — 3 bare-lean + 3 lean+anchor draws each, plus a
Dylan follow-up arm (3 draws, lean + spec width note only). ~$2.01 total.
Comparison artifact: https://claude.ai/code/artifact/bc5b324f-afe6-4e77-9f60-95964d562e24
Raw verdicts: scratchpad spike_results.json / spike_widthnote_results.json.

| Door | Arm | Judge | Operator |
|---|---|---|---|
| Journey | bare ×3 | 3/3 CLEAN | good — thin frame held |
| Journey | anchored ×3 | 0/3 | fattened frames; one draw in 3/4 perspective |
| Dylan | bare ×3 | "0/3, inside-edge only" — stiles_rails FALSE-MATCHED 6/6 | terrible — frame fattened to standard shaker |
| Dylan | anchored ×3 | 0/3 | worse: miters + raised panel induced |
| Dylan | width-note ×3 | 2/3 CLEAN (3rd flag = joint call contradicting the spec, judge/extraction error) | draw 1 visually exact |

## Outcomes

- **A-001 PASS** — anchor excluded from the lean tail. In a lean prompt
  (no "studio product photo" boilerplate) the line-art cross-section
  leaks its own 3/4 viewpoint and cues wrong construction (miters,
  raise). Anchor remains on prose rungs only (unchanged P3 behavior).
- **A-002 FAIL → escape hatch 2** — the lean tail carries exactly the
  spec width note (`wood_specs.learn_notes`), nothing else. Bare lean
  fattened Dylan's 2.25 in frame 3/3; with the note, held.
- **D-012 recorded**: tail = lean prompt + width note only, no anchor,
  temp 0.
- **Judge blind spot re-confirmed**: stiles_rails false-matched on all
  six fat-framed Dylan draws — frame width must be operator-verified;
  Stage-A remains the gate. (Also: auto-extracted facts called mitered
  Dylan "cope and stick" — spec-file joint data is more reliable than
  extraction for joint type.)
