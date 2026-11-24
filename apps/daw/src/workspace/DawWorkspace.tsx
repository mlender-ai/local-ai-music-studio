import React, { useEffect, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Sliders } from "lucide-react";
import { ProjectBrowser } from "../browser/ProjectBrowser";
import { loadWorkspacePrefs, saveWorkspacePrefs, useDaw } from "../commands/store";
import { MixerPanel } from "../mixer/MixerPanel";
import { PianoRoll } from "../piano-roll/PianoRoll";
import { AIProducerPanel } from "../producer/AIProducerPanel";
import { ArrangementTimeline } from "../timeline/ArrangementTimeline";
import { ClipEditor } from "../timeline/ClipEditor";
import { TransportBar } from "../transport/TransportBar";
import type { Clip } from "../project/types";

type DockTab = "clip" | "piano" | "mixer" | "fx";

function isTypingElement(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
}

export function DawWorkspace() {
  const {
    project,
    selectedClip,
    selection,
    setSelection,
    playheadBeats,
    gridBeats,
    isExporting,
    toast,
    dispatch,
    undo,
    redo,
    playPause,
    seek,
    saveCurrentProject,
    createNewProject,
    saveAsProject,
    exportStereoWav,
    revisionConflict,
    resolveConflictReload,
    resolveConflictOverwrite,
    dismissConflict,
  } = useDaw();

  const savedPrefs = loadWorkspacePrefs();
  const [browserOpen, setBrowserOpen] = useState(savedPrefs.browserOpen ?? true);
  const [browserWidth, setBrowserWidth] = useState(216);
  const [producerOpen, setProducerOpen] = useState(savedPrefs.producerOpen ?? true);
  const [producerWidth, setProducerWidth] = useState(258);
  const [dockOpen, setDockOpen] = useState(savedPrefs.dockOpen ?? true);
  const [dockHeight, setDockHeight] = useState(224);
  const [dockTab, setDockTab] = useState<DockTab>("clip");

  useEffect(() => {
    saveWorkspacePrefs({ browserOpen, producerOpen, dockOpen });
  }, [browserOpen, producerOpen, dockOpen]);

  // Modals
  const [newModalOpen, setNewModalOpen] = useState(false);
  const [newName, setNewName] = useState("Untitled Session");
  const [newBpm, setNewBpm] = useState("128");
  const [saveAsOpen, setSaveAsOpen] = useState(false);
  const [saveAsName, setSaveAsName] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const [exportLoopOnly, setExportLoopOnly] = useState(false);

  // Global DAW Keyboard Shortcuts (strictly disabled while typing in inputs!)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isTypingElement(e.target)) return;
      const mod = e.metaKey || e.ctrlKey;

      if (e.code === "Space") {
        e.preventDefault();
        void playPause();
      } else if (mod && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void saveCurrentProject();
      } else if (mod && e.shiftKey && e.key.toLowerCase() === "z") {
        e.preventDefault();
        redo();
      } else if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        undo();
      } else if (mod && e.key.toLowerCase() === "d") {
        e.preventDefault();
        if (selectedClip) {
          dispatch({ type: "clip.duplicate", payload: { clipId: selectedClip.id } });
        }
      } else if (mod && e.key.toLowerCase() === "e") {
        e.preventDefault();
        if (selectedClip) {
          dispatch({
            type: "clip.split",
            payload: { clipId: selectedClip.id, splitBeat: playheadBeats },
          });
        }
      } else if (e.key === "Delete" || e.key === "Backspace") {
        if (selection.selectedClipIds.length > 0) {
          e.preventDefault();
          for (const cid of selection.selectedClipIds) {
            dispatch({ type: "clip.delete", payload: { clipId: cid } });
          }
          setSelection((prev) => ({ ...prev, selectedClipIds: [] }));
        }
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        if (selectedClip && e.altKey) {
          dispatch({
            type: "clip.move",
            payload: {
              clipId: selectedClip.id,
              timelineStartBeats: Math.max(0, selectedClip.timelineStartBeats - gridBeats),
            },
          });
        } else {
          seek(Math.max(0, playheadBeats - gridBeats));
        }
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        if (selectedClip && e.altKey) {
          dispatch({
            type: "clip.move",
            payload: {
              clipId: selectedClip.id,
              timelineStartBeats: selectedClip.timelineStartBeats + gridBeats,
            },
          });
        } else {
          seek(playheadBeats + gridBeats);
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    playPause,
    saveCurrentProject,
    undo,
    redo,
    selectedClip,
    selection.selectedClipIds,
    setSelection,
    playheadBeats,
    gridBeats,
    dispatch,
    seek,
  ]);

  const startResize = (
    axis: "left" | "right" | "bottom",
    e: React.PointerEvent<HTMLDivElement>
  ) => {
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const initVal = axis === "left" ? browserWidth : axis === "right" ? producerWidth : dockHeight;

    const onMove = (ev: PointerEvent) => {
      if (axis === "left") {
        setBrowserWidth(Math.max(170, Math.min(340, initVal + (ev.clientX - startX))));
      } else if (axis === "right") {
        setProducerWidth(Math.max(210, Math.min(380, initVal - (ev.clientX - startX))));
      } else {
        setDockHeight(Math.max(150, Math.min(420, initVal - (ev.clientY - startY))));
      }
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const handleOpenClipInEditor = (clip: Clip) => {
    setDockOpen(true);
    setDockTab(clip.type === "midi" ? "piano" : "clip");
  };

  return (
    <div className="daw-shell">
      <TransportBar
        onOpenNewModal={() => {
          setNewName(`Session ${new Date().toISOString().slice(5, 10)}`);
          setNewBpm("128");
          setNewModalOpen(true);
        }}
        onOpenSaveAsModal={() => {
          setSaveAsName(`${project?.name ?? "Project"} Copy`);
          setSaveAsOpen(true);
        }}
        onOpenExportModal={() => {
          setExportLoopOnly(Boolean(project?.loopRegion.enabled));
          setExportOpen(true);
        }}
      />

      <div className="workspace-body">
        {/* Left Browser Panel */}
        {browserOpen ? (
          <>
            <ProjectBrowser
              width={browserWidth}
              onCollapse={() => setBrowserOpen(false)}
              onOpenNewModal={() => setNewModalOpen(true)}
            />
            <div
              className="resize-handle-v"
              onPointerDown={(e) => startResize("left", e)}
              title="Drag to resize Browser"
            />
          </>
        ) : (
          <div
            style={{
              width: 24,
              background: "var(--bg-panel)",
              borderRight: "1px solid var(--border-default)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              paddingTop: 6,
            }}
          >
            <button className="icon-btn" title="Expand Browser" onClick={() => setBrowserOpen(true)}>
              <ChevronRight size={14} />
            </button>
          </div>
        )}

        {/* Center Column: Arrangement Timeline + Resizable Bottom Dock */}
        <main className="center-column">
          <ArrangementTimeline onOpenClipInEditor={handleOpenClipInEditor} />

          {dockOpen ? (
            <>
              <div
                className="resize-handle-h"
                onPointerDown={(e) => startResize("bottom", e)}
                title="Drag to resize Editor Dock"
              />
              <section className="bottom-dock" style={{ height: dockHeight }} data-testid="bottom-dock">
                <div className="dock-tabs">
                  <div className="dock-tab-list">
                    <button
                      className={`dock-tab ${dockTab === "clip" ? "active" : ""}`}
                      onClick={() => setDockTab("clip")}
                      data-testid="tab-clip-editor"
                    >
                      Clip Editor
                    </button>
                    <button
                      className={`dock-tab ${dockTab === "piano" ? "active" : ""}`}
                      onClick={() => setDockTab("piano")}
                      data-testid="tab-piano-roll"
                    >
                      Piano Roll
                    </button>
                    <button
                      className={`dock-tab ${dockTab === "mixer" ? "active" : ""}`}
                      onClick={() => setDockTab("mixer")}
                      data-testid="tab-mixer"
                    >
                      Mixer
                    </button>
                    <button
                      className={`dock-tab ${dockTab === "fx" ? "active" : ""}`}
                      onClick={() => setDockTab("fx")}
                      style={{ color: dockTab === "fx" ? "var(--text-primary)" : "var(--text-muted)" }}
                    >
                      FX Rack
                    </button>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                      {dockTab === "piano"
                        ? (selectedClip?.type === "midi"
                            ? selectedClip.name
                            : project?.tracks.flatMap((t) => t.clips).find((c) => c.type === "midi")?.name ?? "")
                        : dockTab === "mixer"
                          ? `${project?.tracks.length ?? 0} Tracks + Master`
                          : selectedClip?.name ?? ""}
                    </span>
                    <button
                      className="icon-btn"
                      title="Collapse Editor Dock"
                      onClick={() => setDockOpen(false)}
                    >
                      <ChevronDown size={14} />
                    </button>
                  </div>
                </div>

                <div className="dock-content">
                  {dockTab === "clip" && <ClipEditor />}
                  {dockTab === "piano" && <PianoRoll />}
                  {dockTab === "mixer" && <MixerPanel />}
                  {dockTab === "fx" && (
                    <div
                      style={{
                        flex: 1,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 6,
                        color: "var(--text-muted)",
                      }}
                    >
                      <Sliders size={18} />
                      <div style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
                        FX Rack — Scheduled for Phase 05 (Sound Design)
                      </div>
                      <div style={{ fontSize: 11 }}>
                        EQ, Compressor, Delay, Reverb, Distortion, Automation, and AU/VST3 plugin hosting are not active in Phase 01.
                      </div>
                    </div>
                  )}
                </div>
              </section>
            </>
          ) : (
            <div
              style={{
                height: 28,
                background: "var(--bg-panel)",
                borderTop: "1px solid var(--border-default)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0 10px",
              }}
            >
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Editor Dock collapsed (Clip Editor / Piano Roll / Mixer)
              </span>
              <button className="icon-btn" title="Expand Editor Dock" onClick={() => setDockOpen(true)}>
                <ChevronUp size={14} />
              </button>
            </div>
          )}
        </main>

        {/* Right AI Producer Panel */}
        {producerOpen ? (
          <>
            <div
              className="resize-handle-v"
              onPointerDown={(e) => startResize("right", e)}
              title="Drag to resize AI Producer Panel"
            />
            <AIProducerPanel width={producerWidth} onCollapse={() => setProducerOpen(false)} />
          </>
        ) : (
          <div
            style={{
              width: 24,
              background: "var(--bg-panel)",
              borderLeft: "1px solid var(--border-default)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              paddingTop: 6,
            }}
          >
            <button
              className="icon-btn"
              title="Expand AI Producer Panel"
              onClick={() => setProducerOpen(true)}
            >
              <ChevronLeft size={14} />
            </button>
          </div>
        )}
      </div>

      {/* New Project Modal */}
      {newModalOpen && (
        <div className="modal-backdrop" onClick={() => setNewModalOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>New Project</div>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Project Name</span>
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                style={{ padding: "6px 8px" }}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Tempo (BPM)</span>
              <input
                type="number"
                min={30}
                max={300}
                value={newBpm}
                onChange={(e) => setNewBpm(e.target.value)}
                style={{ padding: "6px 8px" }}
              />
            </label>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
              <button onClick={() => setNewModalOpen(false)}>Cancel</button>
              <button
                className="btn-primary"
                onClick={async () => {
                  await createNewProject(newName.trim() || "Untitled 01", parseFloat(newBpm) || 128);
                  setNewModalOpen(false);
                }}
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Save As Modal */}
      {saveAsOpen && (
        <div className="modal-backdrop" onClick={() => setSaveAsOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Save Project Copy As</div>
            <input
              autoFocus
              value={saveAsName}
              onChange={(e) => setSaveAsName(e.target.value)}
              style={{ padding: "6px 8px" }}
            />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button onClick={() => setSaveAsOpen(false)}>Cancel</button>
              <button
                className="btn-primary"
                onClick={async () => {
                  await saveAsProject(saveAsName.trim() || "Project Copy");
                  setSaveAsOpen(false);
                }}
              >
                Save Copy
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Stereo WAV Export Modal */}
      {exportOpen && project && (
        <div className="modal-backdrop" onClick={() => setExportOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Export Stereo WAV</div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5 }}>
              Renders the edited timeline offline (48 kHz · 24-bit Stereo PCM) reflecting all clip positions, trims,
              loops, track gain/pan, mute/solo states, MIDI synth playback, and master volume. Saves to local{" "}
              <code className="mono">exports/</code> and downloads immediately.
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
              <input
                type="checkbox"
                checked={exportLoopOnly}
                disabled={!project.loopRegion.enabled}
                onChange={(e) => setExportLoopOnly(e.target.checked)}
              />
              <span>
                Export Loop Region only{" "}
                {project.loopRegion.enabled
                  ? `(Beats ${project.loopRegion.startBeats}–${project.loopRegion.endBeats})`
                  : "(Enable Loop to use)"}
              </span>
            </label>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
              <button onClick={() => setExportOpen(false)}>Cancel</button>
              <button
                className="btn-primary"
                disabled={isExporting}
                onClick={async () => {
                  setExportOpen(false);
                  await exportStereoWav(exportLoopOnly);
                }}
                data-testid="btn-confirm-export"
              >
                {isExporting ? "Rendering…" : "Render & Download WAV"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Revision Conflict Banner */}
      {revisionConflict && (
        <div className="modal-backdrop" onClick={dismissConflict}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()} data-testid="conflict-modal">
            <div style={{ fontWeight: 600, fontSize: 14, color: "var(--accent-playhead)" }}>
              Project Revision Conflict
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>
              The backend project was updated (server rev {revisionConflict.serverRevision}, local base rev{" "}
              {revisionConflict.expectedRevision}). Choose whether to load the latest server revision or overwrite with
              your local edits.
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
              <button onClick={dismissConflict}>Cancel</button>
              <button onClick={() => void resolveConflictOverwrite()}>Overwrite Server</button>
              <button className="btn-primary" onClick={() => void resolveConflictReload()}>
                Load Latest (rev {revisionConflict.serverRevision})
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Status / Error Toast */}
      {toast && (
        <div className={`status-banner ${toast.kind === "error" ? "error" : ""}`} role="status">
          {toast.message}
        </div>
      )}
    </div>
  );
}
