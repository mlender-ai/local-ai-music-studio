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

export interface ReferenceSection {
  id: string;
  label: string;
  startSec: number;
  endSec: number;
  startBar: number;
  endBar: number;
  energyDbfs: number;
  relativeEnergy: number;
  isEstimatedRole: boolean;
}

export interface ReferenceAnalysis {
  analysisVersion: string;
  sourceAssetId: string;
  sha256: string;
  analyzedAt: string;
  fromCache: boolean;
  durationSec: number;
  rhythm: {
    measuredPulseBpm?: number | null;
    estimatedBpm: number | null;
    adoptedTempoBpm?: number | null;
    projectBpm?: number | null;
    candidates: Array<{ bpm: number; strength: number; relation?: string }>;
    halfDoubleAmbiguous: boolean;
    halfDoubleRelation?: string | null;
    confidence?: number;
    meterEstimate: string;
    onsetDensityPerSec: number;
    swingRatio: number;
    grooveFeel?: string;
    regularity: number;
    rhythmicMotifRegularity?: number;
    accentPattern: number[];
    assessment: string;
  };
  harmony: {
    estimatedKey: string;
    modeCandidates: Array<{ key: string; root: string; mode: string; score: number }>;
    chromaMean: number[];
    chordProgression: Array<{
      bar: number;
      startSec: number;
      endSec: number;
      chord: string;
      confidence: number;
      isEstimate: boolean;
    }>;
    harmonicChangeTimesSec: number[];
    harmonicRepetitionScore?: number;
    motifRepetitionScore: number;
    melodicMotifStatus?: string;
    instrumentPhraseStatus?: string;
    confidence: number;
    note: string;
  };
  arrangement: {
    durationSec: number;
    sections: ReferenceSection[];
    energyCurve: Array<{ timeSec: number; rmsDbfs: number; normEnergy: number }>;
  };
  sound: {
    measured: {
      sampleRate: number;
      channels: number;
      loudnessStandard?: string;
      integratedLufs?: number;
      shortTermMaxLufs?: number;
      shortTermMedianLufs?: number;
      loudnessRangeLu?: number;
      frequencyBandsPct: Record<string, number>;
      spectralCentroidHz: number;
      spectralFluxMean: number;
      crestFactorDb: number;
      dynamicRangeDb: number;
      approxLufs: number;
      rmsDbfs: number;
      samplePeakDbfs: number;
      truePeakDbtp?: number;
      stereoWidth: number;
      lrCorrelation: number;
      percussiveRatio: number;
      harmonicRatio: number;
    };
    estimated: {
      reverbCharacter: string;
      transientCharacter: string;
      disclaimer: string;
    };
  };
  instrumentation: {
    isEstimated: boolean;
    method: string;
    note: string;
    elements: Array<{ name: string; confidence: number; level: string; status?: string; method?: string }>;
  };
}

export interface ReferenceBlueprint {
  sourceAssetId: string;
  analysisVersion: string;
  tempo: { bpm: number | null; candidates: Array<{ bpm: number; strength: number }>; halfDoubleAmbiguous: boolean };
  meter: string;
  harmonicCharacter: { key: string; sampleChords: string[]; harmonicShiftCount: number };
  grooveProfile: { swingRatio: number; feel: string };
  arrangementTimeline: ReferenceSection[];
  confidence: { tempo: number; harmony: number; overall: number };
  selectedInfluences: string[];
  availableInfluences: Array<{ id: string; labelKo: string; labelEn: string; selected: boolean }>;
  guidanceNote: string;
}

export interface ReferenceItem {
  id: string;
  name: string;
  filename: string | null;
  kind: "audio" | "video" | "url";
  source: string;
  url?: string | null;
  author?: string;
  audioAvailable: boolean;
  sampleRate: number;
  channels: number;
  durationSec: number;
  analysisStatus: "pending" | "completed" | "audio_required";
  noticeKo?: string | null;
  noticeEn?: string | null;
  analysis: ReferenceAnalysis | null;
  blueprint: ReferenceBlueprint | null;
  selectedInfluences: string[];
  createdAt: string;
  updatedAt: string;
}

export interface AnalysisJobStatus {
  jobId: string;
  projectId: string;
  referenceId: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelling" | "cancelled";
  progress: number;
  stage: string;
  error: string | null;
}

export interface ReferenceComparisonResult {
  referenceName: string;
  targetName: string;
  referenceDurationSec: number;
  targetDurationSec: number;
  measuredDeltas: {
    bpmDelta: number | null;
    referenceKey: string;
    targetKey: string;
    frequencyBandsDeltaPct: Record<string, number>;
    crestFactorDeltaDb: number;
    dynamicRangeDeltaDb: number;
    approxLufsDelta: number;
    stereoWidthDelta: number;
    percussiveRatioDelta: number;
    motifRepetitionDelta: number;
  };
  normalizedProgression: Array<{
    phase: string;
    referenceNormEnergy: number;
    targetNormEnergy: number;
    delta: number;
  }>;
  observations: Array<{ category: string; ko: string; en: string }>;
  methodologyNote: string;
}

export interface Project {
  id: string;
  schemaVersion: string;
  revision: number;
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
  references: ReferenceItem[];
  compositionPlans?: CompositionPlan[];
  takes?: Take[];
  notes: string;
  createdAt: string;
  updatedAt: string;
}

export interface ProviderInfo {
  id: string;
  name: string;
  kind: string;
  available: boolean;
  connected: boolean;
  costModel: string;
  requiresApproval: boolean;
  models: string[];
  activeModel: string | null;
  capabilities: string[];
  statusNoteKo: string;
  statusNoteEn: string;
}

export interface ProviderSummary {
  activeProviderId: string;
  activeModel?: string | null;
  providers: ProviderInfo[];
}

export interface GenerationEngineInfo {
  id: string;
  name: string;
  kind: string;
  available: boolean;
  modes: string[];
  honestLabel?: string;
  statusNoteKo: string;
  statusNoteEn: string;
}

export interface ReferenceBinding {
  referenceIds: string[];
  referenceNames: string[];
  selectedInfluences: string[];
  appliedFeatures: Record<string, unknown>;
  unmappedFeatures: string[];
  traceabilityNote: string;
}

export interface PlannedSection {
  name: string;
  startBar: number;
  endBar: number;
  bars: number;
  energy: number;
  activeRoles: string[];
  transitionNote: string;
  source: "planned" | "detected" | "confirmed";
}

export interface CompositionPlan {
  id: string;
  projectId: string;
  createdAt: string;
  instruction: string;
  mode: "full_music" | "instrument_session" | "loop_midi";
  musicalIdentity: {
    title?: string;
    genre?: string;
    mood?: string;
    tempoBpm?: number;
    timeSignature?: string;
    key?: string;
    scale?: string;
    barCount?: number;
    durationSec?: number;
    instrumentalOnly?: boolean;
  };
  signatureMotif: {
    concept?: string;
    scaleDegrees?: number[];
    variationRule?: string;
  };
  harmonyAndGroove: {
    key?: string;
    scale?: string;
    chordProgression?: string[];
    grooveFeel?: string;
    swingRatio?: number;
  };
  instrumentRoles: Array<{
    role: string;
    name: string;
    trackType: string;
    instrumentRef?: string;
    color?: string;
    activeSections?: string[];
  }>;
  arrangement: PlannedSection[];
  variations: string[];
  climax: Record<string, unknown>;
  generationStrategy: Record<string, unknown>;
  referenceBinding: ReferenceBinding;
  providerProvenance: Record<string, unknown>;
  summaryKo: string;
  summaryEn: string;
}

export interface GenerationJobStatus {
  jobId: string;
  projectId: string;
  planId?: string | null;
  takeId?: string | null;
  mode: string;
  engineRequested: string;
  status: string;
  stage: string;
  progress: number;
  error: string | null;
  logs: Array<{ at: string; stage: string; message: string }>;
  createdAt: string;
  updatedAt: string;
}

export interface TakeArtifact {
  role: string;
  name: string;
  trackType: "audio" | "stem" | "midi";
  instrumentRef?: string | null;
  color: string;
  audioRelativePath?: string | null;
  midiRelativePath?: string | null;
  notes: MidiNote[];
  startBeats: number;
  durationBeats: number;
  gainDb: number;
  pan: number;
}

export interface Take {
  id: string;
  projectId: string;
  jobId: string;
  planId?: string | null;
  title: string;
  mode: "full_music" | "instrument_session" | "loop_midi" | "stem_separation";
  status: "ready" | "applied" | "rejected" | "kept";
  previewRelativePath?: string | null;
  previewDurationSec: number;
  previewIntegratedLufs?: number | null;
  levelMatchedGainDb: number;
  targetTrackId?: string | null;
  preserveExistingTracks: boolean;
  plannedSections: PlannedSection[];
  detectedSections: ReferenceSection[];
  artifacts: TakeArtifact[];
  qualityReport: {
    technical: Record<string, unknown>;
    musical: Record<string, unknown>;
    referenceComparison?: ReferenceComparisonResult | null;
    vocalScreening?: Record<string, unknown> | null;
    verdict: "pass" | "warn" | "fail";
    warnings: string[];
    honestyNote?: string;
  };
  provenance: {
    engine: string;
    engineLabel: string;
    mode: string;
    providerId: string;
    model: string;
    seed: number;
    planId?: string | null;
    referenceIds: string[];
    instrumentalPolicy: string;
    generatedAt: string;
  };
  createdAt: string;
  appliedAt?: string | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  revision: number;
  bpm: number;
  timeSignature: TimeSignature;
  trackCount: number;
  assetCount: number;
  lengthBeats: number;
  updatedAt: string;
  createdAt: string;
  hasAutosave: boolean;
}

export interface AssetLoadState {
  status: "loading" | "ready" | "error";
  error?: string;
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

export interface ChangeProposal {
  id: string;
  projectId: string;
  baseRevision: number;
  summary: string;
  sourceAgent: string;
  status: "pending" | "applied" | "rejected";
  operations: Array<{ type: string; payload: Record<string, unknown> }>;
  affectedTracks: string[];
  affectedClipIds: string[];
  operationCount: number;
  createdAt: string;
  resolvedAt?: string | null;
}

export interface ProducerInstructResponse {
  supported: boolean;
  action: string;
  proposal?: ChangeProposal;
  plan?: CompositionPlan;
  projectRevision?: number;
  referenceId?: string;
  messageKo?: string;
  messageEn?: string;
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
