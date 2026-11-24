/**
 * Phase 03-E: 6 Built-in Studio Multi-Timbre Instrument Voices for Web Audio API
 * (Mirrors `engine/instruments/synth_engine.py` across Realtime playback, Piano Roll audition,
 * and OfflineAudioContext WAV export so preview and export match cleanly.)
 */

export interface StudioInstrumentOption {
  id: string;
  name: string;
  nameKo: string;
  category: string;
}

export const STUDIO_INSTRUMENTS: StudioInstrumentOption[] = [
  { id: "drum-kit-electronic", name: "Electronic Drum Kit", nameKo: "일렉트로닉 드럼 킷", category: "drums" },
  { id: "bass-fm-sub", name: "FM Sub Bass", nameKo: "FM 서브 베이스", category: "bass" },
  { id: "synth-fm-hook", name: "Stereo Synth Hook", nameKo: "스테레오 신스 훅", category: "synth" },
  { id: "keys-electric-ep", name: "Warm Electric Piano", nameKo: "일렉트릭 피아노 (EP)", category: "keys" },
  { id: "guitar-clean-pluck", name: "Clean Guitar Pluck", nameKo: "클린 기타 플럭", category: "guitar" },
  { id: "pad-warm-analog", name: "Warm Analog Pad", nameKo: "웜 아날로그 패드", category: "pad" },
  { id: "basic-poly-synth", name: "Basic Poly Synth", nameKo: "기본 폴리 신스", category: "synth" },
];

const noiseBufferCache = new WeakMap<BaseAudioContext, AudioBuffer>();

function getNoiseBuffer(ctx: BaseAudioContext): AudioBuffer {
  let buf = noiseBufferCache.get(ctx);
  if (buf) return buf;
  const len = Math.floor(ctx.sampleRate * 1.0);
  buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const data = buf.getChannelData(0);
  let seed = 1337;
  for (let i = 0; i < len; i++) {
    seed = (seed * 16807) % 2147483647;
    data[i] = (seed / 1073741823.5) - 1.0;
  }
  noiseBufferCache.set(ctx, buf);
  return buf;
}

function scheduleDrumVoice(
  ctx: BaseAudioContext,
  destination: AudioNode,
  pitch: number,
  velocity: number,
  safeStart: number,
  clipGainLinear: number
): AudioScheduledSourceNode[] {
  const ampScale = (Math.max(1, Math.min(127, velocity)) / 127) * 0.55 * clipGainLinear;
  const nodes: AudioScheduledSourceNode[] = [];

  // Kick (35, 36)
  if (pitch === 35 || pitch === 36) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(165, safeStart);
    osc.frequency.exponentialRampToValueAtTime(46, safeStart + 0.085);
    gain.gain.setValueAtTime(Math.max(0.0002, ampScale * 1.15), safeStart);
    gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + 0.30);
    osc.connect(gain);
    gain.connect(destination);
    osc.start(safeStart);
    osc.stop(safeStart + 0.32);
    nodes.push(osc);
    return nodes;
  }

  // Snare (38, 40) or Clap (39)
  if (pitch === 38 || pitch === 39 || pitch === 40) {
    const noise = ctx.createBufferSource();
    noise.buffer = getNoiseBuffer(ctx);
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.setValueAtTime(pitch === 39 ? 1800 : 2400, safeStart);
    bp.Q.setValueAtTime(pitch === 39 ? 1.4 : 0.9, safeStart);
    const ng = ctx.createGain();
    ng.gain.setValueAtTime(Math.max(0.0002, ampScale * 0.78), safeStart);
    ng.gain.exponentialRampToValueAtTime(0.0001, safeStart + (pitch === 39 ? 0.24 : 0.20));
    noise.connect(bp);
    bp.connect(ng);
    ng.connect(destination);
    noise.start(safeStart);
    noise.stop(safeStart + 0.26);
    nodes.push(noise);

    if (pitch !== 39) {
      const body = ctx.createOscillator();
      const bg = ctx.createGain();
      body.type = "triangle";
      body.frequency.setValueAtTime(210, safeStart);
      body.frequency.exponentialRampToValueAtTime(145, safeStart + 0.08);
      bg.gain.setValueAtTime(Math.max(0.0002, ampScale * 0.55), safeStart);
      bg.gain.exponentialRampToValueAtTime(0.0001, safeStart + 0.14);
      body.connect(bg);
      bg.connect(destination);
      body.start(safeStart);
      body.stop(safeStart + 0.16);
      nodes.push(body);
    }
    return nodes;
  }

  // Closed Hat (42, 44) / Open Hat (46) / Crash (49+)
  if (pitch === 42 || pitch === 44 || pitch === 46 || pitch >= 49) {
    const noise = ctx.createBufferSource();
    noise.buffer = getNoiseBuffer(ctx);
    const hp = ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.setValueAtTime(pitch >= 49 ? 3600 : 6200, safeStart);
    const ng = ctx.createGain();
    const decay = pitch >= 49 ? 0.85 : pitch === 46 ? 0.26 : 0.065;
    ng.gain.setValueAtTime(Math.max(0.0002, ampScale * (pitch >= 49 ? 0.45 : 0.52)), safeStart);
    ng.gain.exponentialRampToValueAtTime(0.0001, safeStart + decay);
    noise.connect(hp);
    hp.connect(ng);
    ng.connect(destination);
    noise.start(safeStart);
    noise.stop(safeStart + decay + 0.02);
    nodes.push(noise);
    return nodes;
  }

  // Toms
  const baseFreq = 82 + Math.max(0, pitch - 41) * 14;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(baseFreq * 1.5, safeStart);
  osc.frequency.exponentialRampToValueAtTime(baseFreq, safeStart + 0.11);
  gain.gain.setValueAtTime(Math.max(0.0002, ampScale * 0.8), safeStart);
  gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + 0.25);
  osc.connect(gain);
  gain.connect(destination);
  osc.start(safeStart);
  osc.stop(safeStart + 0.27);
  nodes.push(osc);
  return nodes;
}

export function scheduleInstrumentVoice(
  ctx: BaseAudioContext,
  destination: AudioNode,
  instrumentRef: string | null | undefined,
  pitch: number,
  velocity: number,
  startTime: number,
  durationSec: number,
  clipGainLinear = 1.0,
  chased = false
): AudioScheduledSourceNode[] {
  const inst = instrumentRef || "basic-poly-synth";
  const safeStart = Math.max(ctx.currentTime, startTime);
  const safeDur = Math.max(0.025, durationSec);

  if (inst === "drum-kit-electronic") {
    return scheduleDrumVoice(ctx, destination, pitch, velocity, safeStart, clipGainLinear);
  }

  const freq = 440 * Math.pow(2, (pitch - 69) / 12);
  const velNorm = Math.max(1, Math.min(127, velocity)) / 127;

  if (inst === "bass-fm-sub") {
    const release = 0.06;
    const stopTime = safeStart + safeDur + release;
    const carrier = ctx.createOscillator();
    const mod = ctx.createOscillator();
    const modGain = ctx.createGain();
    const lp = ctx.createBiquadFilter();
    const amp = ctx.createGain();

    carrier.type = "sine";
    carrier.frequency.setValueAtTime(freq, safeStart);
    mod.type = "sine";
    mod.frequency.setValueAtTime(freq * 2, safeStart);

    modGain.gain.setValueAtTime(chased ? freq * 0.3 : freq * 2.2, safeStart);
    modGain.gain.exponentialRampToValueAtTime(Math.max(1, freq * 0.25), safeStart + 0.11);

    lp.type = "lowpass";
    lp.frequency.setValueAtTime(Math.min(1400, freq * 5.5), safeStart);

    const peak = velNorm * 0.36 * clipGainLinear;
    amp.gain.setValueAtTime(0.0001, safeStart);
    amp.gain.linearRampToValueAtTime(peak, safeStart + 0.005);
    amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak * 0.72), safeStart + Math.min(0.14, safeDur));
    amp.gain.setValueAtTime(Math.max(0.0002, peak * 0.72), safeStart + safeDur);
    amp.gain.linearRampToValueAtTime(0.0001, stopTime);

    mod.connect(modGain);
    modGain.connect(carrier.frequency);
    carrier.connect(lp);
    lp.connect(amp);
    amp.connect(destination);

    carrier.start(safeStart);
    mod.start(safeStart);
    carrier.stop(stopTime + 0.01);
    mod.stop(stopTime + 0.01);
    return [carrier, mod];
  }

  if (inst === "synth-fm-hook") {
    const release = 0.14;
    const stopTime = safeStart + safeDur + release;
    const oscL = ctx.createOscillator();
    const oscR = ctx.createOscillator();
    const filter = ctx.createBiquadFilter();
    const amp = ctx.createGain();

    oscL.type = "sawtooth";
    oscR.type = "triangle";
    oscL.frequency.setValueAtTime(freq * 0.9965, safeStart);
    oscR.frequency.setValueAtTime(freq * 1.0035, safeStart);

    filter.type = "lowpass";
    filter.Q.setValueAtTime(2.2, safeStart);
    if (chased) {
      filter.frequency.setValueAtTime(Math.max(600, freq * 2.8), safeStart);
    } else {
      filter.frequency.setValueAtTime(Math.min(9200, freq * 8.5), safeStart);
      filter.frequency.exponentialRampToValueAtTime(
        Math.max(600, freq * 2.6),
        safeStart + Math.min(0.22, safeDur)
      );
    }

    const peak = velNorm * 0.24 * clipGainLinear;
    amp.gain.setValueAtTime(0.0001, safeStart);
    amp.gain.linearRampToValueAtTime(peak, safeStart + 0.006);
    amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak * 0.56), safeStart + Math.min(0.16, safeDur));
    amp.gain.setValueAtTime(Math.max(0.0002, peak * 0.56), safeStart + safeDur);
    amp.gain.linearRampToValueAtTime(0.0001, stopTime);

    oscL.connect(filter);
    oscR.connect(filter);
    filter.connect(amp);
    amp.connect(destination);

    oscL.start(safeStart);
    oscR.start(safeStart);
    oscL.stop(stopTime + 0.01);
    oscR.stop(stopTime + 0.01);
    return [oscL, oscR];
  }

  if (inst === "keys-electric-ep") {
    const release = 0.22;
    const stopTime = safeStart + safeDur + release;
    const body = ctx.createOscillator();
    const tine = ctx.createOscillator();
    const tineGain = ctx.createGain();
    const amp = ctx.createGain();

    body.type = "sine";
    body.frequency.setValueAtTime(freq, safeStart);
    tine.type = "sine";
    tine.frequency.setValueAtTime(freq * 3, safeStart);

    tineGain.gain.setValueAtTime(chased ? 0.02 : 0.28, safeStart);
    tineGain.gain.exponentialRampToValueAtTime(0.005, safeStart + 0.14);

    const peak = velNorm * 0.22 * clipGainLinear;
    amp.gain.setValueAtTime(0.0001, safeStart);
    amp.gain.linearRampToValueAtTime(peak, safeStart + 0.004);
    amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak * 0.42), safeStart + Math.min(0.45, safeDur));
    amp.gain.setValueAtTime(Math.max(0.0002, peak * 0.42), safeStart + safeDur);
    amp.gain.linearRampToValueAtTime(0.0001, stopTime);

    body.connect(amp);
    tine.connect(tineGain);
    tineGain.connect(amp);
    amp.connect(destination);

    body.start(safeStart);
    tine.start(safeStart);
    body.stop(stopTime + 0.01);
    tine.stop(stopTime + 0.01);
    return [body, tine];
  }

  if (inst === "guitar-clean-pluck") {
    const release = 0.18;
    const stopTime = safeStart + safeDur + release;
    const osc = ctx.createOscillator();
    const filter = ctx.createBiquadFilter();
    const amp = ctx.createGain();

    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(freq, safeStart);
    filter.type = "lowpass";
    filter.frequency.setValueAtTime(Math.min(7200, freq * 7.5), safeStart);
    filter.frequency.exponentialRampToValueAtTime(Math.max(380, freq * 1.6), safeStart + 0.18);
    filter.Q.setValueAtTime(0.8, safeStart);

    const peak = velNorm * 0.24 * clipGainLinear;
    amp.gain.setValueAtTime(0.0001, safeStart);
    amp.gain.linearRampToValueAtTime(peak, safeStart + 0.003);
    amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak * 0.28), safeStart + Math.min(0.24, safeDur));
    amp.gain.setValueAtTime(Math.max(0.0002, peak * 0.28), safeStart + safeDur);
    amp.gain.linearRampToValueAtTime(0.0001, stopTime);

    osc.connect(filter);
    filter.connect(amp);
    amp.connect(destination);

    osc.start(safeStart);
    osc.stop(stopTime + 0.01);
    return [osc];
  }

  if (inst === "pad-warm-analog") {
    const release = 0.36;
    const stopTime = safeStart + safeDur + release;
    const osc1 = ctx.createOscillator();
    const osc2 = ctx.createOscillator();
    const filter = ctx.createBiquadFilter();
    const amp = ctx.createGain();

    osc1.type = "sawtooth";
    osc2.type = "triangle";
    osc1.frequency.setValueAtTime(freq * 0.995, safeStart);
    osc2.frequency.setValueAtTime(freq * 1.005, safeStart);

    filter.type = "lowpass";
    filter.frequency.setValueAtTime(Math.min(2600, freq * 3.0), safeStart);
    filter.Q.setValueAtTime(0.7, safeStart);

    const peak = velNorm * 0.14 * clipGainLinear;
    amp.gain.setValueAtTime(0.0001, safeStart);
    amp.gain.linearRampToValueAtTime(peak, safeStart + (chased ? 0.02 : Math.min(0.14, safeDur * 0.4)));
    amp.gain.setValueAtTime(Math.max(0.0002, peak * 0.82), safeStart + safeDur);
    amp.gain.linearRampToValueAtTime(0.0001, stopTime);

    osc1.connect(filter);
    osc2.connect(filter);
    filter.connect(amp);
    amp.connect(destination);

    osc1.start(safeStart);
    osc2.start(safeStart);
    osc1.stop(stopTime + 0.01);
    osc2.stop(stopTime + 0.01);
    return [osc1, osc2];
  }

  // Fallback: basic-poly-synth
  const release = 0.065;
  const stopTime = safeStart + safeDur + release;
  const oscMain = ctx.createOscillator();
  const oscSub = ctx.createOscillator();
  const filter = ctx.createBiquadFilter();
  const amp = ctx.createGain();

  oscMain.type = "sawtooth";
  oscMain.frequency.setValueAtTime(freq, safeStart);
  oscSub.type = "triangle";
  oscSub.frequency.setValueAtTime(freq, safeStart);

  filter.type = "lowpass";
  if (chased) {
    filter.frequency.setValueAtTime(Math.max(420, freq * 2.4), safeStart);
  } else {
    filter.frequency.setValueAtTime(Math.min(6200, freq * 6), safeStart);
    filter.frequency.exponentialRampToValueAtTime(
      Math.max(420, freq * 2.2),
      safeStart + Math.min(0.25, safeDur)
    );
  }
  filter.Q.setValueAtTime(1.2, safeStart);

  const peakGain = velNorm * 0.22 * clipGainLinear;
  const sustainGain = peakGain * 0.58;
  amp.gain.setValueAtTime(0.0001, safeStart);
  if (chased) {
    amp.gain.linearRampToValueAtTime(Math.max(0.0002, sustainGain), safeStart + 0.006);
  } else {
    amp.gain.linearRampToValueAtTime(peakGain, safeStart + 0.008);
    amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, sustainGain), safeStart + Math.min(0.14, safeDur));
  }
  amp.gain.setValueAtTime(Math.max(0.0002, sustainGain), safeStart + safeDur);
  amp.gain.linearRampToValueAtTime(0.0001, stopTime);

  const subMix = ctx.createGain();
  subMix.gain.value = 0.55;
  oscMain.connect(filter);
  oscSub.connect(subMix);
  subMix.connect(filter);
  filter.connect(amp);
  amp.connect(destination);

  oscMain.start(safeStart);
  oscSub.start(safeStart);
  oscMain.stop(stopTime + 0.01);
  oscSub.stop(stopTime + 0.01);
  return [oscMain, oscSub];
}
