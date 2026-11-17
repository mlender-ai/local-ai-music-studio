"""Apply strictly validated effects in user-specified order."""

import numpy as np
from engine.schema import Chain
from engine.dsp.filters import equalize, saturate
from engine.dsp.dynamics import compress, limit
from engine.dsp.reverb import reverb

PROCESSORS = dict(
    eq=equalize, compressor=compress, reverb=reverb, distortion=saturate, limiter=limit
)


def process(x, sr, effects):
    chain = Chain(effects=effects)
    if (
        x.ndim != 2
        or x.shape[1] not in (1, 2)
        or not len(x)
        or not np.isfinite(x).all()
    ):
        raise ValueError(
            "Expected nonempty finite [frames, mono/stereo channels] audio."
        )
    y = x.copy()
    for effect in chain.effects:
        y = PROCESSORS[effect.type](y, sr, effect)
        if y.shape != x.shape or not np.isfinite(y).all():
            raise ValueError(f"{effect.type} produced invalid audio.")
    return y
