import type { TimeSignature } from "./types";

export const DEFAULT_PPQ = 480;

export function beatsPerBar(ts: TimeSignature): number {
  return ts.numerator * (4 / ts.denominator);
}

export function beatsToSeconds(beats: number, bpm: number): number {
  return (beats * 60) / bpm;
}

export function secondsToBeats(seconds: number, bpm: number): number {
  return (seconds * bpm) / 60;
}

export function beatsToTicks(beats: number, ppq = DEFAULT_PPQ): number {
  return Math.round(beats * ppq);
}

export function ticksToBeats(ticks: number, ppq = DEFAULT_PPQ): number {
  return ticks / ppq;
}

export function secondsToSamples(seconds: number, sampleRate: number): number {
  return Math.round(seconds * sampleRate);
}

export function snapBeats(beats: number, gridBeats: number, enabled: boolean): number {
  if (!enabled || gridBeats <= 0) return Math.max(0, beats);
  return Math.max(0, Math.round(beats / gridBeats) * gridBeats);
}

export function formatBarBeatTick(beats: number, ts: TimeSignature): string {
  const safe = Math.max(0, beats);
  const bpb = beatsPerBar(ts);
  const bar = Math.floor(safe / bpb) + 1;
  const remBar = safe - (bar - 1) * bpb;
  const beat = Math.floor(remBar) + 1;
  const sixteenth = Math.floor((remBar - Math.floor(remBar)) * 4) + 1;
  return `${String(bar).padStart(3, "0")}.${beat}.${sixteenth}`;
}

export function formatTimeMs(seconds: number): string {
  const safe = Math.max(0, seconds);
  const mins = Math.floor(safe / 60);
  const secs = Math.floor(safe % 60);
  const ms = Math.floor((safe - Math.floor(safe)) * 100);
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(ms).padStart(2, "0")}`;
}

export function formatBarRange(startBeats: number, endBeats: number, ts: TimeSignature): string {
  const bpb = beatsPerBar(ts);
  const startBar = Math.floor(startBeats / bpb) + 1;
  const endBar = Math.max(startBar, Math.ceil(endBeats / bpb));
  return startBar === endBar ? `Bar ${startBar}` : `Bars ${startBar}–${endBar}`;
}

export function dbToLinear(db: number): number {
  if (db <= -60) return 0;
  return Math.pow(10, db / 20);
}

export function linearToDb(linear: number): number {
  if (linear <= 1e-6) return -60;
  return Math.max(-60, 20 * Math.log10(linear));
}

export function formatDb(db: number): string {
  if (db <= -60) return "-∞ dB";
  return `${db >= 0 ? "+" : ""}${db.toFixed(1)} dB`;
}

export function formatPan(pan: number): string {
  if (Math.abs(pan) < 0.02) return "C";
  const pct = Math.round(Math.abs(pan) * 100);
  return pan < 0 ? `L${pct}` : `R${pct}`;
}

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

export function midiPitchToName(pitch: number): string {
  const clamped = Math.max(0, Math.min(127, Math.round(pitch)));
  const octave = Math.floor(clamped / 12) - 1;
  return `${NOTE_NAMES[clamped % 12]}${octave}`;
}

export function isBlackKey(pitch: number): boolean {
  const pc = ((pitch % 12) + 12) % 12;
  return pc === 1 || pc === 3 || pc === 6 || pc === 8 || pc === 10;
}
