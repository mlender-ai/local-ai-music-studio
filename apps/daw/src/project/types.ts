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

export interface ChordEvent {
  id: string;
  symbol: string;
  root?: string;
  quality?: string;
  extension?: string;
  bassNote?: string | null;
  startBeat: number;
  endBeat: number;
  sourceReferenceId?: string | null;
  confidence?: number;
  isEstimate?: boolean;
  userCorrected?: boolean;
  locked?: boolean;
}

export type FeatureLockState = "free" | "reference" | "locked" | "unsupported";

export interface ReferenceStemItem {
  role: string;
  name: string;
  relativePath: string;
  assetKind: string;
  active: boolean;
  rmsDbfs: number;
  spectralCentroidHz: number;
  attackCharacter: string;
}

export interface ReferenceTranscription {
  transcriptionVersion: string;
  transcribedAt: string;
  fromCache: boolean;
  bpm: number;
  key: string;
  modelsUsed: Array<{ id: string; role: string; license: string }>;
  stemReferences: ReferenceStemItem[];
  chordTimeline: ChordEvent[];
  drums?: {
    hasDrums: boolean;
    sourceKind: string;
    hitCounts: Record<string, number>;
    swingRatio: number;
    grooveFeel: string;
    syncopationScore: number;
    meanMicrotimingMs: number;
    quantizedMidiNotes?: Array<Record<string, unknown>>;
    rawMidiNotes?: Array<Record<string, unknown>>;
  };
  bass?: { noteCount: number; pitchMin: number | null; pitchMax: number | null; meanConfidence: number };
  melody?: { noteCount: number; pitchMin: number | null; pitchMax: number | null; meanConfidence: number };
  arrangementMap?: Array<ReferenceSection & { activeStems?: string[]; enteredStems?: string[]; exitedStems?: string[] }>;
  abcScore?: {
    abc: string;
    validInstrumentalYuE2: boolean;
    issues: string[];
    generator: string;
    productionMode: string;
  };
  limitationsKo?: string[];
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
  fadeInBeats?: number;
  fadeOutBeats?: number;
  reversed?: boolean;
  notes: MidiNote[];
}

export interface TakeLane {
  id: string;
  name: string;
  takeId?: string | null;
  startBeats: number;
  endBeats: number;
  clip?: Clip | null;
  clips?: Clip[];
  isOriginalBackup?: boolean;
  active?: boolean;
  createdAt?: string;
}

export interface EffectSlot {
  id: string;
  type: string;
  name: string;
  nameKo?: string;
  enabled: boolean;
  bypass: boolean;
  wetDry: number;
  preset?: string | null;
  parameters: Record<string, unknown>;
  sidechainTrackId?: string | null;
}

export interface SendSlot {
  id: string;
  busId: string;
  levelDb: number;
  preFader: boolean;
  enabled: boolean;
}

export interface AutomationPoint {
  id: string;
  beat: number;
  value: number;
  interpolation?: "linear" | "step";
}

export interface AutomationLane {
  id: string;
  targetType: "track" | "fx" | "instrument" | "send";
  targetId?: string | null;
  parameterId: string;
  enabled: boolean;
  points: AutomationPoint[];
}

export interface TrackFreezeState {
  frozen: boolean;
  assetId: string;
  stateHash: string;
  frozenAt: string;
  durationSec: number;
  sampleRate?: number;
  fxMeters?: Record<string, Record<string, unknown>>;
}

export interface BusTrack {
  id: string;
  name: string;
  kind: "return" | "group";
  gainDb: number;
  pan: number;
  mute: boolean;
  solo: boolean;
  effects: EffectSlot[];
}

export interface InstrumentCatalogEntry {
  id: string;
  instrumentId: string;
  name: string;
  instrumentName: string;
  nameKo: string;
  category: string;
  role: string;
  engineType: string;
  pluginFormat?: string;
  presetList: Array<{ id: string; name: string; nameKo?: string }>;
  supportedParameters: Array<{
    id: string;
    label: string;
    labelKo?: string;
    min: number;
    max: number;
    default: number;
    unit?: string;
    scale?: string;
  }>;
  supportedArticulations?: string[];
  sampleLibrary?: string | null;
  license?: string;
  runtimeAvailability: string;
  verificationStatus?: string;
  description?: string;
}

export interface FxCatalogEntry {
  type: string;
  name: string;
  nameKo: string;
  category: string;
  engine: string;
  description: string;
  defaultParams: Record<string, unknown>;
  presets: Array<{ id: string; name: string; nameKo?: string; params?: Record<string, unknown> }>;
  cabinets?: Array<{ id: string; name: string }>;
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
  stemMeta?: Record<string, unknown> | null;
  instrumentRef: string | null;
  instrumentConfig?: Record<string, unknown>;
  effects: EffectSlot[];
  sends?: SendSlot[];
  automationLanes?: AutomationLane[];
  freezeState?: TrackFreezeState | null;
  outputBusId?: string;
  clips: Clip[];
  takeLanes?: TakeLane[];
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
    halfDoubleRelation?: string | { lowerBpm: number; upperBpm: number; relation: string } | null;
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
  blueprintVersion?: string;
  tempo: { bpm: number | null; candidates: Array<{ bpm: number; strength: number }>; halfDoubleAmbiguous: boolean };
  meter: string;
  harmonicCharacter: { key: string; sampleChords: string[]; harmonicShiftCount: number; chordEventCount?: number; hasSubBarChanges?: boolean };
  grooveProfile: { swingRatio: number; feel: string; syncopationScore?: number; meanMicrotimingMs?: number };
  arrangementTimeline: ReferenceSection[];
  arrangementMap?: Array<ReferenceSection & { activeStems?: string[]; enteredStems?: string[]; exitedStems?: string[] }>;
  chordTimeline?: ChordEvent[];
  drumEvents?: { transcribed?: boolean; noteCount?: number; hitCounts?: Record<string, number>; fillBars?: number[] };
  bassEvents?: { transcribed?: boolean; noteCount?: number; pitchMin?: number | null; pitchMax?: number | null };
  melodyEvents?: { transcribed?: boolean; noteCount?: number; pitchMin?: number | null; pitchMax?: number | null };
  stemReferences?: ReferenceStemItem[];
  abcScore?: { abc: string; validInstrumentalYuE2: boolean; issues: string[]; generator: string; productionMode: string };
  featureLocks?: Record<string, FeatureLockState>;
  featureLockSpecs?: Array<{ id: string; labelKo: string; labelEn: string; defaultState: FeatureLockState }>;
  confidence: { tempo: number; harmony: number; overall: number; chords?: number };
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
  transcriptionStatus?: "pending" | "completed" | null;
  noticeKo?: string | null;
  noticeEn?: string | null;
  analysis: ReferenceAnalysis | null;
  transcription?: ReferenceTranscription | null;
  blueprint: ReferenceBlueprint | null;
  selectedInfluences: string[];
  featureLocks?: Record<string, FeatureLockState>;
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
  chordTrack?: ChordEvent[];
  chordTrackLocked?: boolean;
  assets: Asset[];
  tracks: Track[];
  buses?: BusTrack[];
  masterEffects?: EffectSlot[];
  references: ReferenceItem[];
  compositionPlans?: CompositionPlan[];
  takes?: Take[];
  musicMemory?: Record<string, unknown>;
  notes: string;
  createdAt: string;
  updatedAt: string;
}

export interface ProviderInfo {
  id: string;
  name: string;
  kind: string;
  providerState?: "uninstalled" | "detected" | "authenticated" | "verified" | "ready_for_client";
  status?: "uninstalled" | "detected" | "authenticated" | "verified" | "ready_for_client";
  available: boolean;
  connected: boolean;
  authenticated?: boolean;
  verified?: boolean;
  costModel: string;
  requiresApproval: boolean;
  models: string[];
  activeModel: string | null;
  capabilities: string[];
  statusNoteKo: string;
  statusNoteEn: string;
}

export interface RuntimeEngineEntry {
  id: string;
  name: string;
  kind: string;
  state: "uninstalled" | "binary_found" | "model_found" | "ready" | "verified" | "failed";
  available: boolean;
  verified: boolean;
  statusNoteKo: string;
  statusNoteEn: string;
}

export interface RuntimeRegistryInfo {
  configPath: string;
  neuralAudioReady: boolean;
  editableMidiReady: boolean;
  stemSeparationReady: boolean;
  transcriptionReady?: boolean;
  engines: RuntimeEngineEntry[];
}

export interface ArrangementEditScope {
  projectId: string;
  baseRevision: number;
  targetTrackIds: string[];
  targetClipIds: string[];
  startBeats: number;
  endBeats: number;
  startBar: number;
  endBarInclusive: number;
  selectionType: "range" | "clip" | "section" | "track";
  requestedOperation: string;
  preservedTrackIds: string[];
  preservedSections: string[];
  harmonicContext: Record<string, unknown>;
  adjacentContext: Record<string, unknown>;
}

export interface ArrangementEditPlan {
  id: string;
  createdAt: string;
  instruction: string;
  operation:
    | "replace_range"
    | "alternative_take"
    | "add_layer"
    | "strip_to_tracks"
    | "extend_section"
    | "audio_reverse"
    | "audio_fade";
  variationKind: string;
  intensity: "subtle" | "moderate" | "creative";
  scope: ArrangementEditScope;
  preservePitch: boolean;
  preserveHarmony: boolean;
  preserveFirstHalf: boolean;
  addTurnaroundFill: boolean;
  keepTrackIds: string[];
  extendBars: number;
  changes: string[];
  providerProvenance: Record<string, unknown>;
  summaryKo: string;
  summaryEn: string;
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
  mode: "full_music" | "instrument_session" | "loop_midi" | "stem_separation" | "midi_variation";
  status: "ready" | "applied" | "rejected" | "kept";
  previewRelativePath?: string | null;
  previewDurationSec: number;
  previewIntegratedLufs?: number | null;
  levelMatchedGainDb: number;
  targetTrackId?: string | null;
  targetRangeBeats?: { startBeats: number; endBeats: number } | null;
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
  arrangementPlan?: ArrangementEditPlan;
  job?: AnalysisJobStatus;
  project?: Project;
  reconstructResult?: Record<string, unknown>;
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
