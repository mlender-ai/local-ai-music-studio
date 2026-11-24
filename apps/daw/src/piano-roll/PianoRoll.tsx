import React, { useEffect, useMemo, useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { audioEngine } from "../audio/audioEngine";
import { makeClientId } from "../commands/executor";
import { useDaw } from "../commands/store";
import { isBlackKey, midiPitchToName, snapBeats } from "../project/time";
import type { MidiNote } from "../project/types";

const MIN_PITCH = 48; // C3
const MAX_PITCH = 84; // C6
const KEY_WIDTH = 48;
const ROW_H = 14;
const PX_PER_BEAT = 56;

type NoteDrag =
  | {
      mode: "move";
      noteId: string;
      startX: number;
      startY: number;
      initStartBeat: number;
      initPitch: number;
    }
  | {
      mode: "resize";
      noteId: string;
      startX: number;
      initDurationBeats: number;
    };

export function PianoRoll() {
  const { project, selectedClip, playheadBeats, dispatch, beginTransaction, commitTransaction } = useDaw();
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [noteGridBeats, setNoteGridBeats] = useState(0.25); // 1/16 note default
  const [drag, setDrag] = useState<NoteDrag | null>(null);
  const lastAuditionedPitchRef = useRef<number | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  // Pick selected MIDI clip, or fall back to first MIDI clip in project
  const midiClip = useMemo(() => {
    if (selectedClip?.type === "midi") return selectedClip;
    if (!project) return null;
    for (const t of project.tracks) {
      const c = t.clips.find((cl) => cl.type === "midi");
      if (c) return c;
    }
    return null;
  }, [project, selectedClip]);

  // Auto-center scroll vertically around the clip's notes whenever opened or clip changes
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el || !midiClip) return;
    const avgPitch =
      midiClip.notes.length > 0
        ? midiClip.notes.reduce((sum, n) => sum + n.pitch, 0) / midiClip.notes.length
        : 66;
    const targetRow = MAX_PITCH - avgPitch;
    el.scrollTop = Math.max(0, targetRow * ROW_H - el.clientHeight / 2);
  }, [midiClip?.id]);

  const pitches = useMemo(() => {
    const arr: number[] = [];
    for (let p = MAX_PITCH; p >= MIN_PITCH; p--) arr.push(p);
    return arr;
  }, []);

  useEffect(() => {
    if (!drag || !midiClip) return;

    const onMove = (e: PointerEvent) => {
      const dx = e.clientX - drag.startX;
      if (drag.mode === "move") {
        const dy = e.clientY - drag.startY;
        const nextBeat = snapBeats(Math.max(0, drag.initStartBeat + dx / PX_PER_BEAT), noteGridBeats, true);
        const nextPitch = Math.max(
          MIN_PITCH,
          Math.min(MAX_PITCH, drag.initPitch - Math.round(dy / ROW_H))
        );
        if (lastAuditionedPitchRef.current !== nextPitch) {
          lastAuditionedPitchRef.current = nextPitch;
          audioEngine.auditionMidiNote(nextPitch, 96, 0.16);
        }
        dispatch(
          {
            type: "midi.moveNote",
            payload: { clipId: midiClip.id, noteId: drag.noteId, pitch: nextPitch, startBeat: nextBeat },
          },
          { recordHistory: false }
        );
      } else if (drag.mode === "resize") {
        const nextDur = Math.max(
          noteGridBeats,
          snapBeats(drag.initDurationBeats + dx / PX_PER_BEAT, noteGridBeats, true)
        );
        dispatch(
          {
            type: "midi.resizeNote",
            payload: { clipId: midiClip.id, noteId: drag.noteId, durationBeats: nextDur },
          },
          { recordHistory: false }
        );
      }
    };

    const onUp = () => {
      lastAuditionedPitchRef.current = null;
      commitTransaction();
      setDrag(null);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [drag, midiClip, noteGridBeats, dispatch, commitTransaction]);

  if (!project) return null;

  if (!midiClip) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
          fontSize: 12,
        }}
      >
        No MIDI clip selected. Add a MIDI track (+MIDI) and double-click its lane, or import a .mid file.
      </div>
    );
  }

  const totalBeats = Math.max(4, Math.ceil(midiClip.durationBeats));
  const gridWidth = Math.max(640, totalBeats * PX_PER_BEAT);
  const gridHeight = pitches.length * ROW_H;
  const selectedNote = midiClip.notes.find((n) => n.id === selectedNoteId) ?? null;

  const handleGridClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const startBeat = snapBeats(Math.max(0, x / PX_PER_BEAT), noteGridBeats, true);
    const rowIdx = Math.max(0, Math.min(pitches.length - 1, Math.floor(y / ROW_H)));
    const pitch = pitches[rowIdx];

    const note: MidiNote = {
      id: makeClientId("note"),
      pitch,
      velocity: 100,
      startBeat,
      durationBeats: Math.max(0.5, noteGridBeats * 2),
    };
    dispatch({ type: "midi.addNote", payload: { clipId: midiClip.id, note } });
    setSelectedNoteId(note.id);
    audioEngine.auditionMidiNote(pitch, 100, 0.24);
  };

  const relPlayheadBeats = playheadBeats - midiClip.timelineStartBeats;
  const showPlayhead = relPlayheadBeats >= 0 && relPlayheadBeats <= midiClip.durationBeats;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }} data-testid="piano-roll">
      {/* Piano Roll Sub-Toolbar */}
      <div
        style={{
          height: 28,
          minHeight: 28,
          padding: "0 10px",
          background: "#16181c",
          borderBottom: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontSize: 11,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <strong style={{ color: "var(--text-primary)" }}>{midiClip.name}</strong>
          <span style={{ color: "var(--text-muted)" }} className="mono">
            {midiClip.notes.length} notes · Basic Poly Synth (Phase 01 preview)
          </span>
          <label style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--text-secondary)" }}>
            Snap
            <select
              value={noteGridBeats}
              onChange={(e) => setNoteGridBeats(parseFloat(e.target.value))}
              style={{ height: 20, fontSize: 10 }}
            >
              <option value={1}>1/4</option>
              <option value={0.5}>1/8</option>
              <option value={0.25}>1/16</option>
            </select>
          </label>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {selectedNote && (
            <>
              <span className="mono" style={{ color: "var(--text-secondary)", fontSize: 10 }}>
                {midiPitchToName(selectedNote.pitch)} · Vel {selectedNote.velocity}
              </span>
              <button
                style={{ height: 20, padding: "0 6px", fontSize: 10 }}
                onClick={() => {
                  dispatch({
                    type: "midi.deleteNote",
                    payload: { clipId: midiClip.id, noteId: selectedNote.id },
                  });
                  setSelectedNoteId(null);
                }}
              >
                <Trash2 size={10} />
                Delete Note
              </button>
            </>
          )}
          <span style={{ color: "var(--text-muted)", fontSize: 10 }}>
            Click grid to add · Drag edge to resize · Right-click note to delete
          </span>
        </div>
      </div>

      {/* Scrollable Keyboard + Pitch Grid */}
      <div
        ref={scrollContainerRef}
        style={{ flex: 1, overflow: "auto", display: "flex", minHeight: 0, position: "relative" }}
      >
        {/* Left Sticky Piano Keys */}
        <div
          style={{
            width: KEY_WIDTH,
            minWidth: KEY_WIDTH,
            height: gridHeight,
            position: "sticky",
            left: 0,
            zIndex: 6,
            background: "#16181c",
            borderRight: "1px solid var(--border-default)",
          }}
        >
          {pitches.map((pitch) => {
            const black = isBlackKey(pitch);
            const isC = pitch % 12 === 0;
            return (
              <div
                key={pitch}
                onMouseDown={() => audioEngine.auditionMidiNote(pitch, 100, 0.25)}
                title={`Audition ${midiPitchToName(pitch)}`}
                style={{
                  height: ROW_H,
                  borderBottom: "1px solid #22262e",
                  background: black ? "#181a1f" : "#2a2f38",
                  color: isC ? "var(--text-primary)" : "var(--text-muted)",
                  fontSize: 9,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "flex-end",
                  paddingRight: 4,
                  cursor: "pointer",
                }}
                className="mono"
              >
                {isC || pitch % 12 === 5 ? midiPitchToName(pitch) : ""}
              </div>
            );
          })}
        </div>

        {/* Note Grid */}
        <div
          style={{
            width: gridWidth,
            height: gridHeight,
            position: "relative",
            background: "#131519",
            cursor: "crosshair",
          }}
          onClick={handleGridClick}
          data-testid="piano-roll-grid"
        >
          {/* Horizontal Pitch Lanes */}
          {pitches.map((pitch, idx) => (
            <div
              key={pitch}
              style={{
                position: "absolute",
                top: idx * ROW_H,
                left: 0,
                right: 0,
                height: ROW_H,
                background: isBlackKey(pitch) ? "rgba(0,0,0,0.22)" : "transparent",
                borderBottom: pitch % 12 === 0 ? "1px solid #2c313c" : "1px solid #1b1e25",
                pointerEvents: "none",
              }}
            />
          ))}

          {/* Vertical Beat & Bar Lines */}
          {Array.from({ length: totalBeats * 4 }, (_, q) => {
            const beat = q / 4;
            const isBar = q % 16 === 0;
            const isBeat = q % 4 === 0;
            return (
              <div
                key={q}
                style={{
                  position: "absolute",
                  left: beat * PX_PER_BEAT,
                  top: 0,
                  bottom: 0,
                  borderLeft: isBar
                    ? "1px solid var(--grid-bar)"
                    : isBeat
                      ? "1px solid var(--grid-beat)"
                      : "1px solid #191c22",
                  pointerEvents: "none",
                }}
              />
            );
          })}

          {/* MIDI Notes */}
          {midiClip.notes.map((note) => {
            if (note.pitch < MIN_PITCH || note.pitch > MAX_PITCH) return null;
            const rowIdx = MAX_PITCH - note.pitch;
            const isSel = selectedNoteId === note.id;
            const alpha = 0.45 + (note.velocity / 127) * 0.55;

            return (
              <div
                key={note.id}
                data-testid={`midi-note-${note.id}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedNoteId(note.id);
                }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  dispatch({
                    type: "midi.deleteNote",
                    payload: { clipId: midiClip.id, noteId: note.id },
                  });
                  if (selectedNoteId === note.id) setSelectedNoteId(null);
                }}
                onPointerDown={(e) => {
                  if (e.button !== 0) return;
                  e.stopPropagation();
                  setSelectedNoteId(note.id);
                  beginTransaction();
                  audioEngine.auditionMidiNote(note.pitch, note.velocity, 0.18);
                  setDrag({
                    mode: "move",
                    noteId: note.id,
                    startX: e.clientX,
                    startY: e.clientY,
                    initStartBeat: note.startBeat,
                    initPitch: note.pitch,
                  });
                }}
                style={{
                  position: "absolute",
                  left: note.startBeat * PX_PER_BEAT,
                  top: rowIdx * ROW_H + 1,
                  width: Math.max(8, note.durationBeats * PX_PER_BEAT - 1),
                  height: ROW_H - 2,
                  background: `rgba(100, 142, 168, ${alpha})`,
                  border: isSel ? "1.5px solid var(--accent-playhead)" : "1px solid #8eb8d1",
                  borderRadius: 2,
                  cursor: "grab",
                  zIndex: isSel ? 4 : 2,
                  display: "flex",
                  alignItems: "center",
                  paddingLeft: 3,
                  fontSize: 8,
                  color: "#0f1318",
                  fontWeight: 700,
                  overflow: "hidden",
                }}
              >
                {note.durationBeats >= 0.5 ? midiPitchToName(note.pitch) : ""}
                {/* Right Resize Handle */}
                <div
                  style={{
                    position: "absolute",
                    right: 0,
                    top: 0,
                    bottom: 0,
                    width: 6,
                    cursor: "ew-resize",
                  }}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    setSelectedNoteId(note.id);
                    beginTransaction();
                    setDrag({
                      mode: "resize",
                      noteId: note.id,
                      startX: e.clientX,
                      initDurationBeats: note.durationBeats,
                    });
                  }}
                />
              </div>
            );
          })}

          {showPlayhead && (
            <div
              style={{
                position: "absolute",
                left: relPlayheadBeats * PX_PER_BEAT,
                top: 0,
                bottom: 0,
                width: 1.5,
                background: "var(--accent-playhead)",
                pointerEvents: "none",
                zIndex: 5,
              }}
            />
          )}
        </div>
      </div>

      {/* Bottom Velocity Lane */}
      <div
        style={{
          height: 44,
          minHeight: 44,
          borderTop: "1px solid var(--border-default)",
          background: "#15171b",
          display: "flex",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: KEY_WIDTH,
            minWidth: KEY_WIDTH,
            borderRight: "1px solid var(--border-default)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 9,
            color: "var(--text-muted)",
            textTransform: "uppercase",
          }}
        >
          Vel
        </div>
        <div style={{ flex: 1, position: "relative", overflowX: "auto" }}>
          <div style={{ width: gridWidth, height: "100%", position: "relative" }}>
            {midiClip.notes.map((note) => {
              const pct = Math.round((note.velocity / 127) * 100);
              const isSel = selectedNoteId === note.id;
              return (
                <div
                  key={note.id}
                  title={`${midiPitchToName(note.pitch)} · Velocity ${note.velocity} (Click/drag vertically)`}
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    setSelectedNoteId(note.id);
                    const lane = e.currentTarget.parentElement;
                    if (!lane) return;
                    const rect = lane.getBoundingClientRect();
                    const updateVel = (clientY: number) => {
                      const ratio = 1 - Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
                      const vel = Math.max(1, Math.min(127, Math.round(ratio * 127)));
                      dispatch(
                        { type: "midi.setVelocity", payload: { clipId: midiClip.id, noteId: note.id, velocity: vel } },
                        { recordHistory: false }
                      );
                    };
                    beginTransaction();
                    updateVel(e.clientY);
                    const onMove = (ev: MouseEvent) => updateVel(ev.clientY);
                    const onUp = () => {
                      commitTransaction();
                      window.removeEventListener("mousemove", onMove);
                      window.removeEventListener("mouseup", onUp);
                    };
                    window.addEventListener("mousemove", onMove);
                    window.addEventListener("mouseup", onUp);
                  }}
                  style={{
                    position: "absolute",
                    left: note.startBeat * PX_PER_BEAT,
                    bottom: 0,
                    width: 8,
                    height: "100%",
                    cursor: "ns-resize",
                    display: "flex",
                    alignItems: "flex-end",
                  }}
                >
                  <div
                    style={{
                      width: 5,
                      height: `${pct}%`,
                      background: isSel ? "var(--accent-playhead)" : "#648ea8",
                      borderRadius: "2px 2px 0 0",
                    }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
