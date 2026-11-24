/**
 * Shared basic polyphonic synth voice used by BOTH Realtime Web Audio playback
 * and OfflineAudioContext WAV export so preview and export sound identical.
 * Supports `chased: true` for smooth mid-note MIDI Chase re-entry.
 */
export function scheduleSynthVoice(
  ctx: BaseAudioContext,
  destination: AudioNode,
  pitch: number,
  velocity: number,
  startTime: number,
  durationSec: number,
  clipGainLinear = 1.0,
  chased = false
): OscillatorNode[] {
  const freq = 440 * Math.pow(2, (pitch - 69) / 12);
  const safeStart = Math.max(ctx.currentTime, startTime);
  const safeDur = Math.max(0.025, durationSec);
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
    // Sustained timbre when chasing mid-note (skip percussive attack sweep)
    filter.frequency.setValueAtTime(Math.max(420, freq * 2.4), safeStart);
  } else {
    filter.frequency.setValueAtTime(Math.min(6200, freq * 6), safeStart);
    filter.frequency.exponentialRampToValueAtTime(
      Math.max(420, freq * 2.2),
      safeStart + Math.min(0.25, safeDur)
    );
  }
  filter.Q.setValueAtTime(1.2, safeStart);

  const peakGain = (Math.max(1, Math.min(127, velocity)) / 127) * 0.22 * clipGainLinear;
  const sustainGain = peakGain * 0.58;

  amp.gain.setValueAtTime(0.0001, safeStart);
  if (chased) {
    amp.gain.linearRampToValueAtTime(Math.max(0.0002, sustainGain), safeStart + 0.006);
  } else {
    amp.gain.linearRampToValueAtTime(peakGain, safeStart + 0.008);
    amp.gain.exponentialRampToValueAtTime(
      Math.max(0.0002, sustainGain),
      safeStart + Math.min(0.14, safeDur)
    );
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
