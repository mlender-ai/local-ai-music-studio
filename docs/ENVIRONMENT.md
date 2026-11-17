# Environment — 2026-11-15 (Asia/Seoul)

Pre-install diagnosis: empty Git repository; no CodeGraph index.

- macOS 26.2 (25C56), arm64, Apple M5, 10 GPU cores, Metal 4.
- RAM 24 GiB. vm_stat: free ~60 MiB, inactive ~4 GiB, speculative ~384 MiB; compressed physical storage ~10.5 GiB. memory_pressure reported 37% system-wide free (not equivalent to immediately free RAM).
- Swap already ~17.6 GiB used before this task. Existing processes were not stopped.
- Largest resident processes: macOS Virtualization (~1.3 GiB), existing Python (~652 MiB), Codex renderer (~621 MiB), Claude renderer (~298 MiB), Chromium (~240 MiB). RSS excludes compressed allocations.
- Disk available ~232 GiB.
- Python 3.13.3, Node v24.11.1, Git 2.50.1, ffmpeg present. uv absent from PATH. Homebrew Python 3.14/3.15 also present.
- Existing Hugging Face cache ~2 GiB: fashion-clip and siglip2, no music weights. Existing global packages inspected read-only; project uses isolated Python 3.12.16.
- torch / MLX isolated runtime checks succeeded as recorded below.

## Resource policy

One generation process across CLI/MCP/player, advisory file lock. DiT-only 2B Turbo; no planning LLM; 15–30 second clips. Monitor child process footprint, system availability and macOS pressure; terminate only project-owned child on limits or timeout. Reuse one local model directory. Do not change shell profiles, system Python, other environments or running jobs.

## Isolated runtime validation

- Project-local uv 0.13.8 and CPython 3.12.16 installed under `.bootstrap/` and `.runtime/python/`; no global package changes.
- PyTorch 2.10.0 MPS: available; GPU tensor `[1,1].sum()` returned `2.0`.
- MLX 0.32.4 Metal computation: `[1,2] + [1,2]` returned `[2,4]`.
- ACE-Step handler, inference dataclasses and LLMHandler imports succeeded. Optional training libraries (Lightning, LyCORIS, bitsandbytes) deliberately absent.
- Available memory at probe: ~4.01 GiB; macOS pressure level 2 (warning) already present before model execution. Generation will abort on critical pressure (4).
- Hugging Face Xet returned HTTP 416 for large files. Official HTTPS byte-range fallback is resumable and checks each weight against the repository LFS SHA-256. Inference itself remains offline.
- System Python 3.13 urllib's certificate store failed a read-only HTTPS probe. Requests with its verified CA bundle worked; certificate verification was not disabled.

## Generation outcome and final QA — 2026-11-16

- Original float32 MPS initialization exceeded the 10 GiB child footprint guard. bf16 MPS-only inference subsequently reached macOS critical pressure. Both attempts were stopped safely; they remain visible as failed history entries. Existing applications/processes were left running.
- Final verified default: official Turbo source/weights, local MLX 4-bit decoder, bf16 MPS conditioning/text encoder, tiled PyTorch VAE (32-frame tiles / 8 overlap). No 1.7B planner LLM. No limits were relaxed to obtain success.
- Trip-hop 30s: 69.132s total, peak child footprint 7.861 GiB (first conversion); ambient 30s: 27.998s / 5.011 GiB; house 30s: 28.650s / 5.003 GiB. See `generation-results.json` for worker-only timings and exact paths.
- New 15s generation through STDIO MCP also succeeded. Browser decoded all three 30s WAVs, played audio and switched A/B at the same time position. Human aesthetic listening assessment is not inferred from these checks.
- Model directory 6.9 GiB (official weights ~5.9 GiB plus local derived MLX cache ~944 MB); isolated environment 1.2 GiB; vendor source 31 MiB; output audio/history ~122 MiB before final transport checks. Disk totals vary as versions accumulate.
- Large files were completed from the official ModelScope mirror with pinned Hugging Face LFS SHA-256 verification. Existing valid files were reused. No community model files were introduced.
- The existing service on port 8765 was left untouched. This project's player uses 8795.
- 16 GiB hardware and CPU-only generation have not been tested. The measured figures are process footprints on this 24 GiB machine, not a guarantee of total system headroom elsewhere.
