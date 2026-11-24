import { scheduleInstrumentVoice } from "./instruments";

/**
 * Shared multi-timbre synth voice used by BOTH Realtime Web Audio playback
 * and OfflineAudioContext WAV export so preview and export sound identical.
 */
export function scheduleSynthVoice(
  ctx: BaseAudioContext,
  destination: AudioNode,
  pitch: number,
  velocity: number,
  startTime: number,
  durationSec: number,
  clipGainLinear = 1.0,
  chased = false,
  instrumentRef?: string | null
): AudioScheduledSourceNode[] {
  return scheduleInstrumentVoice(
    ctx,
    destination,
    instrumentRef,
    pitch,
    velocity,
    startTime,
    durationSec,
    clipGainLinear,
    chased
  );
}
