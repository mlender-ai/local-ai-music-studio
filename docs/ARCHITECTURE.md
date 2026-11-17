# Local AI Music Studio — Phase 1

## Boundaries

`CLI / local HTTP player / STDIO MCP → engine jobs & service → generation backend / independent DSP → immutable WAV versions + SQLite history`

- `engine/generation/backend.py`: replaceable protocol and ACE-Step adapter.
- `worker.py`: only process importing the model. Official pinned code + pinned weights; offline inference; no external music generation endpoints. A small subclass removes the upstream mandatory check/download of the unused 1.7B LM and loads MPS conditioning/text weights in bf16. `mlx_quantized.py` converts official decoder Linear weights to MLX affine 4-bit (group 64), validates complete key coverage and atomically caches the result. The decoder runs on MLX, conditioning and tiled VAE on PyTorch MPS. PyTorch decoder storage is released; automatic full-size fallback is disabled. Vendor source stays untouched.
- `supervisor.py`: timeout (900s), process memory-footprint ceiling (10 GiB, including macOS compressed/unified allocations), available RAM floor, macOS critical-pressure stop. These are best-effort sampled protections, not an OS hard memory quota; MPS allocation also has a 45% physical-memory cap. Only the worker created by this operation can be terminated.
- `jobs.py`: SQLite transaction reserves one active job; detached supervisor permits quick MCP responses and status polling. File lock additionally prevents inference overlap. Client request keys deduplicate retries, and mismatched reused keys are rejected. Stale crashed jobs are detected.
- `schema.py`: Pydantic tagged union, bounded numeric parameters, no extra fields or nonfinite numbers.
- `agent/command_parser.py`: Korean/English templates preserve the original prompt and expose the translated plan. Deterministic rules are deliberately limited. Unsupported edits explicitly require regeneration/stems.
- `dsp/`: RBJ low/high shelf and peaking biquads, stereo-linked peak compressor, diffuse convolution reverb, 4× oversampled tanh saturation, sample-peak limiter.
- `rendering/audio.py`: source shape/rate/finite validation, PCM24 writes, analysis and aligned difference measurement. DSP keeps frames/sample rate/channels exactly. Reverb tails are truncated by design. Sample-peak limiting is not certified true-peak limiting.
- `store.py`: append-only version graph and reversible current-version pointer. Restoring does not delete a newer version. Effects are baked in each child; rendering from an earlier version permits branching. Originals are never overwritten.
- File boundary: all WAV paths resolve inside `outputs` (or configured `MUSIC_DATA_DIR`); symlink escapes, arbitrary exports and overwrites are refused. Imported WAVs are labelled user-supplied, never generated.

## Model capabilities reviewed

ACE-Step upstream commit `ca1e85fe9430179831e6bc6be790c332190a3866`; official HF release `19671f406d603126926c1b7e2adc169acbcade22`.

| Feature | Upstream | This prototype |
|---|---|---|
| Text-to-Music | Base/SFT/Turbo | 2B Turbo, batch 1, 15–30s |
| Instrumental / vocals | supported via lyrics/metadata | exposed; vocal quality separately unverified |
| Repaint, Cover/Remix | Base/SFT/Turbo | not exposed |
| Extract, Lego, Complete | Base; not 2B Turbo/SFT | not exposed |
| Python / REST | official APIs | Python adapter; private player HTTP API |
| Apple Silicon | MPS, MLX DiT/VAE/LM | Verified MLX 4-bit DiT + MPS bf16 / tiled VAE |

No full DAW, stems, MIDI editor, plugin hosting, accounts, payment, or cloud deployment.

Sources: [official repository](https://github.com/ace-step/ACE-Step-1.5), [installation](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INSTALL.md), [Python API](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INFERENCE.md), [model card](https://huggingface.co/ACE-Step/Ace-Step1.5), [RBJ cookbook](https://www.w3.org/TR/audio-eq-cookbook/).

## Local client verification

All frontends share `engine.service` and `engine.jobs`. Nine Python FastMCP tools use STDIO. Project-scoped Codex configuration is backed up before modification; global Codex configuration is untouched. The SDK smoke client performed a new 15-second model generation. The installed Codex app-server then called the real MCP transport, including replaying that generation's request key to verify cross-client idempotency. No model conversation or additional agent was spawned for this transport test.

The player binds to 127.0.0.1:8795, validates Host and mutation Origin/header, serves range-capable WAV responses and exposes no arbitrary file read endpoint. A/B switching pauses the other audio element and aligns its playback time. Browser playback, produce, compare, restore and export were exercised on the actual generated files.
