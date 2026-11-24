import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Copy,
  Flag,
  Magnet,
  Plus,
  Repeat,
  Scissors,
  Trash2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useDaw } from "../commands/store";
import {
  beatsPerBar,
  beatsToSeconds,
  dbToLinear,
  formatDb,
  formatPan,
  snapBeats,
} from "../project/time";
import type { Clip, Track, WaveformData } from "../project/types";
import { makeClientId } from "../commands/executor";

const TRACK_ROW_H = 76;
const SECTION_H = 24;
const RULER_H = 24;

function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace("#", "");
  if (clean.length !== 6) return `rgba(110, 140, 130, ${alpha})`;
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Real PCM waveform or MIDI note mini-preview canvas inside each timeline clip. */
function ClipCanvas({
  clip,
  waveform,
  bpm,
  widthPx,
  heightPx,
  color,
}: {
  clip: Clip;
  waveform?: WaveformData;
  bpm: number;
  widthPx: number;
  heightPx: number;
  color: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.max(12, Math.floor(widthPx));
    const h = Math.max(20, Math.floor(heightPx));
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    if (clip.type === "midi") {
      if (clip.notes.length === 0) return;
      const minPitch = Math.min(...clip.notes.map((n) => n.pitch));
      const maxPitch = Math.max(...clip.notes.map((n) => n.pitch));
      const pitchSpan = Math.max(12, maxPitch - minPitch + 4);
      const maxNoteEnd = clip.notes.reduce((m, n) => Math.max(m, n.startBeat + n.durationBeats), 4);
      const loopLen = clip.loopLengthBeats ?? Math.max(4, Math.ceil(maxNoteEnd / 4) * 4);
      const reps = clip.loop ? Math.ceil(clip.durationBeats / loopLen) : 1;

      ctx.fillStyle = "rgba(18, 24, 30, 0.88)";
      for (let rep = 0; rep < reps; rep++) {
        const repOff = rep * loopLen;
        for (const n of clip.notes) {
          const s = repOff + n.startBeat;
          if (s >= clip.durationBeats) continue;
          const d = Math.min(n.durationBeats, clip.durationBeats - s);
          const x = (s / clip.durationBeats) * w;
          const nw = Math.max(3, (d / clip.durationBeats) * w - 1);
          const normY = 1 - (n.pitch - (minPitch - 2)) / pitchSpan;
          const y = 4 + normY * (h - 12);
          ctx.fillRect(x, y, nw, 4);
        }
      }
      return;
    }

    // Real PCM waveform rendering (never fabricated/random!)
    if (!waveform || waveform.peaks.length === 0 || waveform.durationSec <= 0) {
      ctx.fillStyle = "rgba(20, 22, 26, 0.35)";
      ctx.fillRect(0, h / 2 - 0.5, w, 1);
      return;
    }

    const peaks = waveform.peaks;
    const totalDurSec = waveform.durationSec;
    const clipDurSec = beatsToSeconds(clip.durationBeats, bpm);
    const loopLenSec = clip.loop
      ? Math.max(0.05, clip.loopLengthSec ?? totalDurSec - clip.sourceOffsetSec)
      : totalDurSec;
    const gainScale = Math.min(1.8, dbToLinear(clip.gainDb));
    const midY = h / 2;
    const maxAmp = (h - 8) / 2;

    ctx.fillStyle = "rgba(17, 21, 24, 0.72)";
    const step = w > 500 ? 2 : 1.5;
    for (let x = 0; x < w; x += step) {
      const tInClip = (x / w) * clipDurSec;
      const tInSrc = clip.loop
        ? clip.sourceOffsetSec + (tInClip % loopLenSec)
        : clip.sourceOffsetSec + tInClip;
      if (tInSrc < 0 || tInSrc >= totalDurSec) continue;
      const binIdx = Math.min(peaks.length - 1, Math.floor((tInSrc / totalDurSec) * peaks.length));
      const amp = Math.min(1, peaks[binIdx] * gainScale);
      const barH = Math.max(1.5, amp * maxAmp * 2);
      ctx.fillRect(x, midY - barH / 2, Math.max(1, step - 0.5), barH);
    }

    // Loop cycle subtle vertical divider
    if (clip.loop && loopLenSec > 0.1 && clipDurSec > loopLenSec) {
      ctx.strokeStyle = hexToRgba(color, 0.5);
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      for (let t = loopLenSec; t < clipDurSec; t += loopLenSec) {
        const x = (t / clipDurSec) * w;
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }, [clip, waveform, bpm, widthPx, heightPx, color]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: "100%",
        height: "100%",
        display: "block",
        pointerEvents: "none",
      }}
    />
  );
}

type DragState =
  | {
      mode: "move";
      clipId: string;
      originTrackId: string;
      startX: number;
      startY: number;
      initialStartBeats: number;
      initialTrackIdx: number;
    }
  | {
      mode: "trim-left";
      clipId: string;
      startX: number;
      initialStartBeats: number;
      initialDurationBeats: number;
      initialSourceOffsetSec: number;
    }
  | {
      mode: "trim-right";
      clipId: string;
      startX: number;
      initialDurationBeats: number;
    }
  | {
      mode: "loop-start" | "loop-end" | "loop-body";
      startX: number;
      initialLoopStart: number;
      initialLoopEnd: number;
    }
  | {
      mode: "range-select";
      anchorBeat: number;
    };

interface ArrangementTimelineProps {
  onOpenClipInEditor: (clip: Clip) => void;
}

export function ArrangementTimeline({ onOpenClipInEditor }: ArrangementTimelineProps) {
  const {
    project,
    waveforms,
    selection,
    setSelection,
    selectedClip,
    playheadBeats,
    trackMeters,
    snapEnabled,
    setSnapEnabled,
    gridBeats,
    setGridBeats,
    pixelsPerBeat,
    setPixelsPerBeat,
    dispatch,
    beginTransaction,
    commitTransaction,
    seek,
    showToast,
  } = useDaw();

  const headersScrollRef = useRef<HTMLDivElement | null>(null);
  const timelineScrollRef = useRef<HTMLDivElement | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [renamingTrackId, setRenamingTrackId] = useState<string | null>(null);
  const [renamingTrackVal, setRenamingTrackVal] = useState("");
  const [renamingSectionId, setRenamingSectionId] = useState<string | null>(null);
  const [renamingSectionVal, setRenamingSectionVal] = useState("");

  const bpb = project ? beatsPerBar(project.timeSignature) : 4;
  const totalBeats = project ? Math.max(project.lengthBeats, 64) : 64;
  const timelineWidth = Math.max(900, Math.ceil(totalBeats * pixelsPerBeat) + 120);
  const lanesHeight = Math.max(260, (project?.tracks.length ?? 0) * TRACK_ROW_H + 64);

  // Sync vertical scrolling between track headers and timeline canvas
  const handleTimelineScroll = () => {
    if (headersScrollRef.current && timelineScrollRef.current) {
      headersScrollRef.current.scrollTop = timelineScrollRef.current.scrollTop;
    }
  };

  // Pointer drag handlers for clips, trims, loop bar, and ruler time-range selection
  useEffect(() => {
    if (!drag || !project) return;

    const handleMove = (e: PointerEvent) => {
      const dx = e.clientX - ("startX" in drag ? drag.startX : 0);
      const deltaBeats = dx / pixelsPerBeat;

      if (drag.mode === "move") {
        const rawStart = Math.max(0, drag.initialStartBeats + deltaBeats);
        const snapped = snapBeats(rawStart, gridBeats, snapEnabled);
        const dy = e.clientY - drag.startY;
        const rowDelta = Math.round(dy / TRACK_ROW_H);
        const dstIdx = Math.max(0, Math.min(project.tracks.length - 1, drag.initialTrackIdx + rowDelta));
        const targetTrack = project.tracks[dstIdx];
        const srcTrack = project.tracks.find((t) => t.id === drag.originTrackId);
        const compatible = targetTrack && srcTrack && (targetTrack.type === "midi") === (srcTrack.type === "midi");

        dispatch(
          {
            type: "clip.move",
            payload: {
              clipId: drag.clipId,
              timelineStartBeats: snapped,
              targetTrackId: compatible ? targetTrack.id : undefined,
            },
          },
          { recordHistory: false }
        );
      } else if (drag.mode === "trim-right") {
        const rawDur = Math.max(gridBeats, drag.initialDurationBeats + deltaBeats);
        const snappedDur = Math.max(0.25, snapBeats(rawDur, gridBeats, snapEnabled));
        dispatch(
          {
            type: "clip.trim",
            payload: { clipId: drag.clipId, durationBeats: snappedDur },
          },
          { recordHistory: false }
        );
      } else if (drag.mode === "trim-left") {
        const maxShift = drag.initialDurationBeats - 0.25;
        const clampedDelta = Math.min(maxShift, Math.max(-drag.initialStartBeats, deltaBeats));
        const newStart = snapBeats(drag.initialStartBeats + clampedDelta, gridBeats, snapEnabled);
        const appliedDelta = newStart - drag.initialStartBeats;
        const newDur = Math.max(0.25, drag.initialDurationBeats - appliedDelta);
        const newOffset = Math.max(0, drag.initialSourceOffsetSec + beatsToSeconds(appliedDelta, project.bpm));
        dispatch(
          {
            type: "clip.trim",
            payload: {
              clipId: drag.clipId,
              timelineStartBeats: newStart,
              durationBeats: newDur,
              sourceOffsetSec: newOffset,
            },
          },
          { recordHistory: false }
        );
      } else if (drag.mode === "loop-start") {
        const nextStart = Math.min(
          drag.initialLoopEnd - 1,
          snapBeats(Math.max(0, drag.initialLoopStart + deltaBeats), gridBeats, snapEnabled)
        );
        dispatch(
          {
            type: "transport.setLoop",
            payload: { enabled: true, startBeats: nextStart, endBeats: drag.initialLoopEnd },
          },
          { recordHistory: false }
        );
      } else if (drag.mode === "loop-end") {
        const nextEnd = Math.max(
          drag.initialLoopStart + 1,
          snapBeats(drag.initialLoopEnd + deltaBeats, gridBeats, snapEnabled)
        );
        dispatch(
          {
            type: "transport.setLoop",
            payload: { enabled: true, startBeats: drag.initialLoopStart, endBeats: nextEnd },
          },
          { recordHistory: false }
        );
      } else if (drag.mode === "loop-body") {
        const len = drag.initialLoopEnd - drag.initialLoopStart;
        const nextStart = snapBeats(Math.max(0, drag.initialLoopStart + deltaBeats), gridBeats, snapEnabled);
        dispatch(
          {
            type: "transport.setLoop",
            payload: { enabled: true, startBeats: nextStart, endBeats: nextStart + len },
          },
          { recordHistory: false }
        );
      } else if (drag.mode === "range-select" && timelineScrollRef.current) {
        const rect = timelineScrollRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left + timelineScrollRef.current.scrollLeft;
        const beat = snapBeats(Math.max(0, x / pixelsPerBeat), gridBeats, snapEnabled);
        const start = Math.min(drag.anchorBeat, beat);
        const end = Math.max(drag.anchorBeat + gridBeats, beat);
        setSelection((prev) => ({
          ...prev,
          timeRangeBeats: { startBeats: start, endBeats: end },
          selectedSectionId: null,
        }));
      }
    };

    const handleUp = () => {
      if (drag.mode === "move" || drag.mode === "trim-left" || drag.mode === "trim-right") {
        commitTransaction();
      }
      setDrag(null);
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [drag, project, pixelsPerBeat, gridBeats, snapEnabled, dispatch, commitTransaction, setSelection]);

  const bars = useMemo(() => {
    const count = Math.ceil(totalBeats / bpb);
    return Array.from({ length: count }, (_, i) => i);
  }, [totalBeats, bpb]);

  if (!project) return null;

  const handleSplitSelected = () => {
    if (!selectedClip) {
      showToast("Select a clip to split at the playhead", "error");
      return;
    }
    dispatch({
      type: "clip.split",
      payload: { clipId: selectedClip.id, splitBeat: playheadBeats },
    });
  };

  const handleDuplicateSelected = () => {
    if (!selectedClip) return;
    dispatch({ type: "clip.duplicate", payload: { clipId: selectedClip.id } });
  };

  const handleDeleteSelected = () => {
    for (const cid of selection.selectedClipIds) {
      dispatch({ type: "clip.delete", payload: { clipId: cid } });
    }
    setSelection((prev) => ({ ...prev, selectedClipIds: [] }));
  };

  const handleAddSection = () => {
    const start = snapBeats(playheadBeats, bpb, true);
    dispatch({
      type: "section.add",
      payload: {
        name: `SECTION ${project.sections.length + 1}`,
        startBeats: start,
        endBeats: start + bpb * 4,
        color: "#4a5968",
      },
    });
  };

  const handleAddTrack = (type: Track["type"]) => {
    const label = type === "midi" ? "Synth" : type === "stem" ? "Stem" : "Audio";
    const id = makeClientId("trk");
    dispatch({
      type: "track.add",
      payload: {
        id,
        name: `${label} ${project.tracks.length + 1}`,
        type,
        stemLabel: type === "stem" ? "estimated" : undefined,
      },
    });
    setSelection((prev) => ({ ...prev, selectedTrackId: id }));
  };

  const handleCreateEmptyMidiClip = (track: Track) => {
    if (track.type !== "midi") return;
    const start = snapBeats(playheadBeats, bpb, true);
    const clipId = makeClientId("clp");
    const clip: Clip = {
      id: clipId,
      name: `${track.name} Clip`,
      type: "midi",
      assetId: null,
      timelineStartBeats: start,
      durationBeats: bpb * 4,
      sourceOffsetSec: 0,
      sourceDurationSec: 0,
      loop: false,
      loopLengthSec: null,
      loopLengthBeats: bpb * 4,
      gainDb: 0,
      notes: [
        { id: makeClientId("note"), pitch: 60, velocity: 100, startBeat: 0, durationBeats: 1 },
        { id: makeClientId("note"), pitch: 63, velocity: 96, startBeat: 1, durationBeats: 1 },
        { id: makeClientId("note"), pitch: 67, velocity: 104, startBeat: 2, durationBeats: 1 },
        { id: makeClientId("note"), pitch: 72, velocity: 108, startBeat: 3, durationBeats: 1 },
      ],
    };
    dispatch({ type: "clip.add", payload: { trackId: track.id, clip } });
    setSelection({
      selectedTrackId: track.id,
      selectedClipIds: [clipId],
      timeRangeBeats: { startBeats: start, endBeats: start + clip.durationBeats },
      selectedSectionId: null,
    });
    onOpenClipInEditor(clip);
  };

  const handleRulerPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!timelineScrollRef.current) return;
    const rect = timelineScrollRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left + timelineScrollRef.current.scrollLeft;
    const rawBeat = Math.max(0, x / pixelsPerBeat);
    const beat = snapBeats(rawBeat, gridBeats, snapEnabled);
    if (e.shiftKey) {
      setDrag({ mode: "range-select", anchorBeat: beat });
      setSelection((prev) => ({
        ...prev,
        timeRangeBeats: { startBeats: beat, endBeats: beat + gridBeats },
        selectedSectionId: null,
      }));
    } else {
      seek(beat);
    }
  };

  return (
    <section className="arrangement-container" data-testid="arrangement-timeline">
      {/* Compact Timeline Toolbar */}
      <div className="arrangement-toolbar">
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <button
            className={snapEnabled ? "pill-toggle active" : ""}
            style={{ height: 22, padding: "0 7px", fontSize: 11 }}
            onClick={() => setSnapEnabled(!snapEnabled)}
            title="Toggle Snap to Grid"
          >
            <Magnet size={11} />
            Snap
          </button>
          <select
            aria-label="Grid resolution"
            value={gridBeats}
            onChange={(e) => setGridBeats(parseFloat(e.target.value))}
            style={{ height: 22, padding: "0 4px", fontSize: 11 }}
          >
            <option value={4}>1 Bar</option>
            <option value={2}>1/2</option>
            <option value={1}>1/4 Beat</option>
            <option value={0.5}>1/8</option>
            <option value={0.25}>1/16</option>
          </select>

          <div style={{ width: 1, height: 14, background: "var(--border-subtle)" }} />

          <button
            style={{ height: 22, padding: "0 7px", fontSize: 11 }}
            disabled={!selectedClip}
            onClick={handleSplitSelected}
            title="Split Selected Clip at Playhead (Cmd+E)"
            data-testid="btn-split-clip"
          >
            <Scissors size={11} />
            Split
          </button>
          <button
            style={{ height: 22, padding: "0 7px", fontSize: 11 }}
            disabled={!selectedClip}
            onClick={handleDuplicateSelected}
            title="Duplicate Selected Clip (Cmd+D)"
          >
            <Copy size={11} />
            Duplicate
          </button>
          <button
            style={{ height: 22, padding: "0 7px", fontSize: 11 }}
            disabled={selection.selectedClipIds.length === 0}
            onClick={handleDeleteSelected}
            title="Delete Selected Clip(s) (Delete)"
          >
            <Trash2 size={11} />
          </button>
          <button
            style={{ height: 22, padding: "0 7px", fontSize: 11 }}
            onClick={handleAddSection}
            title="Add Section Marker at Playhead"
          >
            <Flag size={11} />
            + Section
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: "var(--text-muted)", fontSize: 10 }}>Shift+Drag ruler to select range</span>
          <button
            className="icon-btn"
            title="Zoom Out"
            onClick={() => setPixelsPerBeat((z) => Math.max(8, Math.round(z * 0.8)))}
          >
            <ZoomOut size={13} />
          </button>
          <input
            type="range"
            className="mini-slider"
            style={{ width: 68 }}
            min={8}
            max={80}
            value={pixelsPerBeat}
            aria-label="Timeline horizontal zoom"
            onChange={(e) => setPixelsPerBeat(parseInt(e.target.value, 10))}
          />
          <button
            className="icon-btn"
            title="Zoom In"
            onClick={() => setPixelsPerBeat((z) => Math.min(80, Math.round(z * 1.25)))}
          >
            <ZoomIn size={13} />
          </button>
        </div>
      </div>

      {/* Main Split: Left Track Headers + Right Scrollable Arrangement Grid */}
      <div className="arrangement-scroll">
        {/* Track Headers Column */}
        <div className="track-column">
          <div className="track-column-corner">
            <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", color: "var(--text-muted)" }}>
              TRACKS ({project.tracks.length})
            </span>
            <div style={{ display: "flex", gap: 3 }}>
              <button
                style={{ fontSize: 10, padding: "2px 5px" }}
                onClick={() => handleAddTrack("audio")}
                title="Add Audio Track"
                data-testid="btn-add-audio-track"
              >
                +Aud
              </button>
              <button
                style={{ fontSize: 10, padding: "2px 5px" }}
                onClick={() => handleAddTrack("midi")}
                title="Add MIDI Track"
                data-testid="btn-add-midi-track"
              >
                +MIDI
              </button>
            </div>
          </div>

          <div className="track-headers-scroll" ref={headersScrollRef}>
            {project.tracks.map((track, idx) => {
              const selected = selection.selectedTrackId === track.id;
              const meter = trackMeters[track.id];
              const levelPct = meter ? Math.min(100, Math.round(Math.max(meter.peakL, meter.peakR) * 100)) : 0;

              return (
                <div
                  key={track.id}
                  className={`track-header ${selected ? "selected" : ""}`}
                  data-testid={`track-header-${track.id}`}
                  onClick={() =>
                    setSelection((prev) => ({
                      ...prev,
                      selectedTrackId: track.id,
                    }))
                  }
                >
                  <div className="track-color-bar" style={{ background: track.color }} />

                  <div className="track-header-main">
                    <div className="track-header-top">
                      {renamingTrackId === track.id ? (
                        <input
                          autoFocus
                          value={renamingTrackVal}
                          style={{ width: 112, height: 18, padding: "0 4px", fontSize: 11 }}
                          onChange={(e) => setRenamingTrackVal(e.target.value)}
                          onBlur={() => {
                            if (renamingTrackVal.trim()) {
                              dispatch({
                                type: "track.rename",
                                payload: { trackId: track.id, name: renamingTrackVal.trim() },
                              });
                            }
                            setRenamingTrackId(null);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                            if (e.key === "Escape") setRenamingTrackId(null);
                          }}
                        />
                      ) : (
                        <div
                          className="track-name"
                          onDoubleClick={(e) => {
                            e.stopPropagation();
                            setRenamingTrackId(track.id);
                            setRenamingTrackVal(track.name);
                          }}
                          title="Double-click to rename track"
                        >
                          {track.name}
                        </div>
                      )}

                      <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
                        {track.type === "midi" && (
                          <button
                            className="icon-btn"
                            style={{ width: 18, height: 18 }}
                            title="Create MIDI Clip at Playhead"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCreateEmptyMidiClip(track);
                            }}
                          >
                            <Plus size={11} />
                          </button>
                        )}
                        <button
                          className="icon-btn"
                          style={{ width: 16, height: 16 }}
                          disabled={idx === 0}
                          title="Move track up"
                          onClick={(e) => {
                            e.stopPropagation();
                            dispatch({ type: "track.reorder", payload: { fromIndex: idx, toIndex: idx - 1 } });
                          }}
                        >
                          <ArrowUp size={10} />
                        </button>
                        <button
                          className="icon-btn"
                          style={{ width: 16, height: 16 }}
                          disabled={idx === project.tracks.length - 1}
                          title="Move track down"
                          onClick={(e) => {
                            e.stopPropagation();
                            dispatch({ type: "track.reorder", payload: { fromIndex: idx, toIndex: idx + 1 } });
                          }}
                        >
                          <ArrowDown size={10} />
                        </button>
                        <button
                          className="icon-btn"
                          style={{ width: 16, height: 16 }}
                          title="Delete track (original assets are preserved)"
                          onClick={(e) => {
                            e.stopPropagation();
                            dispatch({ type: "track.remove", payload: { trackId: track.id } });
                          }}
                        >
                          <Trash2 size={10} />
                        </button>
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <span className="track-type-label">
                        {track.type === "stem" ? "STEM · est." : track.type.toUpperCase()}
                      </span>
                      <span className="mono" style={{ fontSize: 9, color: "var(--text-muted)" }}>
                        {formatDb(track.gainDb)} · {formatPan(track.pan)}
                      </span>
                    </div>

                    <div className="track-controls-row">
                      <button
                        className={`ms-btn ${track.mute ? "mute-on" : ""}`}
                        title="Mute Track"
                        onClick={(e) => {
                          e.stopPropagation();
                          dispatch({ type: "track.setMute", payload: { trackId: track.id, mute: !track.mute } });
                        }}
                      >
                        M
                      </button>
                      <button
                        className={`ms-btn ${track.solo ? "solo-on" : ""}`}
                        title="Solo Track"
                        onClick={(e) => {
                          e.stopPropagation();
                          dispatch({ type: "track.setSolo", payload: { trackId: track.id, solo: !track.solo } });
                        }}
                      >
                        S
                      </button>

                      {/* Volume Slider */}
                      <input
                        type="range"
                        className="mini-slider"
                        style={{ width: 72 }}
                        min={-60}
                        max={6}
                        step={0.5}
                        value={track.gainDb}
                        title={`Volume: ${formatDb(track.gainDb)}`}
                        onClick={(e) => e.stopPropagation()}
                        onPointerDown={beginTransaction}
                        onPointerUp={commitTransaction}
                        onChange={(e) =>
                          dispatch({
                            type: "track.setGain",
                            payload: { trackId: track.id, gainDb: parseFloat(e.target.value) },
                          })
                        }
                      />

                      {/* Pan Slider */}
                      <input
                        type="range"
                        className="mini-slider"
                        style={{ width: 38 }}
                        min={-1}
                        max={1}
                        step={0.02}
                        value={track.pan}
                        title={`Pan: ${formatPan(track.pan)}`}
                        onClick={(e) => e.stopPropagation()}
                        onPointerDown={beginTransaction}
                        onPointerUp={commitTransaction}
                        onChange={(e) =>
                          dispatch({
                            type: "track.setPan",
                            payload: { trackId: track.id, pan: parseFloat(e.target.value) },
                          })
                        }
                      />
                    </div>

                    {/* Real-time Audio Signal Level Strip */}
                    <div
                      style={{
                        height: 3,
                        background: "#121418",
                        borderRadius: 1,
                        overflow: "hidden",
                        marginTop: 2,
                      }}
                    >
                      <div
                        style={{
                          width: `${levelPct}%`,
                          height: "100%",
                          background: levelPct > 92 ? "var(--accent-danger)" : track.color,
                          transition: "width 45ms linear",
                        }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
            <div style={{ height: 64 }} />
          </div>
        </div>

        {/* Scrollable Arrangement Timeline Viewport */}
        <div
          className="timeline-viewport"
          ref={timelineScrollRef}
          onScroll={handleTimelineScroll}
        >
          <div style={{ width: timelineWidth, position: "relative", minHeight: "100%" }}>
            {/* Sticky Top Header: Section Markers + Bar/Beat Ruler */}
            <div
              style={{
                position: "sticky",
                top: 0,
                zIndex: 12,
                background: "var(--bg-panel)",
                borderBottom: "1px solid var(--border-default)",
              }}
            >
              {/* Section Markers Bar */}
              <div
                style={{
                  height: SECTION_H,
                  position: "relative",
                  borderBottom: "1px solid var(--border-subtle)",
                  background: "#16181c",
                }}
              >
                {project.sections.map((sec) => {
                  const left = sec.startBeats * pixelsPerBeat;
                  const width = Math.max(24, (sec.endBeats - sec.startBeats) * pixelsPerBeat);
                  const isSel = selection.selectedSectionId === sec.id;
                  return (
                    <div
                      key={sec.id}
                      onClick={() => {
                        seek(sec.startBeats);
                        setSelection((prev) => ({
                          ...prev,
                          selectedSectionId: sec.id,
                          timeRangeBeats: { startBeats: sec.startBeats, endBeats: sec.endBeats },
                        }));
                      }}
                      onDoubleClick={(e) => {
                        e.stopPropagation();
                        setRenamingSectionId(sec.id);
                        setRenamingSectionVal(sec.name);
                      }}
                      title={`${sec.name} — Click to jump & select bar range, double-click to rename`}
                      style={{
                        position: "absolute",
                        left,
                        width: width - 1,
                        top: 2,
                        height: SECTION_H - 4,
                        background: hexToRgba(sec.color, isSel ? 0.72 : 0.45),
                        border: `1px solid ${isSel ? "var(--accent-playhead)" : hexToRgba(sec.color, 0.85)}`,
                        borderRadius: 3,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: "0 18px 0 6px",
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: "0.08em",
                        color: "var(--text-primary)",
                        cursor: "pointer",
                        overflow: "hidden",
                      }}
                    >
                      {renamingSectionId === sec.id ? (
                        <input
                          autoFocus
                          value={renamingSectionVal}
                          style={{ width: "100%", height: 16, fontSize: 10, textAlign: "center" }}
                          onChange={(e) => setRenamingSectionVal(e.target.value)}
                          onBlur={() => {
                            dispatch({
                              type: "section.rename",
                              payload: { sectionId: sec.id, name: renamingSectionVal },
                            });
                            setRenamingSectionId(null);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                            if (e.key === "Escape") setRenamingSectionId(null);
                          }}
                        />
                      ) : (
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {sec.name}
                        </span>
                      )}
                      <button
                        className="icon-btn"
                        style={{
                          position: "absolute",
                          right: 2,
                          width: 14,
                          height: 14,
                          fontSize: 10,
                          opacity: 0.65,
                        }}
                        title="Remove section marker"
                        onClick={(e) => {
                          e.stopPropagation();
                          dispatch({ type: "section.remove", payload: { sectionId: sec.id } });
                        }}
                      >
                        ×
                      </button>
                    </div>
                  );
                })}
              </div>

              {/* Bar / Beat Ruler + Draggable Loop Region */}
              <div
                style={{
                  height: RULER_H,
                  position: "relative",
                  cursor: "pointer",
                  background: "#181a1f",
                }}
                onPointerDown={handleRulerPointerDown}
                data-testid="timeline-ruler"
              >
                {/* Loop Region Brace */}
                {project.loopRegion.endBeats > project.loopRegion.startBeats && (
                  <div
                    style={{
                      position: "absolute",
                      top: 0,
                      height: 8,
                      left: project.loopRegion.startBeats * pixelsPerBeat,
                      width: (project.loopRegion.endBeats - project.loopRegion.startBeats) * pixelsPerBeat,
                      background: project.loopRegion.enabled
                        ? "rgba(99, 180, 124, 0.7)"
                        : "rgba(130, 140, 155, 0.35)",
                      borderBottom: `1px solid ${project.loopRegion.enabled ? "#8ce0a6" : "#555d6b"}`,
                      cursor: "grab",
                      zIndex: 4,
                    }}
                    title="Drag to move Loop Region; drag edges to resize"
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      setDrag({
                        mode: "loop-body",
                        startX: e.clientX,
                        initialLoopStart: project.loopRegion.startBeats,
                        initialLoopEnd: project.loopRegion.endBeats,
                      });
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        left: -3,
                        top: 0,
                        bottom: 0,
                        width: 7,
                        cursor: "ew-resize",
                      }}
                      onPointerDown={(e) => {
                        e.stopPropagation();
                        setDrag({
                          mode: "loop-start",
                          startX: e.clientX,
                          initialLoopStart: project.loopRegion.startBeats,
                          initialLoopEnd: project.loopRegion.endBeats,
                        });
                      }}
                    />
                    <div
                      style={{
                        position: "absolute",
                        right: -3,
                        top: 0,
                        bottom: 0,
                        width: 7,
                        cursor: "ew-resize",
                      }}
                      onPointerDown={(e) => {
                        e.stopPropagation();
                        setDrag({
                          mode: "loop-end",
                          startX: e.clientX,
                          initialLoopStart: project.loopRegion.startBeats,
                          initialLoopEnd: project.loopRegion.endBeats,
                        });
                      }}
                    />
                  </div>
                )}

                {/* Bar numbers & ticks */}
                {bars.map((barIdx) => {
                  const left = barIdx * bpb * pixelsPerBeat;
                  return (
                    <div
                      key={barIdx}
                      style={{
                        position: "absolute",
                        left,
                        top: 0,
                        bottom: 0,
                        borderLeft: "1px solid var(--grid-bar)",
                        paddingLeft: 4,
                        paddingTop: 9,
                        fontSize: 10,
                        color: barIdx % 2 === 0 ? "var(--text-secondary)" : "var(--text-muted)",
                        pointerEvents: "none",
                      }}
                      className="mono"
                    >
                      {barIdx + 1}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Arrangement Grid & Track Lanes */}
            <div style={{ position: "relative", height: lanesHeight }}>
              {/* Vertical Bar & Beat Grid Background */}
              <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
                {bars.map((barIdx) => {
                  const barW = bpb * pixelsPerBeat;
                  const left = barIdx * barW;
                  return (
                    <div
                      key={barIdx}
                      style={{
                        position: "absolute",
                        left,
                        top: 0,
                        bottom: 0,
                        width: barW,
                        background: barIdx % 2 === 1 ? "var(--bg-timeline-alt)" : "transparent",
                        borderLeft: "1px solid var(--grid-bar)",
                      }}
                    >
                      {pixelsPerBeat >= 14 &&
                        Array.from({ length: Math.floor(bpb) - 1 }, (_, beatOff) => (
                          <div
                            key={beatOff}
                            style={{
                              position: "absolute",
                              left: (beatOff + 1) * pixelsPerBeat,
                              top: 0,
                              bottom: 0,
                              borderLeft: "1px solid var(--grid-beat)",
                            }}
                          />
                        ))}
                    </div>
                  );
                })}
              </div>

              {/* Loop Region Vertical Tint */}
              {project.loopRegion.enabled && (
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: project.loopRegion.startBeats * pixelsPerBeat,
                    width: (project.loopRegion.endBeats - project.loopRegion.startBeats) * pixelsPerBeat,
                    background: "rgba(99, 180, 124, 0.05)",
                    borderLeft: "1px dashed rgba(99, 180, 124, 0.35)",
                    borderRight: "1px dashed rgba(99, 180, 124, 0.35)",
                    pointerEvents: "none",
                    zIndex: 1,
                  }}
                />
              )}

              {/* Selected Time Range Highlight */}
              {selection.timeRangeBeats && (
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: selection.timeRangeBeats.startBeats * pixelsPerBeat,
                    width:
                      (selection.timeRangeBeats.endBeats - selection.timeRangeBeats.startBeats) *
                      pixelsPerBeat,
                    background: "rgba(229, 184, 75, 0.045)",
                    pointerEvents: "none",
                    zIndex: 1,
                  }}
                />
              )}

              {/* Track Rows & Clips */}
              {project.tracks.map((track, trackIdx) => {
                const isTrackSel = selection.selectedTrackId === track.id;
                return (
                  <div
                    key={track.id}
                    style={{
                      height: TRACK_ROW_H,
                      position: "relative",
                      borderBottom: "1px solid var(--border-subtle)",
                      background: isTrackSel ? "rgba(255,255,255,0.018)" : "transparent",
                    }}
                    onClick={() =>
                      setSelection((prev) => ({
                        ...prev,
                        selectedTrackId: track.id,
                      }))
                    }
                    onDoubleClick={() => {
                      if (track.type === "midi") handleCreateEmptyMidiClip(track);
                    }}
                  >
                    {track.clips.map((clip) => {
                      const left = clip.timelineStartBeats * pixelsPerBeat;
                      const width = Math.max(18, clip.durationBeats * pixelsPerBeat);
                      const isClipSelected = selection.selectedClipIds.includes(clip.id);
                      const wf = clip.assetId ? waveforms[clip.assetId] : undefined;

                      return (
                        <div
                          key={clip.id}
                          data-testid={`clip-${clip.id}`}
                          onPointerDown={(e) => {
                            e.stopPropagation();
                            if (e.shiftKey || e.metaKey || e.ctrlKey) {
                              setSelection((prev) => ({
                                ...prev,
                                selectedTrackId: track.id,
                                selectedClipIds: prev.selectedClipIds.includes(clip.id)
                                  ? prev.selectedClipIds.filter((id) => id !== clip.id)
                                  : [...prev.selectedClipIds, clip.id],
                              }));
                            } else {
                              setSelection({
                                selectedTrackId: track.id,
                                selectedClipIds: [clip.id],
                                timeRangeBeats: {
                                  startBeats: clip.timelineStartBeats,
                                  endBeats: clip.timelineStartBeats + clip.durationBeats,
                                },
                                selectedSectionId: null,
                              });
                            }
                            beginTransaction();
                            setDrag({
                              mode: "move",
                              clipId: clip.id,
                              originTrackId: track.id,
                              startX: e.clientX,
                              startY: e.clientY,
                              initialStartBeats: clip.timelineStartBeats,
                              initialTrackIdx: trackIdx,
                            });
                          }}
                          onDoubleClick={(e) => {
                            e.stopPropagation();
                            onOpenClipInEditor(clip);
                          }}
                          style={{
                            position: "absolute",
                            left,
                            top: 5,
                            width: width - 1,
                            height: TRACK_ROW_H - 10,
                            background: hexToRgba(track.color, isClipSelected ? 0.78 : 0.62),
                            border: isClipSelected
                              ? "1.5px solid var(--accent-playhead)"
                              : `1px solid ${hexToRgba(track.color, 0.92)}`,
                            borderRadius: 5,
                            overflow: "hidden",
                            cursor: "grab",
                            zIndex: isClipSelected ? 5 : 3,
                            boxShadow: isClipSelected
                              ? "0 0 0 1px rgba(229, 184, 75, 0.35), 0 3px 10px rgba(0,0,0,0.4)"
                              : "none",
                            opacity: track.mute ? 0.42 : 1,
                          }}
                        >
                          {/* Clip Header */}
                          <div
                            style={{
                              height: 17,
                              padding: "0 6px",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              background: "rgba(14, 16, 20, 0.32)",
                              fontSize: 10,
                              fontWeight: 600,
                              color: "#111317",
                            }}
                          >
                            <span
                              style={{
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                                color: "#eef2f6",
                                textShadow: "0 1px 2px rgba(0,0,0,0.55)",
                              }}
                            >
                              {clip.name}
                            </span>
                            {clip.loop && <Repeat size={10} color="#eef2f6" />}
                          </div>

                          {/* Real Waveform / MIDI Preview Body */}
                          <div style={{ height: TRACK_ROW_H - 29, position: "relative" }}>
                            <ClipCanvas
                              clip={clip}
                              waveform={wf}
                              bpm={project.bpm}
                              widthPx={width}
                              heightPx={TRACK_ROW_H - 29}
                              color={track.color}
                            />
                          </div>

                          {/* Left Non-Destructive Trim Handle */}
                          <div
                            title="Drag to trim clip start"
                            style={{
                              position: "absolute",
                              left: 0,
                              top: 0,
                              bottom: 0,
                              width: 7,
                              cursor: "ew-resize",
                            }}
                            onPointerDown={(e) => {
                              e.stopPropagation();
                              beginTransaction();
                              setDrag({
                                mode: "trim-left",
                                clipId: clip.id,
                                startX: e.clientX,
                                initialStartBeats: clip.timelineStartBeats,
                                initialDurationBeats: clip.durationBeats,
                                initialSourceOffsetSec: clip.sourceOffsetSec,
                              });
                            }}
                          />

                          {/* Right Non-Destructive Trim / Loop Extend Handle */}
                          <div
                            title="Drag to trim or extend clip length"
                            style={{
                              position: "absolute",
                              right: 0,
                              top: 0,
                              bottom: 0,
                              width: 7,
                              cursor: "ew-resize",
                            }}
                            onPointerDown={(e) => {
                              e.stopPropagation();
                              beginTransaction();
                              setDrag({
                                mode: "trim-right",
                                clipId: clip.id,
                                startX: e.clientX,
                                initialDurationBeats: clip.durationBeats,
                              });
                            }}
                          />
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>

            {/* Audio-Clock Playhead Indicator spanning Ruler + All Tracks */}
            <div
              style={{
                position: "absolute",
                top: SECTION_H,
                bottom: 0,
                left: playheadBeats * pixelsPerBeat,
                width: 1.5,
                background: "var(--accent-playhead)",
                pointerEvents: "none",
                zIndex: 15,
              }}
              data-testid="playhead"
            >
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  left: -5,
                  width: 0,
                  height: 0,
                  borderLeft: "5.5px solid transparent",
                  borderRight: "5.5px solid transparent",
                  borderTop: "8px solid var(--accent-playhead)",
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
