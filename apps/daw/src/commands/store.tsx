import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { audioEngine } from "../audio/audioEngine";
import { renderProjectOfflineWav } from "../audio/offlineRenderer";
import { dawApi } from "../project/api";
import { secondsToBeats } from "../project/time";
import type {
  Asset,
  Clip,
  HealthInfo,
  LibraryItem,
  MidiNote,
  Project,
  ProjectSummary,
  SelectionContext,
  Track,
  TrackMeterLevel,
  WaveformData,
} from "../project/types";
import { executeCommand, makeClientId } from "./executor";
import { NON_UNDOABLE_COMMANDS, type ProjectCommand } from "./types";

const MAX_HISTORY = 100;

interface ToastState {
  message: string;
  kind: "info" | "error";
}

interface DawContextValue {
  project: Project | null;
  recentProjects: ProjectSummary[];
  libraryItems: LibraryItem[];
  health: HealthInfo | null;
  waveforms: Record<string, WaveformData>;
  selection: SelectionContext;
  setSelection: React.Dispatch<React.SetStateAction<SelectionContext>>;
  selectedTrack: Track | null;
  selectedClip: Clip | null;
  isDirty: boolean;
  isSaving: boolean;
  isExporting: boolean;
  lastSavedAt: string | null;
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
  openProjectById: (id: string) => Promise<void>;
  createNewProject: (name: string, bpm?: number) => Promise<void>;
  saveCurrentProject: () => Promise<void>;
  saveAsProject: (newName: string) => Promise<void>;
  importFile: (file: File, kind?: "audio" | "midi" | "reference", addToTimeline?: boolean) => Promise<void>;
  importLibraryAsset: (item: LibraryItem, addToTimeline?: boolean) => Promise<void>;
  addAssetToTimeline: (asset: Asset, targetTrackId?: string, startBeats?: number, midiNotes?: MidiNote[]) => void;
  exportStereoWav: (useLoopRange?: boolean) => Promise<void>;
}

const DawContext = createContext<DawContextValue | null>(null);

const EMPTY_METER: TrackMeterLevel = { peakL: 0, peakR: 0, rmsL: 0, rmsR: 0, clipping: false };

export function DawProvider({ children }: { children: React.ReactNode }) {
  const [project, setProject] = useState<Project | null>(null);
  const [recentProjects, setRecentProjects] = useState<ProjectSummary[]>([]);
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [waveforms, setWaveforms] = useState<Record<string, WaveformData>>({});
  const [selection, setSelection] = useState<SelectionContext>({
    selectedTrackId: null,
    selectedClipIds: [],
    timeRangeBeats: null,
    selectedSectionId: null,
  });

  const [past, setPast] = useState<Project[]>([]);
  const [future, setFuture] = useState<Project[]>([]);
  const [isDirty, setIsDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [playheadBeats, setPlayheadBeats] = useState(0);
  const [trackMeters, setTrackMeters] = useState<Record<string, TrackMeterLevel>>({});
  const [masterMeter, setMasterMeter] = useState<TrackMeterLevel>(EMPTY_METER);

  const [snapEnabled, setSnapEnabled] = useState(true);
  const [gridBeats, setGridBeats] = useState(1); // 1 beat = quarter note
  const [pixelsPerBeat, setPixelsPerBeat] = useState(15);
  const [toast, setToast] = useState<ToastState | null>(null);

  const projectRef = useRef<Project | null>(null);
  projectRef.current = project;
  const txSnapshotRef = useRef<Project | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  const midiNotesCacheRef = useRef<Map<string, MidiNote[]>>(new Map());

  const showToast = useCallback((message: string, kind: "info" | "error" = "info") => {
    setToast({ message, kind });
    if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => setToast(null), kind === "error" ? 5000 : 2800);
  }, []);

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
          // fallback to Web Audio client decode below
        }
        try {
          const buf = await audioEngine.loadAssetBuffer(proj.id, asset.id);
          results[asset.id] = audioEngine.extractWaveformFromBuffer(buf, 1024);
        } catch {
          // leave empty if unreadable
        }
      })
    );
    setWaveforms(results);
  }, []);

  const hydrateProject = useCallback(
    async (loaded: Project) => {
      audioEngine.stop();
      setIsPlaying(false);
      setPlayheadBeats(0);
      setProject(loaded);
      setPast([]);
      setFuture([]);
      setIsDirty(false);
      setLastSavedAt(loaded.updatedAt);

      // Pick a sensible initial selection so Clip Editor & AI Context immediately shine
      const firstAudioTrack = loaded.tracks.find((t) => t.clips.length > 0) ?? loaded.tracks[0] ?? null;
      const featuredClip =
        loaded.tracks.find((t) => t.id === "trk_guitar")?.clips[1] ??
        firstAudioTrack?.clips[0] ??
        null;
      const featuredTrackId =
        featuredClip
          ? loaded.tracks.find((t) => t.clips.some((c) => c.id === featuredClip.id))?.id ?? firstAudioTrack?.id ?? null
          : firstAudioTrack?.id ?? null;

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

  // Initial boot: load health, projects, open Demo B (or latest project) directly into studio
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const h = await dawApi.health();
        if (active) setHealth(h);
      } catch {
        // backend unavailable warning handled on project fetch
      }
      const list = await refreshLists();
      if (!active) return;
      if (list.length > 0) {
        const preferred =
          list.find((p) => p.id === "demo_multitrack_session") ??
          list.find((p) => p.id === "demo_v72_magnetic_afterhours") ??
          list[0];
        try {
          const opened = await dawApi.openProject(preferred.id);
          if (active) await hydrateProject(opened);
        } catch (err) {
          showToast(`Failed to open project: ${(err as Error).message}`, "error");
        }
      } else {
        try {
          const created = await dawApi.createProject({ name: "Untitled 01", bpm: 128 });
          if (active) {
            await hydrateProject(created);
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

  // Sync project mutations to audio engine
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

  // Periodic debounced autosave (every 4s when dirty)
  useEffect(() => {
    if (!isDirty || !project) return;
    const timer = window.setTimeout(() => {
      const current = projectRef.current;
      if (current) {
        void dawApi.autosaveProject(current).catch(() => {
          // non-fatal autosave warning
        });
      }
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [isDirty, project]);

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
        setProject(next);
        setIsDirty(true);

        // If timeline structure changed during playback, re-sync scheduler cleanly
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
      setIsDirty(true);
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
      setIsDirty(true);
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
      setPlayheadBeats(audioEngine.getPlayheadBeats());
    } else {
      await audioEngine.play();
      setIsPlaying(true);
    }
  }, []);

  const stop = useCallback(() => {
    audioEngine.stop();
    setIsPlaying(false);
    setPlayheadBeats(0);
    setTrackMeters({});
    setMasterMeter((m) => ({ ...EMPTY_METER, clipping: m.clipping }));
  }, []);

  const seek = useCallback((beats: number) => {
    audioEngine.seek(beats);
    setPlayheadBeats(Math.max(0, beats));
  }, []);

  const resetMasterClip = useCallback(() => {
    audioEngine.resetMasterClip();
    setMasterMeter((m) => ({ ...m, clipping: false }));
  }, []);

  const openProjectById = useCallback(
    async (id: string) => {
      try {
        const opened = await dawApi.openProject(id);
        await hydrateProject(opened);
        showToast(`Opened "${opened.name}"`);
      } catch (err) {
        showToast(`Open failed: ${(err as Error).message}`, "error");
      }
    },
    [hydrateProject, showToast]
  );

  const createNewProject = useCallback(
    async (name: string, bpm = 128) => {
      try {
        const created = await dawApi.createProject({ name, bpm });
        await hydrateProject(created);
        await refreshLists();
        showToast(`Created "${created.name}"`);
      } catch (err) {
        showToast(`Create failed: ${(err as Error).message}`, "error");
      }
    },
    [hydrateProject, refreshLists, showToast]
  );

  const saveCurrentProject = useCallback(async () => {
    const current = projectRef.current;
    if (!current) return;
    setIsSaving(true);
    try {
      const saved = await dawApi.saveProject(current);
      setProject(saved);
      setIsDirty(false);
      setLastSavedAt(saved.updatedAt);
      await refreshLists();
      showToast(`Saved "${saved.name}"`);
    } catch (err) {
      showToast(`Save failed: ${(err as Error).message}`, "error");
    } finally {
      setIsSaving(false);
    }
  }, [refreshLists, showToast]);

  const saveAsProject = useCallback(
    async (newName: string) => {
      const current = projectRef.current;
      if (!current) return;
      setIsSaving(true);
      try {
        const cloned = await dawApi.saveAsProject(current.id, newName, current);
        await hydrateProject(cloned);
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
          timeRangeBeats: { startBeats: clip.timelineStartBeats, endBeats: clip.timelineStartBeats + clip.durationBeats },
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
          timeRangeBeats: { startBeats: clip.timelineStartBeats, endBeats: clip.timelineStartBeats + clip.durationBeats },
          selectedSectionId: null,
        });
      }
    },
    [dispatch, playheadBeats]
  );

  const handleImportedAsset = useCallback(
    async (
      proj: Project,
      res: { asset: Asset; midi?: { notes: MidiNote[]; bpm: number | null; durationBeats: number } },
      addToTimeline: boolean
    ) => {
      let asset = res.asset;
      if (res.midi?.notes) {
        midiNotesCacheRef.current.set(asset.id, res.midi.notes);
      }

      // Fetch real waveform peaks (or client-decode fallback for MP3/M4A)
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
            // keep going
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
        // Persist latest state before uploading so server project.json stays in sync
        await dawApi.saveProject(current);
        const res = await dawApi.importAsset(current.id, file, kind);
        await handleImportedAsset(current, res, addToTimeline);
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
        await dawApi.saveProject(current);
        const res = await dawApi.importFromLibrary(current.id, item.id);
        await handleImportedAsset(current, res, addToTimeline);
      } catch (err) {
        showToast(`Library import failed: ${(err as Error).message}`, "error");
      }
    },
    [handleImportedAsset, showToast]
  );

  const exportStereoWav = useCallback(
    async (useLoopRange = false) => {
      const current = projectRef.current;
      if (!current) return;
      setIsExporting(true);
      try {
        const result = await renderProjectOfflineWav(current, audioEngine, { useLoopRange });
        // Save rendered Stereo WAV into local project exports/ directory
        const savedInfo = await dawApi.uploadExportWav(current.id, result.filename, result.blob);
        // Trigger local browser download
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
    selection,
    setSelection,
    selectedTrack,
    selectedClip,
    isDirty,
    isSaving,
    isExporting,
    lastSavedAt,
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
    exportStereoWav,
  };

  return <DawContext.Provider value={value}>{children}</DawContext.Provider>;
}

export function useDaw(): DawContextValue {
  const ctx = useContext(DawContext);
  if (!ctx) throw new Error("useDaw must be used within DawProvider");
  return ctx;
}
