"""Signal tests verify physical behavior, not just function return values."""

import numpy as np
import pytest
from engine.dsp.chain import process
from engine.schema import Chain

SR = 48000


def tone(frequency=100, amplitude=0.1):
    t = np.arange(SR) / SR
    x = amplitude * np.sin(2 * np.pi * frequency * t)
    return np.column_stack([x, x * 0.4])


def rms(x):
    return np.sqrt(np.mean(x * x))


@pytest.mark.parametrize(
    "mode,freq", [("low_shelf", 50), ("high_shelf", 12000), ("peaking", 1000)]
)
def test_eq_has_expected_gain(mode, freq):
    x = tone(freq)
    y = process(x, SR, [dict(type="eq", mode=mode, frequency=1000, gain_db=6, q=0.707)])
    gain = 20 * np.log10(rms(y[SR // 2 :, 0]) / rms(x[SR // 2 :, 0]))
    assert 5.7 < gain < 6.3
    assert np.allclose(y[:, 1], y[:, 0] * 0.4)


def test_compressor_reduces_loud_material_and_links_stereo():
    x = tone(amplitude=0.8)
    y = process(
        x, SR, [dict(type="compressor", threshold_db=-24, ratio=6, attack_ms=2)]
    )
    assert rms(y[SR // 2 :]) < rms(x[SR // 2 :]) * 0.5
    assert np.allclose(y[:, 1], y[:, 0] * 0.4)


def test_reverb_has_predelay_tail_and_exact_length():
    x = np.zeros((SR, 2))
    x[0, :] = 0.3
    wet = process(x, SR, [dict(type="reverb", wet=1, pre_delay_ms=50, decay=0.8)])
    assert np.max(np.abs(wet[:2400])) < 1e-12
    assert rms(wet[3000:12000]) > 1e-6
    assert wet.shape == x.shape
    assert not np.array_equal(wet[:, 0], wet[:, 1])


def test_limiter_handles_first_sample_and_transients():
    x = np.zeros((SR, 2))
    x[0] = [20, -10]
    x[20000] = [4, 1]
    y = process(x, SR, [dict(type="limiter", ceiling_db=-1)])
    assert np.max(np.abs(y)) <= 10 ** (-1 / 20) + 1e-12
    assert y[0, 0] / y[0, 1] == -2


def test_saturation_changes_spectrum_and_chain_order():
    x = tone(500, 0.6)
    saturation = dict(type="distortion", drive_db=18, output_db=-12)
    eq = dict(type="eq", mode="low_shelf", frequency=1000, gain_db=6)
    y = process(x, SR, [saturation])
    assert not np.allclose(x, y)
    assert not np.allclose(
        process(x, SR, [saturation, eq]), process(x, SR, [eq, saturation])
    )


@pytest.mark.parametrize(
    "effects",
    [
        [dict(type="eq", gain_db=float("nan"))],
        [dict(type="reverb", decay=-1)],
        [dict(type="exec", code="bad")],
        [dict(type="limiter", ceiling_db=2)],
    ],
)
def test_invalid_parameters_rejected(effects):
    with pytest.raises(ValueError):
        Chain(effects=effects)


def test_nyquist_and_nonfinite_inputs_rejected():
    with pytest.raises(ValueError):
        process(tone(), 8000, [dict(type="eq", frequency=6000)])
    x = tone()
    x[0, 0] = np.inf
    with pytest.raises(ValueError):
        process(x, SR, [dict(type="limiter")])
