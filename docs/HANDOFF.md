# HANDOFF.md — Multi-Agent Handoff

## Snapshot

- **Base Commit:** `a5085de` (`main`)
- **Integration Branch:** `develop/ai-native-daw`
- **Stacked Branches (all pushed, open & unmerged pending user review):**
  1. `feat/daw-workspace-phase-01` — PR #15 → `develop/ai-native-daw`
  2. `fix/daw-phase-01-1-stabilization` — PR #16 → `feat/daw-workspace-phase-01`
  3. `feat/daw-korean-localization` — PR #17 → `fix/daw-phase-01-1-stabilization`
  4. `feat/daw-reference-intelligence` — PR #18 → `feat/daw-korean-localization`
  5. `feat/daw-agent-bridge` — PR #19 → `feat/daw-reference-intelligence`
  6. `feat/daw-ai-composition-phase-03` (HEAD) — PR → `feat/daw-agent-bridge`

## Run Commands

```bash
# Single-command launch (auto-rebuilds frontend if sources changed, starts http://127.0.0.1:8796)
./scripts/start_daw.sh

# Full verification suites
.venv/bin/python -m pytest -q
cd apps/daw && npm test && npm run build

# MCP STDIO server (exposes 9 music.* + 45 daw.* = 54 tools)
.venv/bin/python -m app.mcp_server
```

## Phase 03 Verification Summary

- **Backend & Regression (`pytest -q`):** `51 passed` (including `tests/test_phase03_foundation.py`, `tests/test_mcp_subprocess.py` spawning a separate OS STDIO MCP process, `tests/test_phase03_composition.py` running Tests A, B, C, YuE2/Demucs honesty, providers & sample catalog, plus all 31 legacy tests).
- **Frontend (`vitest` + `vite build`):** `11 passed` + clean `tsc -b && vite build`.
- **Live Browser QA (`http://127.0.0.1:8796`):**
  - `1440×900` & `1280×800` verified with `0` console errors, `0` HTTP 4xx/5xx responses, `0` horizontal overflow.
  - Tested Korean conversational prompt (`현재 코드 진행에 맞는 4마디 신스 훅을 만들어줘. 기존 드럼과 베이스는 유지해줘.`) → `CompositionPlan` → Take generation (`midi-composer-v3`, `-26.51 LUFS`, `TP -17.56 dBTP`) → transactional `새 트랙 추가` preserving Drums & Bass → 20-note Piano Roll inspection + `Stereo Synth Hook ↔ Warm Electric Piano` switching → honest Providers/Engines tab.
  - Screenshots saved in `docs/screenshots/phase-03-*.png`.

## Local Environment Truth (Apple M1, 16 GiB RAM)

- Ready immediately offline: Built-in Music Composition Director, External MCP Bridge (`music-mcp`), Local Multitrack & MIDI Composer with 6 multi-timbre studio voices (`drum-kit-electronic`, `bass-fm-sub`, `synth-fm-hook`, `keys-electric-ep`, `guitar-clean-pluck`, `pad-warm-analog`).
- Not installed on this host (adapters ready & honestly report `Unavailable` / `Not Installed` until user installs weights/binaries):
  - YuE2 native binary (`.runtime/v4/yue2cpp/build/yue-synth` or `YUE2_BIN`)
  - ACE-Step checkpoints (`.runtime/models/checkpoints/` or `ACESTEP_CHECKPOINT_DIR`)
  - Demucs stem separator (`uv pip install demucs`)
  - Local Ollama (`127.0.0.1:11434`), `claude` CLI, `codex` CLI, or optional server-side `DAW_LLM_BASE_URL` + `DAW_LLM_API_KEY`.

## Next Priorities (Phase 04 — Arrangement & Variation)

1. Section/bar-range selective regeneration (regenerating only bars 9–16 or only the Drum fill on bar 8 while preserving surrounding context and crossfading audio seams).
2. Multi-take comping lanes directly inside the Arrangement Timeline.
3. Optional user-approved installation script for `demucs` / `ollama` / YuE2 binary when ready.
