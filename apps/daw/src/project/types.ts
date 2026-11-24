export interface TimeSignature {
  numerator: number;
  denominator: 2 | 4 | 8 | 16;
}

export interface LoopRegion {
  enabled: boolean;
  startBeats: number;
  endBeats: number;
}

export interface SectionMarker {
  id: string;
  name: string;
  startBeats: number;
  endBeats: number;
  color: string;
}

export interface MidiNote {
  id: string;
  pitch: number; // 0-127
  velocity: number; // 1-127
  startBeat: number; // relative to clip start
  durationBeats: number;
}

export interface Clip {
  id: string;
  name: string;
  type: "audio" | "midi";
  assetId: string | null;
  timelineStartBeats: number;
  durationBeats: number;
  sourceOffsetSec: number;
  sourceDurationSec: number;
  loop: boolean;
  loopLengthSec: number | null;
  loopLengthBeats: number | null;
  gainDb: number;
  notes: MidiNote[];
}

export interface Track {
  id: string;
  name: string;
  type: "audio" | "stem" | "midi";
  color: string;
  gainDb: number;
  pan: number; // -1..1
  mute: boolean;
  solo: boolean;
  stemLabel?: string | null;
  instrumentRef: string | null;
  effects: Record<string, unknown>[];
  clips: Clip[];
}

export interface Asset {
  id: string;
  name: string;
  kind: "audio" | "midi" | "reference";
  relativePath: string;
  source: string;
  provenance: string;
  sha256: string;
  sampleRate: number;
  channels: number;
  durationSec: number;
  durationSamples: number;
  durationBeats: number | null;
  mimeType: string;
}

export interface Project {
  id: string;
  schemaVersion: string;
  name: string;
  bpm: number;
  timeSignature: TimeSignature;
  ppq: number;
  sampleRate: number;
  lengthBeats: number;
  masterGainDb: number;
  loopRegion: LoopRegion;
  sections: SectionMarker[];
  assets: Asset[];
  tracks: Track[];
  notes: string;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  bpm: number;
  timeSignature: TimeSignature;
  trackCount: number;
  assetCount: number;
  lengthBeats: number;
  updatedAt: string;
  createdAt: string;
  hasAutosave: boolean;
}

export interface WaveformData {
  sampleRate: number;
  channels: number;
  durationSamples: number;
  durationSec: number;
  bins: number;
  peaks: number[];
  rms: number[];
}

export interface LibraryItem {
  id: string;
  name: string;
  category: string;
  kind: "audio" | "midi";
  sizeBytes: number;
}

export interface SelectionContext {
  selectedTrackId: string | null;
  selectedClipIds: string[];
  timeRangeBeats: { startBeats: number; endBeats: number } | null;
  selectedSectionId: string | null;
}

export interface TrackMeterLevel {
  peakL: number;
  peakR: number;
  rmsL: number;
  rmsR: number;
  clipping: boolean;
}

export interface HealthInfo {
  status: string;
  product: string;
  phase: string;
  port: number;
  reaper: {
    available: boolean;
    mode: string;
    note: string;
  };
  uiBuilt: boolean;
}
