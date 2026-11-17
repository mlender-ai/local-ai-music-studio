"""Isolated ACE-Step worker; stdout is a log, result is an atomic JSON file."""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/ACE-Step-1.5"))
os.environ.update(
    ACESTEP_CHECKPOINTS_DIR=str(ROOT / ".runtime/models/checkpoints"),
    HF_HOME=str(ROOT / ".runtime/hf-cache"),
    HF_MODULES_CACHE=str(ROOT / ".runtime/hf-modules"),
    TORCH_HOME=str(ROOT / ".runtime/torch"),
    HF_HUB_OFFLINE="1",
    TRANSFORMERS_OFFLINE="1",
    TOKENIZERS_PARALLELISM="false",
    ACESTEP_INIT_LLM="false",
    PYTORCH_ENABLE_MPS_FALLBACK="1",
)


def conditional_parameters(request):
    """Experimental official repaint path; unavailable through ordinary Generate input."""
    task = request.get("task_type", "text2music")
    if task == "text2music":
        return {}
    if task != "repaint":
        raise ValueError("Only the audited repaint experiment is supported.")
    from engine.paths import audio_path
    from engine.rendering.audio import analyze
    import math

    path = audio_path(request["src_audio"])
    info = analyze(path)
    start, end = float(request["repainting_start"]), float(request["repainting_end"])
    if not (
        math.isfinite(start)
        and math.isfinite(end)
        and 0 <= start < end <= info["duration_seconds"] <= 30
    ):
        raise ValueError(
            "Repaint range must lie inside a source of at most 30 seconds."
        )
    if abs(info["duration_seconds"] - request["duration"]) > 0.1:
        raise ValueError("Repaint must preserve source duration.")
    return dict(
        task_type="repaint",
        src_audio=str(path),
        repainting_start=start,
        repainting_end=end,
        chunk_mask_mode="explicit",
    )


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    import torch

    torch.set_num_threads(4)
    if torch.backends.mps.is_available():
        torch.mps.set_per_process_memory_fraction(0.45)
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler
    from acestep.inference import GenerationParams, GenerationConfig, generate_music

    class OfflineHandler(AceStepHandler):
        def _load_main_model_from_checkpoint(self, **kwargs):
            # Upstream defaults MPS to float32, doubling 2B weights during load.
            # On supported Apple Silicon, keep checkpoint-native bfloat16.
            if kwargs["device"] == "mps":
                self.dtype = torch.bfloat16
            return super()._load_main_model_from_checkpoint(**kwargs)

        def _load_text_encoder_and_tokenizer(self, *, checkpoint_dir, device):
            from transformers import AutoModel, AutoTokenizer

            path = str(Path(checkpoint_dir) / "Qwen3-Embedding-0.6B")
            self.text_tokenizer = AutoTokenizer.from_pretrained(
                path, local_files_only=True
            )
            self.text_encoder = AutoModel.from_pretrained(
                path, dtype=self.dtype, local_files_only=True
            ).eval()
            return path

        def _initialize_mlx_backends(self, **kwargs):
            if not request.get("mlx", False):
                return "Disabled by adapter", "Disabled by adapter"
            from engine.generation.mlx_quantized import load_decoder

            self.mlx_decoder = load_decoder(
                self.model,
                self.config,
                ROOT / ".runtime/models/derived/dit-4bit-ca1e85fe-19671f40.safetensors",
            )

            class UnavailableDecoder(torch.nn.Module):
                def forward(self, *args, **kwargs):
                    raise RuntimeError(
                        "MLX diffusion failed; full-size PyTorch fallback is disabled for memory safety."
                    )

            self.model.decoder = UnavailableDecoder()
            self.use_mlx_dit = True
            self.mlx_dit_compiled = False
            self._release_system_memory()
            return "Active (local 4-bit Linear weights)", "Disabled; tiled PyTorch VAE"

        def _ensure_models_present(self, *, checkpoint_path, **kwargs):
            # Upstream's precheck also requires the unused 1.7B LM. Only this
            # explicit DiT-only adapter narrows that check. Never auto-download.
            required = [
                "acestep-v15-turbo/model.safetensors",
                "vae/diffusion_pytorch_model.safetensors",
                "Qwen3-Embedding-0.6B/model.safetensors",
            ]
            for item in required:
                if not (checkpoint_path / item).is_file():
                    return (
                        f"Missing official weights: {item}. Run scripts/download_models.py",
                        False,
                    )
            return None

    started = time.monotonic()
    handler = OfflineHandler()
    device = request.get("device", "mps")
    mlx = request.get("mlx", False)
    if mlx:
        import mlx.core as mx

        mx.set_memory_limit(6 * 1024**3)
        mx.set_cache_limit(256 * 1024**2)
    status, ok = handler.initialize_service(
        project_root=str(ROOT / ".runtime/models"),
        config_path="acestep-v15-turbo",
        device=device,
        offload_to_cpu=True,
        offload_dit_to_cpu=True,
        use_mlx_dit=mlx,
        compile_model=False,
        prefer_source="huggingface",
    )
    print(status, flush=True)
    if not ok:
        raise RuntimeError(status)
    conditional = conditional_parameters(request)
    params = GenerationParams(
        **conditional,
        caption=request["caption"],
        lyrics=request.get("lyrics", ""),
        instrumental=request.get("instrumental", True),
        bpm=request.get("bpm"),
        timesignature=request.get("timesignature", ""),
        duration=request["duration"],
        seed=request["seed"],
        inference_steps=8,
        # Turbo's dataclass default is shift=1 (base/SFT). Upstream explicitly
        # recommends shift=3 for this Turbo checkpoint; CFG is distilled in.
        shift=3.0,
        guidance_scale=1.0,
        thinking=False,
        use_cot_caption=False,
        use_cot_metas=False,
        use_cot_language=False,
        use_cot_lyrics=False,
    )
    result = generate_music(
        handler,
        LLMHandler(),
        params,
        GenerationConfig(
            batch_size=1,
            use_random_seed=False,
            seeds=[request["seed"]],
            audio_format="wav",
        ),
        save_dir=request["save_dir"],
    )
    if not result.success or not result.audios:
        raise RuntimeError(result.error or result.status_message)
    record = {
        "path": result.audios[0]["path"],
        "elapsed_seconds": time.monotonic() - started,
        "backend": f"ACE-Step 1.5 2B Turbo / {device} / MLX DiT 4-bit={handler.use_mlx_dit}",
        "model_revision": "19671f406d603126926c1b7e2adc169acbcade22",
        "inference": {
            "task_type": params.task_type,
            "repainting_start": params.repainting_start,
            "repainting_end": params.repainting_end,
            "steps": params.inference_steps,
            "infer_method": params.infer_method,
            "thinking": params.thinking,
            "shift": params.shift,
            "guidance_scale": params.guidance_scale,
            "timesignature": params.timesignature,
            "bpm": params.bpm,
        },
    }
    out = Path(request["result_path"])
    out.with_suffix(".tmp").write_text(json.dumps(record, indent=2))
    out.with_suffix(".tmp").replace(out)


if __name__ == "__main__":
    main()
