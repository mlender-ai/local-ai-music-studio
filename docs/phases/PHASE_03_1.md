# PHASE 03.1 · ENGINE RECOVERY & SAFE INTEGRATION

**Branch:** `fix/daw-phase-03-engine-integration` (stacked on `feat/daw-ai-composition-phase-03` / PR #20)  
**Schema Version:** `1.3.0`  
**Status:** GATE 0 + GATE 1 (AI Provider live verified; Neural Audio runtime honestly audited as absent on host) + GATE 2 (Safe Take Apply & Concurrent Merge) Complete

## GATE 0 · Local Environment Forensic Audit

A full Spotlight (`mdfind`), home-directory, `/Applications`, `~/.cache`, and remote-branch audit (`origin/codex/v7-2-house-hook-first`, `v7-1`, `v7`, `v4`) established:

1. **Neural Audio & Stem Models (Verified Absent, Not Misconfigured Path):**
   - No `yue-synth` / `yue-plan` binaries, no `YuE2-3B-Q8_0.gguf` / `YuE2-Vae-F32.gguf` weights, no ACE-Step checkpoints, no `demucs`, no `ffmpeg`, and no `REAPER.app` exist on this Mac.
   - Earlier Codex V7.2 runs were executed in an external environment; their Golden Reference artifacts (`examples/v72/magnetic-afterhours/{original.wav,final.wav,request.json,generated-plan.abc,vocal-leakage.json,delivery.json}`) live in Git (`origin/codex/v7-2-house-hook-first`) and V7.2 `final.wav` is already imported in `demo_v72_magnetic_afterhours` & `demo_multitrack_session`.
   - Per directive Section 22, multi-gigabyte model caches are **not** blindly re-downloaded without approval.
2. **Real Authenticated Local AI Producer Discovered & Verified:**
   - Native macOS **Claude Code `2.1.330`** was discovered inside Claude Desktop's official bundle (`~/Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude`) with an active `claude.ai` login (`claude auth status -> loggedIn: true`).
   - Verified live end-to-end with strict music-production-only isolation (`--tools "" --no-session-persistence --output-format json`), authoring real structured chord progressions, scale-degree motifs, and Korean producer summaries without terminal/file access.

## Key Engineering Fixes Implemented

1. **Shared Runtime Registry (`engine/runtime/registry.py`)**:
   - Cross-worktree discovery via `DAW_SHARED_RUNTIME_DIR` / `~/.config/ai-native-daw/runtime.json` (zero personal paths in Git).
   - Strict 6-state lifecycle: `uninstalled` → `binary_found` → `model_found` → `ready` → `verified` → `failed`. Binary alone is never reported `ready`; `verified` requires recorded WAV smoke output.
2. **Exact V7.2 YuE2 Adapter & 3-State Vocal Gate (`engine/generation/adapters/yue2_adapter.py`)**:
   - Fixed CLI invocation to exact `v4_study.py` flags (`yue-plan` & `yue-synth` with `--model`, `--vae`, `--request`, `--max-seq 8192`, `--out`, `--score`).
   - Wired strict `check_resting_voice()` preflight ABC gate directly before `yue-synth` execution (verified blocking vocal ABC before synthesis runs).
   - Upgraded vocal leakage screening to strict 3-state `PASS` / `REJECT` / `UNCERTAIN` (neural audio without PANNs/Whisper/Demucs honestly yields `UNCERTAIN` and is never auto-approved as vocal-free).
3. **No Silent Engine Substitution (`engine/generation/daw_jobs.py`)**:
   - Explicitly requesting `yue2-native`, `ace-step-local`, or `neural_audio` when uninstalled returns `engineUnavailable: true` with exact missing items instead of silently substituting local MIDI.
4. **True Process-Group Cancellation & Shared Execution Lock (`engine/generation/process_guard.py`)**:
   - Replaced blocking `subprocess.run()` with `subprocess.Popen(..., start_new_session=True)` + `fcntl.flock` cross-process lock + 10 GiB Apple Silicon RSS guard + `SIGTERM → SIGKILL` process-group termination (verified in TEST F).
5. **Multi-Reference Binding & 5-State Feature Consumption (`engine/composition/reference_context.py`)**:
   - Independent per-reference influence mapping (`perReferenceBindings`), explicit opt-in (`reference_ids=[]` never auto-attaches), and `extracted → selected → mapped → consumed → verified` lifecycle per feature.
6. **GATE 2 · All 4 `apply_take()` Bugs Fixed + Concurrent Merge Safety**:
   - `replace_range` splits/carves ONLY `[startBeats, endBeats]` on target track with zero overlapping clips and creates an automatic Original Backup Take Lane.
   - Never overwrites an existing MIDI track's `instrumentRef`.
   - Stem separation records `sourceTrackId`/`parentSourceAssetId`/`separationModel`/`separationJobId` and mutes ONLY `sourceTrackId` (TEST D).
   - Never wipes existing section markers unless `replace_sections=true` or project is empty.
   - Concurrent edit merge (TEST E): tracks `baseRevision` + per-track fingerprints so user edits on unrelated tracks during AI generation are preserved cleanly; duplicate apply is rejected unless `forceReapply=true`.
