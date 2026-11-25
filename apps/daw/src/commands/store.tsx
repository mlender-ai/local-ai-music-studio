import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { audioEngine } from "../audio/audioEngine";
import { renderProjectOfflineWav } from "../audio/offlineRenderer";
import { dawApi, RevisionConflictError } from "../project/api";
import { secondsToBeats } from "../project/time";
import type {
  AnalysisJobStatus,
  ArrangementEditPlan,
  Asset,
  AssetLoadState,
  ChangeProposal,
  ChordEvent,
  Clip,
  CompositionPlan,
  GenerationEngineInfo,
  GenerationJobStatus,
  HealthInfo,
  LibraryItem,
  MidiNote,
  ProducerInstructResponse,
  Project,
  ProjectSummary,
  ProviderSummary,
  ReferenceItem,
  RuntimeRegistryInfo,
  SelectionContext,
  Take,
  Track,
  TrackMeterLevel,
  WaveformData,
} from "../project/types";
import { executeCommand, makeClientId } from "./executor";
import { NON_UNDOABLE_COMMANDS, type ProjectCommand } from "./types";

const MAX_HISTORY = 100;
const WORKSPACE_PREFS_KEY = "ai_native_daw_workspace_v1";

interface WorkspacePrefs {
  lastProjectId?: string;
  lastTrackId?: string | null;
  lastPlayheadBeats?: number;
  pixelsPerBeat?: number;
  browserOpen?: boolean;
  producerOpen?: boolean;
  dockOpen?: boolean;
}

export function loadWorkspacePrefs(): WorkspacePrefs {
  try {
    const raw = window.localStorage.getItem(WORKSPACE_PREFS_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as WorkspacePrefs;
  } catch {
    return {};
  }
}

export function saveWorkspacePrefs(patch: Partial<WorkspacePrefs>): void {
  try {
    const prev = loadWorkspacePrefs();
    window.localStorage.setItem(WORKSPACE_PREFS_KEY, JSON.stringify({ ...prev, ...patch }));
  } catch {
    // ignore storage errors
  }
}

/** Deterministic structural fingerprint ignoring revision & updatedAt timestamps. */
export function projectFingerprint(project: Project): string {
  const { revision: _rev, updatedAt: _upd, ...rest } = project;
  return JSON.stringify(rest);
}

interface ToastState {
  message: string;
  kind: "info" | "error";
}

export interface ConflictNotice {
  expectedRevision: number;
  serverRevision: number;
  serverProject: Project;
}

interface DawContextValue {
  project: Project | null;
  recentProjects: ProjectSummary[];
  libraryItems: LibraryItem[];
  health: HealthInfo | null;
  waveforms: Record<string, WaveformData>;
  assetStates: Record<string, AssetLoadState>;
  selection: SelectionContext;
  setSelection: React.Dispatch<React.SetStateAction<SelectionContext>>;
  selectedTrack: Track | null;
  selectedClip: Clip | null;
  isDirty: boolean;
  isSaving: boolean;
  isExporting: boolean;
  lastSavedAt: string | null;
  savedRevision: number;
  revisionConflict: ConflictNotice | null;
  resolveConflictReload: () => Promise<void>;
  resolveConflictOverwrite: () => Promise<void>;
  dismissConflict: () => void;
  canUndo: boolean;
  canRedo: boolean;
  isPlaying: boolean;
  playheadBeats: number;
  trackMeters: Record<string, TrackMeterLevel>;
  masterMeter: TrackMeterLevel;
  snapEnabled: boolean;
  setSnapEnabled: (v: boolean) => void;
  gridBeats: number;
  setGridBeats: (v: number) => void;
  pixelsPerBeat: number;
  setPixelsPerBeat: React.Dispatch<React.SetStateAction<number>>;
  toast: ToastState | null;
  showToast: (message: string, kind?: "info" | "error") => void;
  dispatch: (cmd: ProjectCommand, options?: { recordHistory?: boolean }) => void;
  beginTransaction: () => void;
  commitTransaction: () => void;
  undo: () => void;
  redo: () => void;
  playPause: () => Promise<void>;
  stop: () => void;
  seek: (beats: number) => void;
  resetMasterClip: () => void;
  openProjectById: (id: string, options?: { force?: boolean }) => Promise<void>;
  createNewProject: (name: string, bpm?: number) => Promise<void>;
  saveCurrentProject: (options?: { forceOverwrite?: boolean }) => Promise<void>;
  saveAsProject: (newName: string) => Promise<void>;
  importFile: (file: File, kind?: "audio" | "midi" | "reference", addToTimeline?: boolean) => Promise<void>;
  importLibraryAsset: (item: LibraryItem, addToTimeline?: boolean) => Promise<void>;
  addAssetToTimeline: (asset: Asset, targetTrackId?: string, startBeats?: number, midiNotes?: MidiNote[]) => void;
  retryAssetLoad: (assetId: string) => Promise<void>;
  relinkAssetFile: (assetId: string, file: File) => Promise<void>;
  exportStereoWav: (useLoopRange?: boolean) => Promise<void>;
  applyExternalProjectUpdate: (updated: Project, message?: string) => void;
  refreshLists: () => Promise<ProjectSummary[]>;
  activeReferenceId: string | null;
  setActiveReferenceId: (id: string | null) => void;
  activeReference: ReferenceItem | null;
  activeAnalysisJob: AnalysisJobStatus | null;
  importReferenceFile: (file: File) => Promise<ReferenceItem | null>;
  attachAudioToReference: (refId: string, file: File) => Promise<void>;
  addReferenceUrl: (url: string) => Promise<ReferenceItem | null>;
  deleteReference: (refId: string) => Promise<void>;
  runReferenceAnalysis: (refId: string) => Promise<void>;
  runReferenceTranscription: (refId: string, useDemucs?: boolean) => Promise<void>;
  cancelReferenceAnalysis: () => Promise<void>;
  toggleBlueprintInfluence: (refId: string, influenceId: string) => Promise<void>;
  updateReferenceLocks: (
    refId: string,
    body: { featureLocks?: Record<string, string>; chordCorrections?: ChordEvent[] }
  ) => Promise<void>;
  reconstructReference: (
    refId: string,
    opts?: {
      importChords?: boolean;
      importDrumsMidi?: boolean;
      importBassMidi?: boolean;
      importMelodyMidi?: boolean;
      importStems?: boolean;
      importSections?: boolean;
      applyBpm?: boolean;
    }
  ) => Promise<void>;
  sessionId: string;
  sseConnected: boolean;
  pendingProposals: ChangeProposal[];
  applyPendingProposal: (proposalId: string) => Promise<void>;
  rejectPendingProposal: (proposalId: string) => Promise<void>;
  submitProducerInstruction: (instruction: string) => Promise<ProducerInstructResponse | null>;
  // Phase 03 / 03.1 / 04 AI Composition, Engine Recovery & Selective Arrangement
  providerSummary: ProviderSummary | null;
  generationEngines: GenerationEngineInfo[];
  runtimeRegistry: RuntimeRegistryInfo | null;
  activePlan: CompositionPlan | null;
  setActivePlan: (plan: CompositionPlan | null) => void;
  activeArrangementPlan: ArrangementEditPlan | null;
  setActiveArrangementPlan: (plan: ArrangementEditPlan | null) => void;
  engineUnavailableNotice: { requestedEngine: string; errorKo: string; errorEn: string; plan: CompositionPlan } | null;
  dismissEngineUnavailableNotice: () => void;
  activeGenerationJob: GenerationJobStatus | null;
  takes: Take[];
  selectAiProvider: (providerId: string) => Promise<void>;
  requestCompositionPlan: (
    instruction: string,
    opts?: {
      mode?: string;
      targetInstrument?: string;
      useReference?: boolean;
      enginePreference?: string;
      featureLocks?: Record<string, string>;
      referenceMode?: "reconstruct" | "reference_compose" | "reinterpret";
      useProjectChordTrack?: boolean;
    }
  ) => Promise<CompositionPlan | null>;
  startGenerationFromPlan: (plan: CompositionPlan, engine?: string) => Promise<boolean>;
  cancelActiveGeneration: () => Promise<void>;
  applyGeneratedTake: (
    takeId: string,
    applyMode:
      | "add"
      | "new_tracks"
      | "replace_range"
      | "selected_range"
      | "alternative_take"
      | "extend"
      | "new_project"
      | "keep_take",
    targetTrackId?: string | null
  ) => Promise<void>;
  rejectGeneratedTake: (takeId: string) => Promise<void>;
  requestArrangementPlan: (
    instruction: string,
    opts?: { intensity?: "subtle" | "moderate" | "creative"; targetTrackId?: string | null }
  ) => Promise<ArrangementEditPlan | null>;
  executeArrangementPlan: (
    plan: ArrangementEditPlan,
    opts?: { intensity?: "subtle" | "moderate" | "creative"; seed?: number }
  ) => Promise<{ take?: Take; applied?: boolean; messageKo?: string } | null>;
  promoteTakeLane: (
    trackId: string,
    laneId: string,
    range?: { startBeats: number; endBeats: number }
  ) => Promise<void>;
  restoreOriginalTakeLane: (trackId: string, laneId?: string) => Promise<void>;
  renameTakeLane: (trackId: string, laneId: string, name: string) => Promise<void>;
  reverseAudioClip: (clipId: string) => Promise<void>;
}

const DawContext = createContext<DawContextValue | null>(null);

const EMPTY_METER: TrackMeterLevel = { peakL: 0, peakR: 0, rmsL: 0, rmsR: 0, clipping: false };

export function DawProvider({ children }: { children: React.ReactNode }) {
  const initialPrefs = useMemo(() => loadWorkspacePrefs(), []);

  const [project, setProject] = useState<Project | null>(null);
  const [recentProjects, setRecentProjects] = useState<ProjectSummary[]>([]);
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [waveforms, setWaveforms] = useState<Record<string, WaveformData>>({});
  const [assetStates, setAssetStates] = useState<Record<string, AssetLoadState>>({});
  const [selection, setSelection] = useState<SelectionContext>({
    selectedTrackId: null,
    selectedClipIds: [],
    timeRangeBeats: null,
    selectedSectionId: null,
  });

  const [past, setPast] = useState<Project[]>([]);
  const [future, setFuture] = useState<Project[]>([]);
  const [savedFingerprint, setSavedFingerprint] = useState<string>("");
  const [savedRevision, setSavedRevision] = useState<number>(1);
  const [revisionConflict, setRevisionConflict] = useState<ConflictNotice | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [playheadBeats, setPlayheadBeats] = useState(0);
  const [trackMeters, setTrackMeters] = useState<Record<string, TrackMeterLevel>>({});
  const [masterMeter, setMasterMeter] = useState<TrackMeterLevel>(EMPTY_METER);

  const [snapEnabled, setSnapEnabled] = useState(true);
  const [gridBeats, setGridBeats] = useState(1);
  const [pixelsPerBeat, setPixelsPerBeat] = useState(initialPrefs.pixelsPerBeat ?? 15);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [activeReferenceId, setActiveReferenceId] = useState<string | null>(null);
  const [activeAnalysisJob, setActiveAnalysisJob] = useState<AnalysisJobStatus | null>(null);
  const [sessionId] = useState(() => makeClientId("sess"));
  const [sseConnected, setSseConnected] = useState(false);
  const [pendingProposals, setPendingProposals] = useState<ChangeProposal[]>([]);
  const [providerSummary, setProviderSummary] = useState<ProviderSummary | null>(null);
  const [generationEngines, setGenerationEngines] = useState<GenerationEngineInfo[]>([]);
  const [runtimeRegistry, setRuntimeRegistry] = useState<RuntimeRegistryInfo | null>(null);
  const [activePlan, setActivePlan] = useState<CompositionPlan | null>(null);
  const [activeArrangementPlan, setActiveArrangementPlan] = useState<ArrangementEditPlan | null>(null);
  const [engineUnavailableNotice, setEngineUnavailableNotice] = useState<{
    requestedEngine: string;
    errorKo: string;
    errorEn: string;
    plan: CompositionPlan;
  } | null>(null);
  const [activeGenerationJob, setActiveGenerationJob] = useState<GenerationJobStatus | null>(null);

  const projectRef = useRef<Project | null>(null);
  projectRef.current = project;
  const savedRevisionRef = useRef<number>(1);
  savedRevisionRef.current = savedRevision;
  const txSnapshotRef = useRef<Project | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  const midiNotesCacheRef = useRef<Map<string, MidiNote[]>>(new Map());
  const saveInFlightRef = useRef(false);

  const isDirty = useMemo(() => {
    if (!project) return false;
    return projectFingerprint(project) !== savedFingerprint;
  }, [project, savedFingerprint]);

  const showToast = useCallback((message: string, kind: "info" | "error" = "info") => {
    setToast({ message, kind });
    if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => setToast(null), kind === "error" ? 5500 : 3000);
  }, []);

  // Subscribe to real audio decode statuses from audioEngine
  useEffect(() => {
    return audioEngine.subscribeAssetStates(() => {
      const pid = projectRef.current?.id;
      if (pid) {
        setAssetStates(audioEngine.getAssetStates(pid));
      }
    });
  }, []);

  // Warn before closing tab if unsaved changes exist
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  // Persist workspace preferences (zoom, last track, playhead)
  useEffect(() => {
    saveWorkspacePrefs({ pixelsPerBeat });
  }, [pixelsPerBeat]);

  useEffect(() => {
    if (project) {
      saveWorkspacePrefs({
        lastProjectId: project.id,
        lastTrackId: selection.selectedTrackId,
      });
    }
  }, [project?.id, selection.selectedTrackId]);

  const refreshLists = useCallback(async () => {
    try {
      const [projList, libList] = await Promise.all([dawApi.listProjects(), dawApi.listLibrary()]);
      setRecentProjects(projList.projects);
      setLibraryItems(libList.items);
      return projList.projects;
    } catch (err) {
      showToast(`Failed to list projects: ${(err as Error).message}`, "error");
      return [];
    }
  }, [showToast]);

  const loadWaveformsForProject = useCallback(async (proj: Project) => {
    const audioAssets = proj.assets.filter((a) => a.kind !== "midi");
    const results: Record<string, WaveformData> = {};
    await Promise.all(
      audioAssets.map(async (asset) => {
        try {
          const wf = await dawApi.getWaveform(proj.id, asset.id, 1024);
          if (wf.peaks && wf.peaks.length > 0) {
            results[asset.id] = wf;
            return;
          }
        } catch {
          // fallback to Web Audio decode below
        }
        try {
          const buf = await audioEngine.loadAssetBuffer(proj.id, asset.id);
          results[asset.id] = audioEngine.extractWaveformFromBuffer(buf, 1024);
        } catch {
          // error state is tracked in audioEngine.assetStates
        }
      })
    );
    setWaveforms(results);
    setAssetStates(audioEngine.getAssetStates(proj.id));
  }, []);

  const hydrateProject = useCallback(
    async (loaded: Project, restoreSessionState = false) => {
      audioEngine.stop();
      setIsPlaying(false);
      const prefs = restoreSessionState ? loadWorkspacePrefs() : {};
      const restoredPlayhead =
        restoreSessionState &&
        prefs.lastProjectId === loaded.id &&
        typeof prefs.lastPlayheadBeats === "number"
          ? Math.max(0, Math.min(loaded.lengthBeats, prefs.lastPlayheadBeats))
          : 0;

      audioEngine.seek(restoredPlayhead);
      setPlayheadBeats(restoredPlayhead);
      setProject(loaded);
      setPast([]);
      setFuture([]);
      setSavedFingerprint(projectFingerprint(loaded));
      setSavedRevision(loaded.revision ?? 1);
      setRevisionConflict(null);
      setLastSavedAt(loaded.updatedAt);
      setActiveReferenceId(loaded.references?.[0]?.id ?? null);
      const loadedPlans = loaded.compositionPlans ?? [];
      setActivePlan(loadedPlans.length > 0 ? loadedPlans[loadedPlans.length - 1] : null);

      const restoredTrack =
        restoreSessionState && prefs.lastTrackId
          ? loaded.tracks.find((t) => t.id === prefs.lastTrackId) ?? null
          : null;
      const firstAudioTrack = loaded.tracks.find((t) => t.clips.length > 0) ?? loaded.tracks[0] ?? null;
      const featuredClip =
        restoredTrack?.clips[0] ??
        loaded.tracks.find((t) => t.id === "trk_guitar")?.clips[1] ??
        firstAudioTrack?.clips[0] ??
        null;
      const featuredTrackId =
        restoredTrack?.id ??
        (featuredClip
          ? loaded.tracks.find((t) => t.clips.some((c) => c.id === featuredClip.id))?.id ??
            firstAudioTrack?.id ??
            null
          : firstAudioTrack?.id ?? null);

      setSelection({
        selectedTrackId: featuredTrackId,
        selectedClipIds: featuredClip ? [featuredClip.id] : [],
        timeRangeBeats: featuredClip
          ? {
              startBeats: featuredClip.timelineStartBeats,
              endBeats: featuredClip.timelineStartBeats + featuredClip.durationBeats,
            }
          : null,
        selectedSectionId: loaded.sections[1]?.id ?? loaded.sections[0]?.id ?? null,
      });

      audioEngine.syncProject(loaded);
      void loadWaveformsForProject(loaded);
    },
    [loadWaveformsForProject]
  );

  // Initial boot: restore last worked project first, falling back to demos / new project
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [h, provs, engs, rt] = await Promise.all([
          dawApi.health(),
          dawApi.getProviders().catch(() => null),
          dawApi.getGenerationEngines().catch(() => null),
          dawApi.getRuntimeRegistry().catch(() => null),
        ]);
        if (active) {
          setHealth(h);
          if (provs) setProviderSummary(provs);
          if (engs) setGenerationEngines(engs.engines);
          if (rt) setRuntimeRegistry(rt);
        }
      } catch {
        // backend unavailable warning handled below
      }
      const list = await refreshLists();
      if (!active) return;
      if (list.length > 0) {
        const prefs = loadWorkspacePrefs();
        const preferred =
          (prefs.lastProjectId ? list.find((p) => p.id === prefs.lastProjectId) : undefined) ??
          list.find((p) => p.id === "demo_multitrack_session") ??
          list.find((p) => p.id === "demo_v72_magnetic_afterhours") ??
          list[0];
        try {
          const opened = await dawApi.openProject(preferred.id);
          if (active) await hydrateProject(opened, true);
        } catch (err) {
          showToast(`Failed to open project: ${(err as Error).message}`, "error");
        }
      } else {
        try {
          const created = await dawApi.createProject({ name: "Untitled 01", bpm: 128 });
          if (active) {
            await hydrateProject(created, false);
            await refreshLists();
          }
        } catch (err) {
          showToast(`Backend unreachable: ${(err as Error).message}`, "error");
        }
      }
    })();
    return () => {
      active = false;
      audioEngine.stop();
    };
  }, [hydrateProject, refreshLists, showToast]);

  useEffect(() => {
    if (project) {
      audioEngine.syncProject(project);
    }
  }, [project]);

  // Real-time rAF playhead & AnalyserNode meter loop
  useEffect(() => {
    let rafId = 0;
    const tick = () => {
      const playingNow = audioEngine.isPlaying;
      setIsPlaying((prev) => (prev !== playingNow ? playingNow : prev));
      if (playingNow) {
        setPlayheadBeats(audioEngine.getPlayheadBeats());
        const m = audioEngine.readMeters();
        setTrackMeters(m.tracks);
        setMasterMeter(m.master);
      }
      rafId = window.requestAnimationFrame(tick);
    };
    rafId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(rafId);
  }, []);

  // Periodic debounced autosave (respects expectedRevision so external agent edits are never clobbered)
  useEffect(() => {
    if (!isDirty || !project || saveInFlightRef.current || revisionConflict) return;
    const timer = window.setTimeout(() => {
      const current = projectRef.current;
      if (current && !saveInFlightRef.current) {
        void dawApi
          .autosaveProject(current, savedRevisionRef.current)
          .catch((err) => {
            if (err instanceof RevisionConflictError) {
              setRevisionConflict({
                expectedRevision: savedRevisionRef.current,
                serverRevision: err.serverRevision,
                serverProject: err.serverProject,
              });
            }
          });
      }
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [isDirty, project, revisionConflict]);

  const beginTransaction = useCallback(() => {
    if (!txSnapshotRef.current && projectRef.current) {
      txSnapshotRef.current = JSON.parse(JSON.stringify(projectRef.current)) as Project;
    }
  }, []);

  const commitTransaction = useCallback(() => {
    if (txSnapshotRef.current) {
      const snap = txSnapshotRef.current;
      txSnapshotRef.current = null;
      setPast((prev) => [...prev.slice(-(MAX_HISTORY - 1)), snap]);
      setFuture([]);
    }
  }, []);

  const dispatch = useCallback(
    (cmd: ProjectCommand, options?: { recordHistory?: boolean }) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const next = executeCommand(current, cmd);
        const shouldRecord =
          options?.recordHistory !== undefined
            ? options.recordHistory
            : !NON_UNDOABLE_COMMANDS.has(cmd.type) && !txSnapshotRef.current;

        if (shouldRecord) {
          setPast((prev) => [...prev.slice(-(MAX_HISTORY - 1)), current]);
          setFuture([]);
        }
        // Keep ref synchronously updated so back-to-back dispatches in the same handler never drop earlier commands!
        projectRef.current = next;
        setProject(next);

        if (
          audioEngine.isPlaying &&
          (cmd.type.startsWith("clip.") || cmd.type.startsWith("midi.") || cmd.type === "track.remove")
        ) {
          audioEngine.syncProject(next);
          audioEngine.resyncActivePlayback();
        }
      } catch (err) {
        showToast((err as Error).message, "error");
      }
    },
    [showToast]
  );

  const undo = useCallback(() => {
    setPast((prev) => {
      if (prev.length === 0 || !projectRef.current) return prev;
      const previous = prev[prev.length - 1];
      const current = projectRef.current;
      setFuture((f) => [current, ...f.slice(0, MAX_HISTORY - 1)]);
      setProject(previous);
      if (audioEngine.isPlaying) {
        audioEngine.syncProject(previous);
        audioEngine.resyncActivePlayback();
      }
      return prev.slice(0, -1);
    });
  }, []);

  const redo = useCallback(() => {
    setFuture((prev) => {
      if (prev.length === 0 || !projectRef.current) return prev;
      const next = prev[0];
      const current = projectRef.current;
      setPast((p) => [...p.slice(-(MAX_HISTORY - 1)), current]);
      setProject(next);
      if (audioEngine.isPlaying) {
        audioEngine.syncProject(next);
        audioEngine.resyncActivePlayback();
      }
      return prev.slice(1);
    });
  }, []);

  const playPause = useCallback(async () => {
    if (audioEngine.isPlaying) {
      audioEngine.pause();
      setIsPlaying(false);
      const pos = audioEngine.getPlayheadBeats();
      setPlayheadBeats(pos);
      saveWorkspacePrefs({ lastPlayheadBeats: pos });
    } else {
      await audioEngine.play();
      setIsPlaying(audioEngine.isPlaying);
    }
  }, []);

  const stop = useCallback(() => {
    audioEngine.stop();
    setIsPlaying(false);
    setPlayheadBeats(0);
    saveWorkspacePrefs({ lastPlayheadBeats: 0 });
    setTrackMeters({});
    setMasterMeter((m) => ({ ...EMPTY_METER, clipping: m.clipping }));
  }, []);

  const seek = useCallback((beats: number) => {
    const clamped = Math.max(0, beats);
    audioEngine.seek(clamped);
    setPlayheadBeats(clamped);
    saveWorkspacePrefs({ lastPlayheadBeats: clamped });
  }, []);

  const resetMasterClip = useCallback(() => {
    audioEngine.resetMasterClip();
    setMasterMeter((m) => ({ ...m, clipping: false }));
  }, []);

  const saveCurrentProject = useCallback(
    async (options?: { forceOverwrite?: boolean }) => {
      const snapshot = projectRef.current;
      if (!snapshot || saveInFlightRef.current) return;
      saveInFlightRef.current = true;
      setIsSaving(true);
      const sentFingerprint = projectFingerprint(snapshot);
      const expectedRev = options?.forceOverwrite ? undefined : savedRevisionRef.current;

      try {
        const saved = await dawApi.saveProject(snapshot, expectedRev);
        setSavedRevision(saved.revision);
        setSavedFingerprint(projectFingerprint(saved));
        setLastSavedAt(saved.updatedAt);
        setRevisionConflict(null);

        // Critical: NEVER overwrite newer edits made by the user while save was in-flight!
        setProject((latest) => {
          if (!latest || latest.id !== saved.id) return latest;
          if (projectFingerprint(latest) === sentFingerprint) {
            return saved;
          }
          // User edited while saving — keep user's newer state, adopt bumped revision!
          return { ...latest, revision: saved.revision, updatedAt: saved.updatedAt };
        });

        await refreshLists();
        showToast(`Saved "${saved.name}" (rev ${saved.revision})`);
      } catch (err) {
        if (err instanceof RevisionConflictError) {
          setRevisionConflict({
            expectedRevision: savedRevisionRef.current,
            serverRevision: err.serverRevision,
            serverProject: err.serverProject,
          });
          showToast(
            `Revision conflict (local rev ${savedRevisionRef.current}, server rev ${err.serverRevision})`,
            "error"
          );
        } else {
          showToast(`Save failed: ${(err as Error).message}`, "error");
        }
      } finally {
        saveInFlightRef.current = false;
        setIsSaving(false);
      }
    },
    [refreshLists, showToast]
  );

  const openProjectById = useCallback(
    async (id: string, options?: { force?: boolean }) => {
      if (!options?.force && isDirty) {
        const ok = window.confirm(
          "저장되지 않은 변경사항이 있습니다. 저장하지 않고 다른 프로젝트를 여시겠습니까?\n(Unsaved changes will be lost. Open anyway?)"
        );
        if (!ok) return;
      }
      try {
        const opened = await dawApi.openProject(id);
        await hydrateProject(opened, false);
        showToast(`Opened "${opened.name}"`);
      } catch (err) {
        showToast(`Open failed: ${(err as Error).message}`, "error");
      }
    },
    [hydrateProject, isDirty, showToast]
  );

  const createNewProject = useCallback(
    async (name: string, bpm = 128) => {
      try {
        const created = await dawApi.createProject({ name, bpm });
        await hydrateProject(created, false);
        await refreshLists();
        showToast(`Created "${created.name}"`);
      } catch (err) {
        showToast(`Create failed: ${(err as Error).message}`, "error");
      }
    },
    [hydrateProject, refreshLists, showToast]
  );

  const saveAsProject = useCallback(
    async (newName: string) => {
      const current = projectRef.current;
      if (!current) return;
      setIsSaving(true);
      try {
        const cloned = await dawApi.saveAsProject(current.id, newName, current);
        await hydrateProject(cloned, false);
        await refreshLists();
        showToast(`Saved copy "${cloned.name}"`);
      } catch (err) {
        showToast(`Save As failed: ${(err as Error).message}`, "error");
      } finally {
        setIsSaving(false);
      }
    },
    [hydrateProject, refreshLists, showToast]
  );

  const resolveConflictReload = useCallback(async () => {
    if (!revisionConflict) return;
    await hydrateProject(revisionConflict.serverProject, false);
    showToast(`Reloaded server revision ${revisionConflict.serverRevision}`);
  }, [hydrateProject, revisionConflict, showToast]);

  const resolveConflictOverwrite = useCallback(async () => {
    setRevisionConflict(null);
    await saveCurrentProject({ forceOverwrite: true });
  }, [saveCurrentProject]);

  const dismissConflict = useCallback(() => {
    setRevisionConflict(null);
  }, []);

  const applyExternalProjectUpdate = useCallback(
    (updated: Project, message?: string) => {
      const current = projectRef.current;
      if (!current || current.id !== updated.id) return;
      if (updated.revision <= savedRevisionRef.current && !isDirty) return;

      if (isDirty) {
        setRevisionConflict({
          expectedRevision: savedRevisionRef.current,
          serverRevision: updated.revision,
          serverProject: updated,
        });
        showToast(message || `External edit detected (rev ${updated.revision})`, "info");
        return;
      }

      // Clean live sync from external AI agent or MCP tool without reload!
      setPast((prev) => [...prev.slice(-(MAX_HISTORY - 1)), current]);
      setFuture([]);
      setProject(updated);
      setSavedRevision(updated.revision);
      setSavedFingerprint(projectFingerprint(updated));
      setLastSavedAt(updated.updatedAt);
      audioEngine.syncProject(updated);
      if (audioEngine.isPlaying) {
        audioEngine.resyncActivePlayback();
      }
      void loadWaveformsForProject(updated);
      if (message) showToast(message);
    },
    [isDirty, loadWaveformsForProject, showToast]
  );

  const addAssetToTimeline = useCallback(
    (asset: Asset, targetTrackId?: string, startBeats?: number, midiNotes?: MidiNote[]) => {
      const current = projectRef.current;
      if (!current) return;

      const isMidi = asset.kind === "midi";
      let track =
        (targetTrackId ? current.tracks.find((t) => t.id === targetTrackId) : undefined) ??
        current.tracks.find((t) => (isMidi ? t.type === "midi" : t.type !== "midi"));

      let newTrackId: string | undefined;
      if (!track) {
        newTrackId = makeClientId("trk");
        dispatch({
          type: "track.add",
          payload: {
            id: newTrackId,
            name: asset.name.replace(/\.[^.]+$/, ""),
            type: isMidi ? "midi" : "audio",
          },
        });
      }

      const trackId = track ? track.id : newTrackId!;
      const dropStart = startBeats !== undefined ? Math.max(0, startBeats) : Math.floor(playheadBeats);

      if (isMidi) {
        const notes = midiNotes ?? midiNotesCacheRef.current.get(asset.id) ?? [];
        const durBeats = Math.max(4, Math.ceil((asset.durationBeats ?? 16) / 4) * 4);
        const clip: Clip = {
          id: makeClientId("clp"),
          name: asset.name.replace(/\.[^.]+$/, ""),
          type: "midi",
          assetId: asset.id,
          timelineStartBeats: dropStart,
          durationBeats: durBeats,
          sourceOffsetSec: 0,
          sourceDurationSec: 0,
          loop: false,
          loopLengthSec: null,
          loopLengthBeats: durBeats,
          gainDb: 0,
          notes: notes.map((n) => ({ ...n, id: makeClientId("note") })),
        };
        dispatch({ type: "clip.add", payload: { trackId, clip } });
        setSelection({
          selectedTrackId: trackId,
          selectedClipIds: [clip.id],
          timeRangeBeats: {
            startBeats: clip.timelineStartBeats,
            endBeats: clip.timelineStartBeats + clip.durationBeats,
          },
          selectedSectionId: null,
        });
      } else {
        const durSec = asset.durationSec > 0 ? asset.durationSec : 4.0;
        const durBeats = Math.max(1, Math.round(secondsToBeats(durSec, current.bpm) * 100) / 100);
        const clip: Clip = {
          id: makeClientId("clp"),
          name: asset.name.replace(/\.[^.]+$/, ""),
          type: "audio",
          assetId: asset.id,
          timelineStartBeats: dropStart,
          durationBeats: durBeats,
          sourceOffsetSec: 0,
          sourceDurationSec: durSec,
          loop: false,
          loopLengthSec: durSec,
          loopLengthBeats: null,
          gainDb: 0,
          notes: [],
        };
        dispatch({ type: "clip.add", payload: { trackId, clip } });
        setSelection({
          selectedTrackId: trackId,
          selectedClipIds: [clip.id],
          timeRangeBeats: {
            startBeats: clip.timelineStartBeats,
            endBeats: clip.timelineStartBeats + clip.durationBeats,
          },
          selectedSectionId: null,
        });
      }
    },
    [dispatch, playheadBeats]
  );

  const handleImportedAsset = useCallback(
    async (
      proj: Project,
      res: {
        asset: Asset;
        projectRevision?: number;
        midi?: { notes: MidiNote[]; bpm: number | null; durationBeats: number };
      },
      addToTimeline: boolean
    ) => {
      let asset = res.asset;
      if (res.projectRevision) {
        setSavedRevision(res.projectRevision);
      }
      if (res.midi?.notes) {
        midiNotesCacheRef.current.set(asset.id, res.midi.notes);
      }

      if (asset.kind !== "midi") {
        try {
          const wf = await dawApi.getWaveform(proj.id, asset.id, 1024);
          setWaveforms((prev) => ({ ...prev, [asset.id]: wf }));
        } catch {
          try {
            const buf = await audioEngine.loadAssetBuffer(proj.id, asset.id);
            const wf = audioEngine.extractWaveformFromBuffer(buf, 1024);
            setWaveforms((prev) => ({ ...prev, [asset.id]: wf }));
            if (asset.durationSec <= 0) {
              asset = {
                ...asset,
                durationSec: buf.duration,
                sampleRate: buf.sampleRate,
                channels: buf.numberOfChannels,
                durationSamples: buf.length,
              };
            }
          } catch {
            // error recorded in assetStates
          }
        }
      }

      dispatch({ type: "asset.register", payload: { asset } }, { recordHistory: false });
      if (addToTimeline) {
        addAssetToTimeline(asset, selection.selectedTrackId ?? undefined, undefined, res.midi?.notes);
      }
      showToast(`Imported "${asset.name}"`);
    },
    [addAssetToTimeline, dispatch, selection.selectedTrackId, showToast]
  );

  const importFile = useCallback(
    async (file: File, kind?: "audio" | "midi" | "reference", addToTimeline = true) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const saved = await dawApi.saveProject(current, savedRevisionRef.current);
        setSavedRevision(saved.revision);
        const res = await dawApi.importAsset(current.id, file, kind);
        await handleImportedAsset(saved, res, addToTimeline);
      } catch (err) {
        showToast(`Import failed: ${(err as Error).message}`, "error");
      }
    },
    [handleImportedAsset, showToast]
  );

  const importLibraryAsset = useCallback(
    async (item: LibraryItem, addToTimeline = true) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const saved = await dawApi.saveProject(current, savedRevisionRef.current);
        setSavedRevision(saved.revision);
        const res = await dawApi.importFromLibrary(current.id, item.id);
        await handleImportedAsset(saved, res, addToTimeline);
      } catch (err) {
        showToast(`Library import failed: ${(err as Error).message}`, "error");
      }
    },
    [handleImportedAsset, showToast]
  );

  const retryAssetLoad = useCallback(
    async (assetId: string) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const buf = await audioEngine.loadAssetBuffer(current.id, assetId, true);
        const wf = audioEngine.extractWaveformFromBuffer(buf, 1024);
        setWaveforms((prev) => ({ ...prev, [assetId]: wf }));
        showToast("Audio asset reloaded successfully");
      } catch (err) {
        showToast(`Reload failed: ${(err as Error).message}`, "error");
      }
    },
    [showToast]
  );

  const relinkAssetFile = useCallback(
    async (assetId: string, file: File) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const res = await dawApi.relinkAsset(current.id, assetId, file);
        setSavedRevision(res.projectRevision);
        audioEngine.invalidateAssetBuffer(current.id, assetId);
        setProject((prev) => {
          if (!prev) return prev;
          const next: Project = {
            ...prev,
            revision: res.projectRevision,
            assets: prev.assets.map((a) => (a.id === assetId ? res.asset : a)),
          };
          setSavedFingerprint(projectFingerprint(next));
          return next;
        });
        if (res.asset.kind !== "midi") {
          const buf = await audioEngine.loadAssetBuffer(current.id, assetId, true);
          const wf = audioEngine.extractWaveformFromBuffer(buf, 1024);
          setWaveforms((prev) => ({ ...prev, [assetId]: wf }));
        }
        showToast(`Relinked "${res.asset.name}"`);
      } catch (err) {
        showToast(`Relink failed: ${(err as Error).message}`, "error");
      }
    },
    [showToast]
  );

  const exportStereoWav = useCallback(
    async (useLoopRange = false) => {
      const current = projectRef.current;
      if (!current) return;
      setIsExporting(true);
      try {
        const usesStudioEngine =
          (current.buses?.length ?? 0) > 0 ||
          (current.masterEffects?.length ?? 0) > 0 ||
          current.tracks.some(
            (t) =>
              Boolean(t.instrumentRef?.startsWith("sf-") || t.instrumentRef?.startsWith("pro-")) ||
              (t.effects?.length ?? 0) > 0 ||
              (t.sends?.length ?? 0) > 0 ||
              (t.automationLanes?.length ?? 0) > 0 ||
              Boolean(t.freezeState?.frozen)
          );

        if (usesStudioEngine) {
          // Ensure latest edits are persisted before 3-pass FluidSynth + Pedalboard studio render
          const saved = await dawApi.saveProject(current, savedRevisionRef.current);
          setSavedRevision(saved.revision);
          setSavedFingerprint(projectFingerprint(saved));
          const serverRes = await dawApi.exportServerWav(saved.id, useLoopRange);
          const url = URL.createObjectURL(serverRes.blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = serverRes.filename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
          showToast(
            `Exported ${serverRes.filename} (${serverRes.durationSec.toFixed(1)}s · 48kHz Studio DSP · ${serverRes.integratedLufs.toFixed(1)} LUFS · Peak ${serverRes.peakDbfs.toFixed(1)} dBFS)`
          );
          return;
        }

        const result = await renderProjectOfflineWav(current, audioEngine, { useLoopRange });
        const savedInfo = await dawApi.uploadExportWav(current.id, result.filename, result.blob);
        const url = URL.createObjectURL(result.blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = savedInfo.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        const peakDb = result.peakLinear > 1e-6 ? (20 * Math.log10(result.peakLinear)).toFixed(1) : "-inf";
        showToast(
          `Exported ${savedInfo.filename} (${result.durationSec.toFixed(1)}s · 48kHz Stereo · Peak ${peakDb} dBFS)`
        );
      } catch (err) {
        showToast(`Export failed: ${(err as Error).message}`, "error");
      } finally {
        setIsExporting(false);
      }
    },
    [showToast]
  );

  const importReferenceFile = useCallback(
    async (file: File): Promise<ReferenceItem | null> => {
      const current = projectRef.current;
      if (!current) return null;
      try {
        const res = await dawApi.importReferenceFile(current.id, file);
        setSavedRevision(res.projectRevision);
        setProject((prev) => {
          if (!prev) return prev;
          const next: Project = {
            ...prev,
            revision: res.projectRevision,
            references: [...(prev.references ?? []), res.reference],
          };
          setSavedFingerprint(projectFingerprint(next));
          return next;
        });
        setActiveReferenceId(res.reference.id);
        showToast(`레퍼런스 "${res.reference.name}" 추가됨`);
        return res.reference;
      } catch (err) {
        showToast(`Reference import failed: ${(err as Error).message}`, "error");
        return null;
      }
    },
    [showToast]
  );

  const attachAudioToReference = useCallback(
    async (refId: string, file: File) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const res = await dawApi.importReferenceFile(current.id, file, refId);
        setSavedRevision(res.projectRevision);
        setProject((prev) => {
          if (!prev) return prev;
          const next: Project = {
            ...prev,
            revision: res.projectRevision,
            references: (prev.references ?? []).map((r) => (r.id === refId ? res.reference : r)),
          };
          setSavedFingerprint(projectFingerprint(next));
          return next;
        });
        showToast(`오디오 연결 완료: "${res.reference.name}"`);
      } catch (err) {
        showToast(`Attach audio failed: ${(err as Error).message}`, "error");
      }
    },
    [showToast]
  );

  const addReferenceUrl = useCallback(
    async (url: string): Promise<ReferenceItem | null> => {
      const current = projectRef.current;
      if (!current) return null;
      try {
        const res = await dawApi.addReferenceUrl(current.id, url);
        setSavedRevision(res.projectRevision);
        setProject((prev) => {
          if (!prev) return prev;
          const next: Project = {
            ...prev,
            revision: res.projectRevision,
            references: [...(prev.references ?? []), res.reference],
          };
          setSavedFingerprint(projectFingerprint(next));
          return next;
        });
        setActiveReferenceId(res.reference.id);
        showToast(res.reference.noticeKo || "URL 메타데이터가 등록되었습니다.");
        return res.reference;
      } catch (err) {
        showToast(`URL import failed: ${(err as Error).message}`, "error");
        return null;
      }
    },
    [showToast]
  );

  const deleteReference = useCallback(
    async (refId: string) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const res = await dawApi.deleteReference(current.id, refId);
        setSavedRevision(res.projectRevision);
        setProject((prev) => {
          if (!prev) return prev;
          const nextRefs = (prev.references ?? []).filter((r) => r.id !== refId);
          const next: Project = { ...prev, revision: res.projectRevision, references: nextRefs };
          setSavedFingerprint(projectFingerprint(next));
          return next;
        });
        setActiveReferenceId((prev) => (prev === refId ? null : prev));
        showToast("레퍼런스가 삭제되었습니다.");
      } catch (err) {
        showToast(`Delete reference failed: ${(err as Error).message}`, "error");
      }
    },
    [showToast]
  );

  const runReferenceAnalysis = useCallback(
    async (refId: string) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const started = await dawApi.startReferenceAnalysis(current.id, refId, false);
        if (started.job) {
          setActiveAnalysisJob(started.job);
          const jobId = started.job.jobId;
          const poll = async () => {
            try {
              const st = await dawApi.getAnalysisJob(jobId);
              setActiveAnalysisJob(st);
              if (st.status === "completed") {
                const reloaded = await dawApi.openProject(current.id);
                setProject((prev) => {
                  if (!prev || prev.id !== reloaded.id) return prev;
                  const next = { ...prev, revision: reloaded.revision, references: reloaded.references };
                  setSavedRevision(reloaded.revision);
                  setSavedFingerprint(projectFingerprint(next));
                  return next;
                });
                showToast("레퍼런스 음향 분석 및 Blueprint 생성 완료");
              } else if (st.status === "failed" || st.status === "cancelled") {
                showToast(st.error || "분석이 취소되었습니다.", st.status === "failed" ? "error" : "info");
              } else {
                window.setTimeout(() => void poll(), 350);
              }
            } catch {
              setActiveAnalysisJob(null);
            }
          };
          window.setTimeout(() => void poll(), 250);
        }
      } catch (err) {
        showToast(`Analysis failed: ${(err as Error).message}`, "error");
      }
    },
    [showToast]
  );

  const cancelReferenceAnalysis = useCallback(async () => {
    if (!activeAnalysisJob) return;
    try {
      const st = await dawApi.cancelAnalysisJob(activeAnalysisJob.jobId);
      setActiveAnalysisJob(st);
    } catch {
      // ignore
    }
  }, [activeAnalysisJob]);

  const toggleBlueprintInfluence = useCallback(
    async (refId: string, influenceId: string) => {
      const current = projectRef.current;
      if (!current) return;
      const ref = (current.references ?? []).find((r) => r.id === refId);
      if (!ref) return;
      const existing = new Set(ref.selectedInfluences ?? []);
      if (existing.has(influenceId)) existing.delete(influenceId);
      else existing.add(influenceId);
      try {
        const res = await dawApi.updateReferenceBlueprint(current.id, refId, {
          selectedInfluences: Array.from(existing),
        });
        setSavedRevision(res.projectRevision);
        setProject((prev) => {
          if (!prev) return prev;
          const next: Project = {
            ...prev,
            revision: res.projectRevision,
            references: (prev.references ?? []).map((r) => (r.id === refId ? res.reference : r)),
          };
          setSavedFingerprint(projectFingerprint(next));
          return next;
        });
      } catch (err) {
        showToast(`Blueprint update failed: ${(err as Error).message}`, "error");
      }
    },
    [showToast]
  );

  const pollAnalysisOrTranscriptionJob = useCallback(
    (projectId: string, job: AnalysisJobStatus, doneMessage: string) => {
      setActiveAnalysisJob(job);
      const jobId = job.jobId;
      const poll = async () => {
        try {
          const st = await dawApi.getAnalysisJob(jobId);
          setActiveAnalysisJob(st);
          if (st.status === "completed") {
            const reloaded = await dawApi.openProject(projectId);
            setProject((prev) => {
              if (!prev || prev.id !== reloaded.id) return prev;
              const next = { ...prev, revision: reloaded.revision, references: reloaded.references };
              setSavedRevision(reloaded.revision);
              setSavedFingerprint(projectFingerprint(next));
              return next;
            });
            showToast(doneMessage);
          } else if (st.status === "failed" || st.status === "cancelled") {
            showToast(st.error || "분석/채보가 취소되었습니다.", st.status === "failed" ? "error" : "info");
          } else {
            window.setTimeout(() => void poll(), 400);
          }
        } catch {
          setActiveAnalysisJob(null);
        }
      };
      window.setTimeout(() => void poll(), 250);
    },
    [showToast]
  );

  const runReferenceTranscription = useCallback(
    async (refId: string, useDemucs = true) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const started = await dawApi.startReferenceTranscription(current.id, refId, {
          sync: false,
          useDemucs,
        });
        if (started.job) {
          pollAnalysisOrTranscriptionJob(
            current.id,
            started.job,
            "정밀 채보 완료 (Demucs 스템 + Basic Pitch + 코드/드럼 Blueprint v2)"
          );
        }
      } catch (err) {
        showToast(`Transcription failed: ${(err as Error).message}`, "error");
      }
    },
    [pollAnalysisOrTranscriptionJob, showToast]
  );

  const updateReferenceLocks = useCallback(
    async (
      refId: string,
      body: { featureLocks?: Record<string, string>; chordCorrections?: ChordEvent[] }
    ) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const res = await dawApi.updateReferenceLocks(current.id, refId, body);
        setSavedRevision(res.projectRevision);
        setProject((prev) => {
          if (!prev) return prev;
          const next: Project = {
            ...prev,
            revision: res.projectRevision,
            references: (prev.references ?? []).map((r) => (r.id === refId ? res.reference : r)),
          };
          setSavedFingerprint(projectFingerprint(next));
          return next;
        });
        if (body.chordCorrections) showToast("레퍼런스 코드 수정이 Blueprint v2에 반영되었습니다.");
      } catch (err) {
        showToast(`Reference lock update failed: ${(err as Error).message}`, "error");
      }
    },
    [showToast]
  );

  const reconstructReference = useCallback(
    async (
      refId: string,
      opts?: {
        importChords?: boolean;
        importDrumsMidi?: boolean;
        importBassMidi?: boolean;
        importMelodyMidi?: boolean;
        importStems?: boolean;
        importSections?: boolean;
        applyBpm?: boolean;
      }
    ) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        if (projectFingerprint(current) !== savedFingerprint) {
          const saved = await dawApi.saveProject(current, savedRevisionRef.current);
          setSavedRevision(saved.revision);
          setSavedFingerprint(projectFingerprint(saved));
          setProject(saved);
        }
        const res = await dawApi.reconstructReference(current.id, refId, opts ?? {});
        applyExternalProjectUpdate(
          res.project,
          `레퍼런스 가져오기 완료: ${res.importedItems.join(", ")} (Cmd+Z / Undo 지원)`
        );
      } catch (err) {
        showToast(`재구성 실패: ${(err as Error).message}`, "error");
      }
    },
    [applyExternalProjectUpdate, savedFingerprint, showToast]
  );

  const activeReference = useMemo(() => {
    if (!project || !project.references?.length) return null;
    if (activeReferenceId) {
      return project.references.find((r) => r.id === activeReferenceId) ?? project.references[0];
    }
    return project.references[0];
  }, [project, activeReferenceId]);

  // Sync live browser SelectionContext & active project to backend Session Registry (for external MCP agents!)
  useEffect(() => {
    if (!project) return;
    const locale = window.localStorage.getItem("ai_native_daw_locale_v1") || "ko";
    const timer = window.setTimeout(() => {
      void dawApi
        .syncSessionState({
          sessionId,
          projectId: project.id,
          revision: savedRevision,
          selection,
          activeReferenceId: activeReference?.id ?? null,
          locale,
          claimActive: true,
        })
        .catch(() => {
          // non-fatal
        });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [sessionId, project?.id, savedRevision, selection, activeReference?.id]);

  // Fetch pending proposals & maintain live SSE connection for real-time external agent sync
  useEffect(() => {
    if (!project?.id) return;
    const pid = project.id;
    let active = true;

    void dawApi
      .listProposals(pid, "pending")
      .then((res) => {
        if (active) setPendingProposals(res.proposals);
      })
      .catch(() => {});

    if (typeof EventSource === "undefined") return;
    const es = new EventSource(`/api/events?projectId=${encodeURIComponent(pid)}`);
    let hadDisconnect = false;
    es.onopen = () => {
      if (!active) return;
      setSseConnected(true);
      if (hadDisconnect) {
        hadDisconnect = false;
        // Phase 03-A: recover latest project revision & pending proposals after SSE drop
        void dawApi
          .openProject(pid)
          .then((latest) => {
            if (active && latest.revision > savedRevisionRef.current) {
              applyExternalProjectUpdate(latest, "연결 복구 후 최신 상태 동기화됨");
            }
          })
          .catch(() => {});
        void dawApi
          .listProposals(pid, "pending")
          .then((res) => {
            if (active) setPendingProposals(res.proposals);
          })
          .catch(() => {});
      }
    };
    es.onerror = () => {
      if (active) {
        hadDisconnect = true;
        setSseConnected(false);
      }
    };
    es.onmessage = (evt) => {
      if (!active) return;
      try {
        const msg = JSON.parse(evt.data) as { type: string; payload: Record<string, unknown> };
        if (msg.type === "connected") {
          setSseConnected(true);
        } else if (msg.type === "project.updated" && msg.payload.project) {
          const updated = msg.payload.project as Project;
          if (updated.id === pid && updated.revision > savedRevisionRef.current) {
            applyExternalProjectUpdate(
              updated,
              typeof msg.payload.reason === "string" ? msg.payload.reason : undefined
            );
          }
        } else if (msg.type === "proposal.created" && msg.payload.proposal) {
          const prop = msg.payload.proposal as ChangeProposal;
          if (prop.projectId === pid && prop.status === "pending") {
            setPendingProposals((prev) =>
              prev.some((p) => p.id === prop.id) ? prev : [...prev, prop]
            );
          }
        } else if (msg.type === "proposal.updated" && msg.payload.proposal) {
          const prop = msg.payload.proposal as ChangeProposal;
          if (prop.projectId === pid) {
            setPendingProposals((prev) =>
              prop.status === "pending"
                ? prev.map((p) => (p.id === prop.id ? prop : p))
                : prev.filter((p) => p.id !== prop.id)
            );
          }
        } else if (msg.type === "proposals.synced" && Array.isArray(msg.payload.proposals)) {
          if (msg.payload.projectId === pid) {
            setPendingProposals(msg.payload.proposals as ChangeProposal[]);
          }
        } else if (msg.type === "generation.job.updated" && msg.payload.job) {
          const job = msg.payload.job as GenerationJobStatus;
          if (job.projectId === pid) {
            setActiveGenerationJob(job);
          }
        } else if (msg.type === "take.created" && msg.payload.take) {
          const take = msg.payload.take as Take;
          if (take.projectId === pid) {
            void dawApi
              .openProject(pid)
              .then((latest) => {
                if (!active) return;
                setProject((prev) => {
                  if (!prev || prev.id !== latest.id) return prev;
                  const next = { ...prev, revision: latest.revision, takes: latest.takes, compositionPlans: latest.compositionPlans };
                  setSavedRevision(latest.revision);
                  setSavedFingerprint(projectFingerprint(next));
                  return next;
                });
              })
              .catch(() => {});
          }
        }
      } catch {
        // ignore malformed SSE frame
      }
    };

    return () => {
      active = false;
      es.close();
      setSseConnected(false);
    };
  }, [project?.id, applyExternalProjectUpdate]);

  const applyPendingProposal = useCallback(
    async (proposalId: string) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const res = await dawApi.applyProposal(current.id, proposalId);
        setPendingProposals((prev) => prev.filter((p) => p.id !== proposalId));
        applyExternalProjectUpdate(res.project, `적용됨: ${res.proposal.summary}`);
      } catch (err) {
        if (err instanceof RevisionConflictError) {
          setRevisionConflict({
            expectedRevision: savedRevisionRef.current,
            serverRevision: err.serverRevision,
            serverProject: err.serverProject,
          });
        }
        showToast((err as Error).message, "error");
      }
    },
    [applyExternalProjectUpdate, showToast]
  );

  const rejectPendingProposal = useCallback(
    async (proposalId: string) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        await dawApi.rejectProposal(current.id, proposalId);
        setPendingProposals((prev) => prev.filter((p) => p.id !== proposalId));
        showToast("제안이 거절되었습니다.");
      } catch (err) {
        showToast((err as Error).message, "error");
      }
    },
    [showToast]
  );

  const submitProducerInstruction = useCallback(
    async (instruction: string): Promise<ProducerInstructResponse | null> => {
      const current = projectRef.current;
      if (!current || !instruction.trim()) return null;
      try {
        // Ensure latest unsaved local edits are synced before staging server proposal
        let effectiveRev = savedRevisionRef.current;
        if (projectFingerprint(current) !== savedFingerprint) {
          const saved = await dawApi.saveProject(current, effectiveRev);
          savedRevisionRef.current = saved.revision;
          effectiveRev = saved.revision;
          projectRef.current = saved;
          setSavedRevision(saved.revision);
          setSavedFingerprint(projectFingerprint(saved));
          setProject(saved);
        }
        let res: ProducerInstructResponse;
        try {
          res = await dawApi.sendProducerInstruction(current.id, {
            instruction: instruction.trim(),
            selection,
            activeReferenceId: activeReference?.id ?? null,
            baseRevision: effectiveRev,
          });
        } catch (err) {
          if (err instanceof RevisionConflictError) {
            // Autosave raced with instruction submit: adopt latest server revision and retry once cleanly
            savedRevisionRef.current = err.serverRevision;
            setSavedRevision(err.serverRevision);
            res = await dawApi.sendProducerInstruction(current.id, {
              instruction: instruction.trim(),
              selection,
              activeReferenceId: activeReference?.id ?? null,
              baseRevision: err.serverRevision,
            });
          } else {
            throw err;
          }
        }
        if (res.action === "analyze_reference" && res.referenceId) {
          await runReferenceAnalysis(res.referenceId);
        } else if (res.action === "transcription_started" && res.job) {
          pollAnalysisOrTranscriptionJob(
            current.id,
            res.job,
            "정밀 채보 완료 (Demucs + Basic Pitch + 코드/드럼 Blueprint v2)"
          );
        } else if (res.action === "reference_reconstructed" && res.project) {
          applyExternalProjectUpdate(res.project, res.messageKo || "레퍼런스 재구성 완료");
        } else if (res.action === "proposal_created" && res.proposal) {
          setPendingProposals((prev) =>
            prev.some((p) => p.id === res.proposal!.id) ? prev : [...prev, res.proposal!]
          );
        } else if (res.action === "arrangement_edit_plan_created" && res.arrangementPlan) {
          setActiveArrangementPlan(res.arrangementPlan);
        } else if (res.action === "composition_plan_created" && res.plan) {
          setActivePlan(res.plan);
          if (res.projectRevision) setSavedRevision(res.projectRevision);
          setProject((prev) => {
            if (!prev) return prev;
            const plans = [...(prev.compositionPlans ?? []).filter((p) => p.id !== res.plan!.id), res.plan!];
            const next = { ...prev, revision: res.projectRevision ?? prev.revision, compositionPlans: plans };
            setSavedFingerprint(projectFingerprint(next));
            return next;
          });
        }
        return res;
      } catch (err) {
        showToast((err as Error).message, "error");
        return null;
      }
    },
    [
      selection,
      activeReference?.id,
      savedFingerprint,
      runReferenceAnalysis,
      pollAnalysisOrTranscriptionJob,
      applyExternalProjectUpdate,
      showToast,
    ]
  );

  // --- Phase 03 AI Composition Engine Store Actions ---

  const selectAiProvider = useCallback(
    async (providerId: string) => {
      try {
        const updated = await dawApi.selectProvider(providerId);
        setProviderSummary(updated);
        showToast(`AI Producer 프로바이더 변경됨: ${providerId}`);
      } catch (err) {
        showToast((err as Error).message, "error");
      }
    },
    [showToast]
  );

  const requestCompositionPlan = useCallback(
    async (
      instruction: string,
      opts?: {
        mode?: string;
        targetInstrument?: string;
        useReference?: boolean;
        enginePreference?: string;
        featureLocks?: Record<string, string>;
        referenceMode?: "reconstruct" | "reference_compose" | "reinterpret";
        useProjectChordTrack?: boolean;
      }
    ): Promise<CompositionPlan | null> => {
      const current = projectRef.current;
      if (!current || !instruction.trim()) return null;
      try {
        if (projectFingerprint(current) !== savedFingerprint) {
          const saved = await dawApi.saveProject(current, savedRevisionRef.current);
          setSavedRevision(saved.revision);
          setSavedFingerprint(projectFingerprint(saved));
          setProject(saved);
        }
        const useRef = opts?.useReference !== false && Boolean(activeReference?.analysis);
        const res = await dawApi.createCompositionPlan(current.id, {
          instruction: instruction.trim(),
          mode: opts?.mode,
          targetInstrument: opts?.targetInstrument,
          referenceIds: useRef && activeReference ? [activeReference.id] : [],
          selectedInfluences: useRef && activeReference ? activeReference.selectedInfluences : undefined,
          featureLocks: opts?.featureLocks ?? (useRef ? activeReference?.featureLocks : undefined),
          referenceMode: opts?.referenceMode ?? "reference_compose",
          useProjectChordTrack: opts?.useProjectChordTrack ?? Boolean(current.chordTrackLocked),
          selection,
          enginePreference: opts?.enginePreference,
        });
        setActivePlan(res.plan);
        setEngineUnavailableNotice(null);
        setSavedRevision(res.projectRevision);
        setProject((prev) => {
          if (!prev) return prev;
          const plans = [...(prev.compositionPlans ?? []).filter((p) => p.id !== res.plan.id), res.plan];
          const next = { ...prev, revision: res.projectRevision, compositionPlans: plans };
          setSavedFingerprint(projectFingerprint(next));
          return next;
        });
        return res.plan;
      } catch (err) {
        showToast(`작곡 계획 생성 실패: ${(err as Error).message}`, "error");
        return null;
      }
    },
    [activeReference, savedFingerprint, selection, showToast]
  );

  const dismissEngineUnavailableNotice = useCallback(() => {
    setEngineUnavailableNotice(null);
  }, []);

  const startGenerationFromPlan = useCallback(
    async (plan: CompositionPlan, engine = "auto"): Promise<boolean> => {
      const current = projectRef.current;
      if (!current) return false;
      try {
        setEngineUnavailableNotice(null);
        const res = await dawApi.startGenerationJob(current.id, {
          planId: plan.id,
          engine,
          sync: false,
        });
        if (res.engineUnavailable || !res.job) {
          setEngineUnavailableNotice({
            requestedEngine: res.requestedEngine || engine,
            errorKo: res.errorKo || "요청하신 신경망 오디오 엔진이 현재 설치되지 않았습니다.",
            errorEn: res.errorEn || "Requested neural audio engine is not installed on this machine.",
            plan,
          });
          showToast(res.errorKo || "요청하신 생성 엔진이 설치되지 않았습니다.", "error");
          return false;
        }
        setActiveGenerationJob(res.job);
        const jobId = res.job.jobId;
        const poll = async () => {
          try {
            const st = await dawApi.getGenerationJob(jobId);
            setActiveGenerationJob(st);
            if (st.status === "ready_for_preview") {
              const latest = await dawApi.openProject(current.id);
              setProject((prev) => {
                if (!prev || prev.id !== latest.id) return prev;
                const next = {
                  ...prev,
                  revision: latest.revision,
                  takes: latest.takes,
                  compositionPlans: latest.compositionPlans,
                };
                setSavedRevision(latest.revision);
                setSavedFingerprint(projectFingerprint(next));
                return next;
              });
              showToast(`Take 생성 완료: "${plan.musicalIdentity.title || plan.mode}" — 미리듣기 후 적용하세요.`);
            } else if (st.status === "failed" || st.status === "cancelled") {
              showToast(st.error || "생성이 취소되었습니다.", st.status === "failed" ? "error" : "info");
            } else {
              window.setTimeout(() => void poll(), 300);
            }
          } catch {
            setActiveGenerationJob(null);
          }
        };
        window.setTimeout(() => void poll(), 200);
        return true;
      } catch (err) {
        showToast(`생성 시작 실패: ${(err as Error).message}`, "error");
        return false;
      }
    },
    [showToast]
  );

  const cancelActiveGeneration = useCallback(async () => {
    if (!activeGenerationJob) return;
    try {
      const st = await dawApi.cancelGenerationJob(activeGenerationJob.jobId);
      setActiveGenerationJob(st);
    } catch {
      // ignore
    }
  }, [activeGenerationJob]);

  const applyGeneratedTake = useCallback(
    async (
      takeId: string,
      applyMode:
        | "add"
        | "new_tracks"
        | "replace_range"
        | "selected_range"
        | "alternative_take"
        | "extend"
        | "new_project"
        | "keep_take",
      targetTrackId?: string | null
    ) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        if (projectFingerprint(current) !== savedFingerprint) {
          const saved = await dawApi.saveProject(current, savedRevisionRef.current);
          setSavedRevision(saved.revision);
          setSavedFingerprint(projectFingerprint(saved));
          setProject(saved);
        }
        const targetTake = (projectRef.current?.takes ?? []).find((tk) => tk.id === takeId);
        const startBeatsOverride =
          applyMode === "replace_range" || applyMode === "selected_range" || applyMode === "alternative_take"
            ? targetTake?.targetRangeBeats?.startBeats ?? selection.timeRangeBeats?.startBeats
            : selection.timeRangeBeats?.startBeats;
        const res = await dawApi.applyTake(current.id, takeId, {
          applyMode,
          targetTrackId: targetTrackId ?? targetTake?.targetTrackId ?? selection.selectedTrackId,
          startBeats: startBeatsOverride,
          addSectionMarkers: applyMode === "new_tracks" || applyMode === "add" || applyMode === "new_project",
          expectedRevision: savedRevisionRef.current,
        });
        if (res.createdNewProject && res.project) {
          await hydrateProject(res.project, false);
          await refreshLists();
          showToast(`새 프로젝트로 생성 결과 적용됨: "${res.project.name}"`);
        } else if (res.project) {
          applyExternalProjectUpdate(res.project, `Take 적용됨 (${applyMode}): ${res.take.title}`);
        }
      } catch (err) {
        showToast(`Take 적용 실패: ${(err as Error).message}`, "error");
      }
    },
    [applyExternalProjectUpdate, hydrateProject, refreshLists, savedFingerprint, selection, showToast]
  );

  const rejectGeneratedTake = useCallback(
    async (takeId: string) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const res = await dawApi.rejectTake(current.id, takeId);
        setSavedRevision(res.projectRevision);
        setProject((prev) => {
          if (!prev) return prev;
          const next = {
            ...prev,
            revision: res.projectRevision,
            takes: (prev.takes ?? []).map((tk) => (tk.id === takeId ? res.take : tk)),
          };
          setSavedFingerprint(projectFingerprint(next));
          return next;
        });
        showToast("Take가 거절 처리되었습니다.");
      } catch (err) {
        showToast(`Take 거절 실패: ${(err as Error).message}`, "error");
      }
    },
    [showToast]
  );

  // --- Phase 04 Selective Arrangement, Musical Variation, Take Lanes & Audio Reverse ---

  const requestArrangementPlan = useCallback(
    async (
      instruction: string,
      opts?: { intensity?: "subtle" | "moderate" | "creative"; targetTrackId?: string | null }
    ): Promise<ArrangementEditPlan | null> => {
      const current = projectRef.current;
      if (!current || !instruction.trim()) return null;
      try {
        if (projectFingerprint(current) !== savedFingerprint) {
          const saved = await dawApi.saveProject(current, savedRevisionRef.current);
          setSavedRevision(saved.revision);
          setSavedFingerprint(projectFingerprint(saved));
          setProject(saved);
        }
        const res = await dawApi.createArrangementPlan(current.id, {
          instruction: instruction.trim(),
          selection,
          intensity: opts?.intensity,
          targetTrackId: opts?.targetTrackId,
        });
        setActiveArrangementPlan(res.plan);
        return res.plan;
      } catch (err) {
        showToast(`편곡 계획 생성 실패: ${(err as Error).message}`, "error");
        return null;
      }
    },
    [savedFingerprint, selection, showToast]
  );

  const executeArrangementPlan = useCallback(
    async (
      plan: ArrangementEditPlan,
      opts?: { intensity?: "subtle" | "moderate" | "creative"; seed?: number }
    ): Promise<{ take?: Take; applied?: boolean; messageKo?: string } | null> => {
      const current = projectRef.current;
      if (!current) return null;
      try {
        if (projectFingerprint(current) !== savedFingerprint) {
          const saved = await dawApi.saveProject(current, savedRevisionRef.current);
          setSavedRevision(saved.revision);
          setSavedFingerprint(projectFingerprint(saved));
          setProject(saved);
        }
        const res = await dawApi.executeArrangementPlan(current.id, {
          plan,
          intensity: opts?.intensity ?? plan.intensity,
          seed: opts?.seed ?? 42,
        });
        if (res.project) {
          applyExternalProjectUpdate(res.project, res.messageKo || "편곡이 적용되었습니다.");
        } else if (res.take) {
          const latest = await dawApi.openProject(current.id);
          setProject((prev) => {
            if (!prev || prev.id !== latest.id) return prev;
            const next = {
              ...prev,
              revision: latest.revision,
              takes: latest.takes,
              musicMemory: latest.musicMemory,
            };
            setSavedRevision(latest.revision);
            setSavedFingerprint(projectFingerprint(next));
            return next;
          });
          showToast(`변주 Take 생성 완료: "${res.take.title}" — 단독/함께 듣기로 비교 후 적용하세요.`);
        }
        return res;
      } catch (err) {
        showToast(`편곡/변주 실행 실패: ${(err as Error).message}`, "error");
        return null;
      }
    },
    [applyExternalProjectUpdate, savedFingerprint, showToast]
  );

  const promoteTakeLane = useCallback(
    async (trackId: string, laneId: string, range?: { startBeats: number; endBeats: number }) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        if (projectFingerprint(current) !== savedFingerprint) {
          const saved = await dawApi.saveProject(current, savedRevisionRef.current);
          setSavedRevision(saved.revision);
          setSavedFingerprint(projectFingerprint(saved));
          setProject(saved);
        }
        const res = await dawApi.promoteTakeLane(current.id, trackId, laneId, range);
        applyExternalProjectUpdate(
          res.project,
          range ? "선택한 구간만 Take Lane에서 채택되었습니다." : "Take Lane이 메인 타임라인으로 채택되었습니다."
        );
      } catch (err) {
        showToast(`Take Lane 채택 실패: ${(err as Error).message}`, "error");
      }
    },
    [applyExternalProjectUpdate, savedFingerprint, showToast]
  );

  const restoreOriginalTakeLane = useCallback(
    async (trackId: string, laneId?: string) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        const res = await dawApi.restoreOriginalTakeLane(current.id, trackId, laneId);
        applyExternalProjectUpdate(res.project, "원본 백업 Take Lane이 복원되었습니다.");
      } catch (err) {
        showToast(`원본 복원 실패: ${(err as Error).message}`, "error");
      }
    },
    [applyExternalProjectUpdate, showToast]
  );

  const renameTakeLane = useCallback(
    async (trackId: string, laneId: string, name: string) => {
      const current = projectRef.current;
      if (!current || !name.trim()) return;
      try {
        const res = await dawApi.renameTakeLane(current.id, trackId, laneId, name.trim());
        applyExternalProjectUpdate(res.project);
      } catch (err) {
        showToast(`Take Lane 이름 변경 실패: ${(err as Error).message}`, "error");
      }
    },
    [applyExternalProjectUpdate, showToast]
  );

  const reverseAudioClip = useCallback(
    async (clipId: string) => {
      const current = projectRef.current;
      if (!current) return;
      try {
        if (projectFingerprint(current) !== savedFingerprint) {
          const saved = await dawApi.saveProject(current, savedRevisionRef.current);
          setSavedRevision(saved.revision);
          setSavedFingerprint(projectFingerprint(saved));
          setProject(saved);
        }
        const res = await dawApi.reverseAudioClip(current.id, clipId, savedRevisionRef.current);
        applyExternalProjectUpdate(res.project, `비파괴 리버스 완료: "${res.newAsset.name}" (원본 WAV 보존됨)`);
      } catch (err) {
        showToast(`오디오 리버스 실패: ${(err as Error).message}`, "error");
      }
    },
    [applyExternalProjectUpdate, savedFingerprint, showToast]
  );

  const takes = useMemo(() => [...(project?.takes ?? [])].reverse(), [project?.takes]);

  const selectedTrack = useMemo(() => {
    if (!project || !selection.selectedTrackId) return null;
    return project.tracks.find((t) => t.id === selection.selectedTrackId) ?? null;
  }, [project, selection.selectedTrackId]);

  const selectedClip = useMemo(() => {
    if (!project || selection.selectedClipIds.length === 0) return null;
    const primaryId = selection.selectedClipIds[0];
    for (const t of project.tracks) {
      const found = t.clips.find((c) => c.id === primaryId);
      if (found) return found;
    }
    return null;
  }, [project, selection.selectedClipIds]);

  const value: DawContextValue = {
    project,
    recentProjects,
    libraryItems,
    health,
    waveforms,
    assetStates,
    selection,
    setSelection,
    selectedTrack,
    selectedClip,
    isDirty,
    isSaving,
    isExporting,
    lastSavedAt,
    savedRevision,
    revisionConflict,
    resolveConflictReload,
    resolveConflictOverwrite,
    dismissConflict,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
    isPlaying,
    playheadBeats,
    trackMeters,
    masterMeter,
    snapEnabled,
    setSnapEnabled,
    gridBeats,
    setGridBeats,
    pixelsPerBeat,
    setPixelsPerBeat,
    toast,
    showToast,
    dispatch,
    beginTransaction,
    commitTransaction,
    undo,
    redo,
    playPause,
    stop,
    seek,
    resetMasterClip,
    openProjectById,
    createNewProject,
    saveCurrentProject,
    saveAsProject,
    importFile,
    importLibraryAsset,
    addAssetToTimeline,
    retryAssetLoad,
    relinkAssetFile,
    exportStereoWav,
    applyExternalProjectUpdate,
    refreshLists,
    activeReferenceId,
    setActiveReferenceId,
    activeReference,
    activeAnalysisJob,
    importReferenceFile,
    attachAudioToReference,
    addReferenceUrl,
    deleteReference,
    runReferenceAnalysis,
    runReferenceTranscription,
    cancelReferenceAnalysis,
    toggleBlueprintInfluence,
    updateReferenceLocks,
    reconstructReference,
    sessionId,
    sseConnected,
    pendingProposals,
    applyPendingProposal,
    rejectPendingProposal,
    submitProducerInstruction,
    providerSummary,
    generationEngines,
    runtimeRegistry,
    activePlan,
    setActivePlan,
    activeArrangementPlan,
    setActiveArrangementPlan,
    engineUnavailableNotice,
    dismissEngineUnavailableNotice,
    activeGenerationJob,
    takes,
    selectAiProvider,
    requestCompositionPlan,
    startGenerationFromPlan,
    cancelActiveGeneration,
    applyGeneratedTake,
    rejectGeneratedTake,
    requestArrangementPlan,
    executeArrangementPlan,
    promoteTakeLane,
    restoreOriginalTakeLane,
    renameTakeLane,
    reverseAudioClip,
  };

  return <DawContext.Provider value={value}>{children}</DawContext.Provider>;
}

export function useDaw(): DawContextValue {
  const ctx = useContext(DawContext);
  if (!ctx) throw new Error("useDaw must be used within DawProvider");
  return ctx;
}
