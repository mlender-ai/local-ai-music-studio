# HANDOFF.md — Multi-Agent Handoff

## Snapshot

- **Base Commit:** `a5085de` (`main`)
- **Integration Branch:** `develop/ai-native-daw`
- **Stacked Branches (all pushed, unmerged pending user review):**
  1. `feat/daw-workspace-phase-01` (`f13cc7e`) — PR #15 → `develop/ai-native-daw`
  2. `fix/daw-phase-01-1-stabilization` (`12aa2b5`) — PR → `feat/daw-workspace-phase-01`
  3. `feat/daw-korean-localization` (`99d5e14`) — PR → `fix/daw-phase-01-1-stabilization`
  4. `feat/daw-reference-intelligence` (`fb30864`) — PR → `feat/daw-korean-localization`
  5. `feat/daw-agent-bridge` (HEAD) — PR → `feat/daw-reference-intelligence`

## Run Commands

```bash
# Single-command launch (auto-detects frontend source changes, seeds demos, starts http://127.0.0.1:8796)
./scripts/start_daw.sh

# Full verification suites
.venv/bin/python -m pytest -q
cd apps/daw && npm test && npm run build

# MCP STDIO server (exposes 9 music.* + 28 daw.* tools)
.venv/bin/music-mcp
```

## Test & QA Summary

- **Backend & Legacy Regression:** `40 passed` in `3.29s` (`tests/test_daw_workspace.py`, `tests/test_reference_intelligence.py`, `tests/test_agent_bridge.py` + all 31 legacy tests).
- **Frontend Unit Tests & Build:** `10 passed` (Vitest: scheduler parity, MIDI chase, revision fingerprint, i18n ko/en parity, IME guard, WAV encoder) + clean `tsc -b && vite build`.
- **Live Browser QA (`http://127.0.0.1:8796`):**
  - `1440×900` Korean default UI, `KO ↔ EN` toggle, live `에이전트 브리지 활성` SSE badge, `0` console/HTTP errors.
  - Real V7.2 Magnetic Afterhours acoustic analysis (`127.9 BPM`, `F mixolydian`, `-18.48 LUFS`, `-1.64 dBFS`, 8 clickable sections, 6 Welch PSD bands, HPSS estimates, Blueprint toggle, Reference vs Mix comparison).
  - Live Korean Producer Command (`드럼 트랙을 잠깐 뮤트해줘` → Staged Proposal → Apply → immediate Mute + revision bump → Undo; `기타에 EQ랑 리버브 걸어줘` → honest Phase 05 refusal).
  - `1280×800` responsive Korean layout verified (`내보내기` right edge `1272px <= 1280px`, single-line buttons and Clip Editor footer).

## Unverified / Pending User Input

- Subjective listening QA on real playback/editing and external user-supplied reference files (Test B local file).
- Merging of stacked PRs after user review.

## Next Priorities (Phase 03 — AI Composition)

1. Connect `ReferenceBlueprint` (`selectedInfluences`, BPM, key, section timeline, energy arc) to local YuE2 / ACE-Step generation adapters behind an explicit job queue respecting existing 10 GiB Apple Silicon memory guards.
2. Auto-place generated audio/MIDI outputs onto new timeline tracks as staged proposals (`daw.preview_changes`) with non-destructive take comparison.
3. Add optional stem separation workflow (Demucs/equivalent, explicitly marked `STEM · 추정`) gated behind memory checks.
