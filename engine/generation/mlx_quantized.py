"""Layerwise local MLX conversion of official ACE-Step decoder weights.

Only Linear weights are quantized; convolution layout follows upstream's
converter. No community weights or additional model download is used.
"""

import gc
from pathlib import Path


def _replace(model, path, layer):
    parts = path.split(".")
    parent = model
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    if isinstance(parent, list):
        parent[int(parts[-1])] = layer
    else:
        parent[parts[-1]] = layer


def _mapped(key, value):
    data = value.detach().cpu().float().numpy()
    if key.startswith("proj_in.1."):
        key = key.replace("proj_in.1.", "proj_in.")
        if key.endswith(".weight"):
            data = data.swapaxes(1, 2)
    elif key.startswith("proj_out.1."):
        key = key.replace("proj_out.1.", "proj_out.")
        if key.endswith(".weight"):
            data = data.transpose(1, 2, 0)
    return key, data


def load_decoder(pytorch_model, config, cache: Path):
    import mlx.core as mx
    import mlx.nn as nn
    from mlx.utils import tree_flatten
    from acestep.models.mlx.dit_model import MLXDiTDecoder

    decoder = MLXDiTDecoder.from_config(config)

    def predicate(path, module):
        return isinstance(module, nn.Linear) and module.weight.shape[-1] % 64 == 0

    if cache.is_file():
        nn.quantize(decoder, group_size=64, bits=4, class_predicate=predicate)
        decoder.load_weights(str(cache), strict=True)
        mx.eval(decoder.parameters())
        print("Loaded local MLX 4-bit decoder cache", flush=True)
    else:
        source = pytorch_model.decoder.state_dict()
        expected = set(dict(tree_flatten(decoder.parameters())))
        consumed = set()
        for name, module in list(decoder.named_modules()):
            if not predicate(name, module):
                continue
            key = name + ".weight"
            if key not in source:
                raise ValueError(f"No official weight for MLX layer {key}")
            module.weight = mx.array(source[key].detach().cpu().float().numpy())
            consumed.add(key)
            if name + ".bias" in source:
                module.bias = mx.array(
                    source[name + ".bias"].detach().cpu().float().numpy()
                )
                consumed.add(name + ".bias")
            quantized = nn.QuantizedLinear.from_linear(module, group_size=64, bits=4)
            mx.eval(quantized.parameters())
            _replace(decoder, name, quantized)
            # named_modules() snapshot retains old Linear objects: release their
            # temporary float weights immediately after the quantized arrays materialize.
            module.weight = mx.zeros((0, 0))
            if "bias" in module:
                module.bias = mx.zeros((0,))
            mx.clear_cache()
        for key, value in source.items():
            if key in consumed or "rotary_emb" in key:
                continue
            mapped, data = _mapped(key, value)
            if mapped not in expected:
                raise ValueError(f"Unexpected decoder weight {mapped}")
            decoder.load_weights([(mapped, mx.array(data))], strict=False)
            consumed.add(mapped)
        if expected - consumed:
            raise ValueError(f"Missing decoder weights: {sorted(expected - consumed)}")
        mx.eval(decoder.parameters())
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(".tmp.safetensors")
        mx.save_safetensors(
            str(temporary),
            dict(tree_flatten(decoder.parameters())),
            metadata={
                "source": "ACE-Step/Ace-Step1.5@19671f406d603126926c1b7e2adc169acbcade22",
                "conversion": "linear affine 4-bit, group 64; native convolution layouts",
            },
        )
        temporary.replace(cache)
        print("Created local MLX 4-bit decoder cache", flush=True)
        del source
    decoder.materialize_static_buffers()
    gc.collect()
    mx.clear_cache()
    return decoder
