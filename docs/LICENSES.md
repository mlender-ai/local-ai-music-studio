# Licenses and distribution review

The prototype uses a minimal inference dependency set, rather than ACE-Step's full UI/training environment. It does not bundle or invoke paid plugins, Suno/Splice, or a cloud music API. Package versions and bundled notices are recorded by `scripts/license_inventory.py` in `DEPENDENCIES.md` and `dependency-licenses.json`.

| Component | License/source | Distribution notes |
|---|---|---|
| ACE-Step Python implementation | [MIT](https://github.com/ace-step/ACE-Step-1.5/blob/main/LICENSE) | Preserve copyright and MIT text; pinned source checkout remains separate in ignored `vendor/`. |
| ACE-Step 1.5 Turbo / VAE weights | [Official model card: MIT](https://huggingface.co/ACE-Step/Ace-Step1.5) | Preserve model provenance/license when redistributing weights. Only official artifacts downloaded. |
| Qwen3-Embedding-0.6B text encoder | [Apache-2.0](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | Retain Apache license and any required notices; do not treat the aggregate ACE card's MIT label as relicensing Qwen. |
| PyTorch / torchaudio | BSD-style | Preserve bundled third-party notices. |
| MLX / mlx-lm | MIT | Used for the verified Apple Silicon decoder backend. |
| NumPy / SciPy / Numba | BSD-style | Binary wheels include additional native-library notices; retained in inventory. |
| Transformers / Diffusers / Accelerate / PEFT | Apache-2.0 | Preserve notices; PEFT is imported by upstream adapter, no training flow exposed. |
| SoundFile | BSD-3-Clause | Python wrapper is permissive; underlying library differs. |
| libsndfile (SoundFile's dynamic library) | [LGPL-2.1-or-later](https://github.com/libsndfile/libsndfile) | Do not silently bundle into a closed/static binary. For a shipped application, review LGPL source/relinking/replacement and notice requirements. Current use is a separate dynamically loaded local wheel. |
| FastAPI / Pydantic / MCP / Uvicorn | MIT / BSD as in installed metadata | Preserve notices. |
| frozendict (einx/vector-quantize dependency) | LGPL-3.0-only, installed package metadata | Retain LGPL text and corresponding source/changes when distributing; Python source remains a separate replaceable package. Commercial packaging needs review. |
| Certifi | MPL-2.0 | File-level obligations matter if modifying/distributing the package. |
| RBJ equalizer formulas | [W3C Audio EQ Cookbook](https://www.w3.org/TR/audio-eq-cookbook/) | Independently implemented mathematical formulas; reference attribution retained. |

No GPL-only DSP/plugin dependency was deliberately added. System ffmpeg was observed during diagnosis but is not required for WAV generation, processing or export. Optional upstream MP3/training/third-party code paths are not part of the product runtime.

Before commercial packaging: review the exact locked wheels' native components and bundled notices, preserve attribution, review LGPL distribution choices, and separately evaluate generated audio rights. Model/code license labels alone do not establish that every generated composition is free of third-party rights. This is an engineering inventory, not a completed legal clearance of a commercial release.
