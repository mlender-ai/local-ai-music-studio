import React, { useEffect, useState } from "react";
import {
  Circle,
  Download,
  FilePlus,
  Pause,
  Play,
  Redo2,
  Repeat,
  Save,
  Square,
  Undo2,
  Volume2,
} from "lucide-react";
import { useDaw } from "../commands/store";
import { beatsToSeconds, formatBarBeatTick, formatDb, formatTimeMs } from "../project/time";

interface TransportBarProps {
  onOpenNewModal: () => void;
  onOpenSaveAsModal: () => void;
  onOpenExportModal: () => void;
}

export function TransportBar({
  onOpenNewModal,
  onOpenSaveAsModal,
  onOpenExportModal,
}: TransportBarProps) {
  const {
    project,
    isDirty,
    isSaving,
    isExporting,
    canUndo,
    canRedo,
    isPlaying,
    playheadBeats,
    masterMeter,
    dispatch,
    beginTransaction,
    commitTransaction,
    undo,
    redo,
    playPause,
    stop,
    resetMasterClip,
    saveCurrentProject,
  } = useDaw();

  const [nameDraft, setNameDraft] = useState(project?.name ?? "");
  const [bpmDraft, setBpmDraft] = useState(project ? project.bpm.toFixed(2) : "128.00");

  useEffect(() => {
    setNameDraft(project?.name ?? "");
  }, [project?.id, project?.name]);

  useEffect(() => {
    if (project) setBpmDraft(project.bpm.toFixed(2));
  }, [project?.bpm]);

  if (!project) return <header className="transport-bar" />;

  const commitName = () => {
    const trimmed = nameDraft.trim();
    if (trimmed && trimmed !== project.name) {
      dispatch({ type: "project.rename", payload: { name: trimmed } });
    } else {
      setNameDraft(project.name);
    }
  };

  const commitBpm = () => {
    const parsed = parseFloat(bpmDraft);
    if (Number.isFinite(parsed) && parsed >= 30 && parsed <= 300) {
      if (Math.abs(parsed - project.bpm) > 0.001) {
        dispatch({ type: "project.setTempo", payload: { bpm: parsed } });
      }
      setBpmDraft(parsed.toFixed(2));
    } else {
      setBpmDraft(project.bpm.toFixed(2));
    }
  };

  const currentSec = beatsToSeconds(playheadBeats, project.bpm);
  const meterPctL = Math.min(100, Math.round(masterMeter.peakL * 100));
  const meterPctR = Math.min(100, Math.round(masterMeter.peakR * 100));

  return (
    <header className="transport-bar" data-testid="transport-bar">
      {/* Left: Brand, Project Name, New/SaveAs, Undo/Redo */}
      <div className="transport-group">
        <div className="brand-mark">
          <span className="brand-dot" />
          STUDIO
        </div>
        <input
          className="project-name-input"
          aria-label="Project name"
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={commitName}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          }}
        />
        <button title="New Project" onClick={onOpenNewModal} data-testid="btn-new-project">
          <FilePlus size={13} />
          New
        </button>
        <button title="Save Copy As..." onClick={onOpenSaveAsModal}>
          Save As
        </button>
        <button
          className="transport-btn"
          title="Undo (Cmd+Z)"
          disabled={!canUndo}
          onClick={undo}
          data-testid="btn-undo"
        >
          <Undo2 size={13} />
        </button>
        <button
          className="transport-btn"
          title="Redo (Cmd+Shift+Z)"
          disabled={!canRedo}
          onClick={redo}
          data-testid="btn-redo"
        >
          <Redo2 size={13} />
        </button>
      </div>

      {/* Center: Playback Controls, BPM, Meter, Position LCD, Loop */}
      <div className="transport-group">
        <button
          className={`transport-btn ${isPlaying ? "play-active" : ""}`}
          title="Play / Pause (Space)"
          onClick={() => void playPause()}
          data-testid="btn-play"
        >
          {isPlaying ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
        </button>
        <button className="transport-btn" title="Stop & Return to Bar 1" onClick={stop} data-testid="btn-stop">
          <Square size={12} fill="currentColor" />
        </button>
        <button
          className="transport-btn record-disabled"
          disabled
          title="Audio/MIDI Recording is not enabled in Phase 01"
          aria-label="Record disabled in Phase 01"
        >
          <Circle size={11} fill="currentColor" />
        </button>

        <div className="lcd-readout">
          <div className="lcd-field" title="Tempo (BPM) — MIDI follows BPM; audio clips keep original length in Phase 01">
            <input
              className="lcd-input"
              aria-label="BPM"
              value={bpmDraft}
              onChange={(e) => setBpmDraft(e.target.value)}
              onBlur={commitBpm}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              }}
            />
            <span style={{ fontSize: 10, color: "var(--text-muted)" }}>BPM</span>
          </div>

          <select
            aria-label="Time signature"
            value={`${project.timeSignature.numerator}/${project.timeSignature.denominator}`}
            onChange={(e) => {
              const [num, den] = e.target.value.split("/").map(Number);
              dispatch({
                type: "project.setTimeSignature",
                payload: { numerator: num, denominator: den as 2 | 4 | 8 | 16 },
              });
            }}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            <option value="4/4">4/4</option>
            <option value="3/4">3/4</option>
            <option value="6/8">6/8</option>
          </select>

          <div
            style={{
              width: 1,
              height: 16,
              background: "var(--border-subtle)",
            }}
          />

          <span className="lcd-position mono" data-testid="lcd-position">
            {formatBarBeatTick(playheadBeats, project.timeSignature)}
          </span>
          <span className="lcd-seconds mono">{formatTimeMs(currentSec)}</span>
        </div>

        <button
          className={`pill-toggle ${project.loopRegion.enabled ? "active" : ""}`}
          onClick={() =>
            dispatch({
              type: "transport.setLoop",
              payload: { enabled: !project.loopRegion.enabled },
            })
          }
          title="Toggle Loop Region"
          data-testid="btn-loop"
        >
          <Repeat size={13} />
          Loop
        </button>
      </div>

      {/* Right: Master Volume & Meter, Save, Export */}
      <div className="transport-group">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            padding: "0 5px",
            borderRight: "1px solid var(--border-subtle)",
          }}
          title={`Master Output: ${formatDb(project.masterGainDb)}`}
        >
          <Volume2 size={13} color="var(--text-secondary)" />
          <input
            type="range"
            className="mini-slider"
            style={{ width: 50 }}
            min={-60}
            max={6}
            step={0.5}
            value={project.masterGainDb}
            onPointerDown={beginTransaction}
            onPointerUp={commitTransaction}
            onChange={(e) =>
              dispatch({
                type: "project.setMasterGain",
                payload: { gainDb: parseFloat(e.target.value) },
              })
            }
          />
          <div style={{ display: "flex", flexDirection: "column", gap: 2, width: 28 }}>
            <div style={{ height: 4, background: "#111317", borderRadius: 1, overflow: "hidden" }}>
              <div
                style={{
                  width: `${meterPctL}%`,
                  height: "100%",
                  background: meterPctL > 92 ? "var(--accent-danger)" : "var(--accent-play)",
                }}
              />
            </div>
            <div style={{ height: 4, background: "#111317", borderRadius: 1, overflow: "hidden" }}>
              <div
                style={{
                  width: `${meterPctR}%`,
                  height: "100%",
                  background: meterPctR > 92 ? "var(--accent-danger)" : "var(--accent-play)",
                }}
              />
            </div>
          </div>
          {masterMeter.clipping && (
            <button
              onClick={resetMasterClip}
              title="Output clipped! Click to reset clip indicator."
              style={{
                background: "var(--accent-danger)",
                borderColor: "#f07575",
                color: "#fff",
                fontSize: 9,
                fontWeight: 700,
                padding: "1px 4px",
              }}
            >
              CLIP
            </button>
          )}
        </div>

        <span className={`save-badge ${isDirty ? "dirty" : ""}`} data-testid="save-status">
          {isSaving ? "Saving…" : isDirty ? "Unsaved" : "Saved"}
        </span>
        <button
          onClick={() => void saveCurrentProject()}
          disabled={isSaving}
          title="Save Project (Cmd+S)"
          data-testid="btn-save"
        >
          <Save size={13} />
          Save
        </button>
        <button
          className="btn-primary"
          onClick={onOpenExportModal}
          disabled={isExporting}
          data-testid="btn-export"
        >
          <Download size={13} />
          {isExporting ? "Rendering…" : "Export"}
        </button>
      </div>
    </header>
  );
}
