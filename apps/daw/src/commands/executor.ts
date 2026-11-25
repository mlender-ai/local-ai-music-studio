import type { ChordEvent, Clip, MidiNote, Project, Track } from "../project/types";
import type { ProjectCommand } from "./types";

export const TRACK_PALETTE = [
  "#6a997c",
  "#867ca8",
  "#b89458",
  "#648ea8",
  "#9e7389",
  "#6a9999",
  "#9c8568",
];

let idCounter = 1;
export function makeClientId(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 8);
  return `${prefix}_${Date.now().toString(36)}_${(idCounter++).toString(36)}_${rand}`;
}

function cloneProject(project: Project): Project {
  return JSON.parse(JSON.stringify(project)) as Project;
}

function findTrack(project: Project, trackId: string): Track {
  const found = project.tracks.find((t) => t.id === trackId);
  if (!found) throw new Error(`Track not found: ${trackId}`);
  return found;
}

function findClip(project: Project, clipId: string): { track: Track; clip: Clip } {
  for (const track of project.tracks) {
    const clip = track.clips.find((c) => c.id === clipId);
    if (clip) return { track, clip };
  }
  throw new Error(`Clip not found: ${clipId}`);
}

export function executeCommand(project: Project, cmd: ProjectCommand): Project {
  const p = cloneProject(project);

  switch (cmd.type) {
    case "project.rename": {
      const trimmed = cmd.payload.name.trim();
      if (!trimmed) throw new Error("Project name cannot be empty");
      p.name = trimmed;
      break;
    }

    case "project.setTempo": {
      const bpm = Math.max(30, Math.min(300, Number(cmd.payload.bpm)));
      if (!Number.isFinite(bpm)) throw new Error("Invalid BPM");
      p.bpm = Math.round(bpm * 1000) / 1000;
      break;
    }

    case "project.setTimeSignature": {
      p.timeSignature = {
        numerator: Math.max(1, Math.min(16, Math.round(cmd.payload.numerator))),
        denominator: cmd.payload.denominator,
      };
      break;
    }

    case "project.setLength": {
      p.lengthBeats = Math.max(4, Math.min(4096, cmd.payload.lengthBeats));
      break;
    }

    case "project.setMasterGain": {
      p.masterGainDb = Math.max(-60, Math.min(6, cmd.payload.gainDb));
      break;
    }

    case "transport.setLoop": {
      const enabled = cmd.payload.enabled ?? p.loopRegion.enabled;
      const startBeats = Math.max(0, cmd.payload.startBeats ?? p.loopRegion.startBeats);
      const endBeats = Math.max(startBeats + 1, cmd.payload.endBeats ?? p.loopRegion.endBeats);
      p.loopRegion = { enabled, startBeats, endBeats };
      break;
    }

    case "asset.register": {
      if (!p.assets.some((a) => a.id === cmd.payload.asset.id)) {
        p.assets.push(cmd.payload.asset);
      }
      break;
    }

    case "track.add": {
      const color = cmd.payload.color ?? TRACK_PALETTE[p.tracks.length % TRACK_PALETTE.length];
      p.tracks.push({
        id: cmd.payload.id ?? makeClientId("trk"),
        name: cmd.payload.name?.trim() || `Track ${p.tracks.length + 1}`,
        type: cmd.payload.type,
        color,
        gainDb: 0,
        pan: 0,
        mute: false,
        solo: false,
        stemLabel: cmd.payload.stemLabel ?? null,
        instrumentRef: cmd.payload.instrumentRef ?? (cmd.payload.type === "midi" ? "basic-poly-synth" : null),
        effects: [],
        clips: [],
      });
      break;
    }

    case "track.remove": {
      // Never delete underlying assets!
      p.tracks = p.tracks.filter((t) => t.id !== cmd.payload.trackId);
      break;
    }

    case "track.rename": {
      const trk = findTrack(p, cmd.payload.trackId);
      const trimmed = cmd.payload.name.trim();
      if (!trimmed) throw new Error("Track name cannot be empty");
      trk.name = trimmed;
      break;
    }

    case "track.reorder": {
      const { fromIndex, toIndex } = cmd.payload;
      if (fromIndex < 0 || fromIndex >= p.tracks.length || toIndex < 0 || toIndex >= p.tracks.length) {
        throw new Error("Invalid track reorder indices");
      }
      const [moved] = p.tracks.splice(fromIndex, 1);
      p.tracks.splice(toIndex, 0, moved);
      break;
    }

    case "track.setColor": {
      findTrack(p, cmd.payload.trackId).color = cmd.payload.color;
      break;
    }

    case "track.setGain": {
      findTrack(p, cmd.payload.trackId).gainDb = Math.max(-60, Math.min(6, cmd.payload.gainDb));
      break;
    }

    case "track.setPan": {
      findTrack(p, cmd.payload.trackId).pan = Math.max(-1, Math.min(1, cmd.payload.pan));
      break;
    }

    case "track.setMute": {
      findTrack(p, cmd.payload.trackId).mute = cmd.payload.mute;
      break;
    }

    case "track.setSolo": {
      findTrack(p, cmd.payload.trackId).solo = cmd.payload.solo;
      break;
    }

    case "track.setInstrument": {
      const trk = findTrack(p, cmd.payload.trackId);
      trk.instrumentRef = cmd.payload.instrumentRef;
      if (cmd.payload.preset !== undefined || cmd.payload.parameters !== undefined) {
        const prevCfg = (trk.instrumentConfig ?? {}) as Record<string, unknown>;
        const prevParams = (prevCfg.parameters ?? {}) as Record<string, unknown>;
        trk.instrumentConfig = {
          ...prevCfg,
          ...(cmd.payload.preset !== undefined ? { preset: cmd.payload.preset } : {}),
          ...(cmd.payload.parameters ? { parameters: { ...prevParams, ...cmd.payload.parameters } } : {}),
        };
      }
      trk.freezeState = null;
      break;
    }

    case "instrument.setPreset": {
      const trk = findTrack(p, cmd.payload.trackId);
      const prevCfg = (trk.instrumentConfig ?? {}) as Record<string, unknown>;
      const prevParams = (prevCfg.parameters ?? {}) as Record<string, unknown>;
      trk.instrumentConfig = {
        ...prevCfg,
        preset: cmd.payload.preset,
        ...(cmd.payload.parameters ? { parameters: { ...prevParams, ...cmd.payload.parameters } } : {}),
      };
      trk.freezeState = null;
      break;
    }

    case "instrument.setParams": {
      const trk = findTrack(p, cmd.payload.trackId);
      const prevCfg = (trk.instrumentConfig ?? {}) as Record<string, unknown>;
      const prevParams = (prevCfg.parameters ?? {}) as Record<string, unknown>;
      trk.instrumentConfig = {
        ...prevCfg,
        parameters: { ...prevParams, ...cmd.payload.parameters },
        ...(cmd.payload.articulation !== undefined ? { articulation: cmd.payload.articulation } : {}),
        ...(cmd.payload.samplerConfig ? { samplerConfig: { ...(prevCfg.samplerConfig as Record<string, unknown> | undefined), ...cmd.payload.samplerConfig } } : {}),
        ...(cmd.payload.drumRackConfig ? { drumRackConfig: { ...(prevCfg.drumRackConfig as Record<string, unknown> | undefined), ...cmd.payload.drumRackConfig } } : {}),
      };
      trk.freezeState = null;
      break;
    }

    case "fx.add":
    case "fx.remove":
    case "fx.move":
    case "fx.setParams":
    case "fx.setBypass": {
      const target = cmd.payload.target ?? (cmd.payload.busId ? "bus" : "track");
      let fxList: Track["effects"];
      let ownerTrack: Track | null = null;
      if (target === "master") {
        p.masterEffects = p.masterEffects ?? [];
        fxList = p.masterEffects;
      } else if (target === "bus" && cmd.payload.busId) {
        const bus = (p.buses ?? []).find((b) => b.id === cmd.payload.busId);
        if (!bus) throw new Error(`Bus not found: ${cmd.payload.busId}`);
        bus.effects = bus.effects ?? [];
        fxList = bus.effects;
      } else {
        ownerTrack = findTrack(p, cmd.payload.trackId ?? "");
        ownerTrack.effects = ownerTrack.effects ?? [];
        fxList = ownerTrack.effects;
      }

      if (cmd.type === "fx.add") {
        const slot = { ...cmd.payload.slot, id: cmd.payload.slot.id || makeClientId("fx") };
        if (typeof cmd.payload.index === "number" && cmd.payload.index >= 0 && cmd.payload.index <= fxList.length) {
          fxList.splice(cmd.payload.index, 0, slot);
        } else {
          fxList.push(slot);
        }
      } else if (cmd.type === "fx.remove") {
        const idx = fxList.findIndex((f) => f.id === cmd.payload.fxId);
        if (idx >= 0) fxList.splice(idx, 1);
      } else if (cmd.type === "fx.move") {
        const { fromIndex, toIndex } = cmd.payload;
        if (fromIndex >= 0 && fromIndex < fxList.length && toIndex >= 0 && toIndex < fxList.length) {
          const [moved] = fxList.splice(fromIndex, 1);
          fxList.splice(toIndex, 0, moved);
        }
      } else if (cmd.type === "fx.setParams") {
        const slot = fxList.find((f) => f.id === cmd.payload.fxId);
        if (slot) {
          if (cmd.payload.parameters) {
            slot.parameters = { ...(slot.parameters ?? {}), ...cmd.payload.parameters };
          }
          if (cmd.payload.preset !== undefined) slot.preset = cmd.payload.preset;
          if (cmd.payload.wetDry !== undefined) {
            slot.wetDry = Math.max(0, Math.min(1, cmd.payload.wetDry));
            slot.parameters = { ...(slot.parameters ?? {}), wetDry: slot.wetDry };
          }
          if (cmd.payload.sidechainTrackId !== undefined) {
            slot.sidechainTrackId = cmd.payload.sidechainTrackId;
          }
        }
      } else if (cmd.type === "fx.setBypass") {
        const slot = fxList.find((f) => f.id === cmd.payload.fxId);
        if (slot) slot.bypass = cmd.payload.bypass;
      }
      if (ownerTrack) ownerTrack.freezeState = null;
      break;
    }

    case "bus.add": {
      p.buses = p.buses ?? [];
      const bid = cmd.payload.id || makeClientId("bus");
      p.buses = [
        ...p.buses.filter((b) => b.id !== bid),
        {
          id: bid,
          name: cmd.payload.name,
          kind: cmd.payload.kind ?? "return",
          gainDb: 0,
          pan: 0,
          mute: false,
          solo: false,
          effects: cmd.payload.effects ?? [],
        },
      ];
      break;
    }

    case "bus.remove": {
      const bid = cmd.payload.busId;
      p.buses = (p.buses ?? []).filter((b) => b.id !== bid);
      for (const trk of p.tracks) {
        trk.sends = (trk.sends ?? []).filter((s) => s.busId !== bid);
        if (trk.outputBusId === bid) trk.outputBusId = "master";
      }
      break;
    }

    case "bus.setGain": {
      const bus = (p.buses ?? []).find((b) => b.id === cmd.payload.busId);
      if (bus) bus.gainDb = Math.max(-60, Math.min(6, cmd.payload.gainDb));
      break;
    }

    case "bus.setMute": {
      const bus = (p.buses ?? []).find((b) => b.id === cmd.payload.busId);
      if (bus) bus.mute = cmd.payload.mute;
      break;
    }

    case "bus.setSolo": {
      const bus = (p.buses ?? []).find((b) => b.id === cmd.payload.busId);
      if (bus) bus.solo = cmd.payload.solo;
      break;
    }

    case "send.set": {
      const trk = findTrack(p, cmd.payload.trackId);
      trk.sends = trk.sends ?? [];
      const ex = trk.sends.find((s) => s.busId === cmd.payload.busId);
      const lvl = Math.max(-60, Math.min(6, cmd.payload.levelDb));
      if (ex) {
        ex.levelDb = lvl;
        if (cmd.payload.preFader !== undefined) ex.preFader = cmd.payload.preFader;
        if (cmd.payload.enabled !== undefined) ex.enabled = cmd.payload.enabled;
      } else {
        trk.sends.push({
          id: makeClientId("snd"),
          busId: cmd.payload.busId,
          levelDb: lvl,
          preFader: cmd.payload.preFader ?? false,
          enabled: cmd.payload.enabled ?? true,
        });
      }
      break;
    }

    case "send.remove": {
      const trk = findTrack(p, cmd.payload.trackId);
      trk.sends = (trk.sends ?? []).filter((s) => s.busId !== cmd.payload.busId);
      break;
    }

    case "automation.upsertLane": {
      const trk = findTrack(p, cmd.payload.trackId);
      const lane = {
        ...cmd.payload.lane,
        id: cmd.payload.lane.id || makeClientId("auto"),
        points: [...(cmd.payload.lane.points ?? [])].sort((a, b) => a.beat - b.beat),
      };
      trk.automationLanes = [...(trk.automationLanes ?? []).filter((l) => l.id !== lane.id), lane];
      trk.freezeState = null;
      break;
    }

    case "automation.removeLane": {
      const trk = findTrack(p, cmd.payload.trackId);
      trk.automationLanes = (trk.automationLanes ?? []).filter((l) => l.id !== cmd.payload.laneId);
      trk.freezeState = null;
      break;
    }

    case "track.addTakeLane": {
      const trk = findTrack(p, cmd.payload.trackId);
      const lane = {
        ...cmd.payload.lane,
        id: cmd.payload.lane.id || makeClientId("lane"),
        createdAt: cmd.payload.lane.createdAt ?? new Date().toISOString(),
      };
      const existing = trk.takeLanes ?? [];
      trk.takeLanes = [...existing.filter((ln) => ln.id !== lane.id), lane];
      break;
    }

    case "track.renameTakeLane": {
      const trk = findTrack(p, cmd.payload.trackId);
      const trimmed = cmd.payload.name.trim();
      if (!trimmed) throw new Error("Take lane name cannot be empty");
      const ln = (trk.takeLanes ?? []).find((item) => item.id === cmd.payload.laneId);
      if (!ln) throw new Error(`Take lane not found: ${cmd.payload.laneId}`);
      ln.name = trimmed;
      break;
    }

    case "track.removeTakeLane": {
      const trk = findTrack(p, cmd.payload.trackId);
      trk.takeLanes = (trk.takeLanes ?? []).filter((item) => item.id !== cmd.payload.laneId);
      break;
    }

    case "clip.setFades": {
      const { clip } = findClip(p, cmd.payload.clipId);
      if (cmd.payload.fadeInBeats !== undefined) {
        clip.fadeInBeats = Math.max(0, Math.min(64, cmd.payload.fadeInBeats));
      }
      if (cmd.payload.fadeOutBeats !== undefined) {
        clip.fadeOutBeats = Math.max(0, Math.min(64, cmd.payload.fadeOutBeats));
      }
      break;
    }

    case "clip.add": {
      const trk = findTrack(p, cmd.payload.trackId);
      trk.clips.push(cmd.payload.clip);
      const clipEnd = cmd.payload.clip.timelineStartBeats + cmd.payload.clip.durationBeats;
      if (clipEnd > p.lengthBeats) {
        p.lengthBeats = Math.ceil(clipEnd / 4) * 4;
      }
      break;
    }

    case "clip.move": {
      const { track: srcTrack, clip } = findClip(p, cmd.payload.clipId);
      clip.timelineStartBeats = Math.max(0, Math.round(cmd.payload.timelineStartBeats * 10000) / 10000);
      if (cmd.payload.targetTrackId && cmd.payload.targetTrackId !== srcTrack.id) {
        const dstTrack = findTrack(p, cmd.payload.targetTrackId);
        if ((dstTrack.type === "midi") !== (clip.type === "midi")) {
          throw new Error("Cannot move MIDI clip onto Audio track or vice versa");
        }
        srcTrack.clips = srcTrack.clips.filter((c) => c.id !== clip.id);
        dstTrack.clips.push(clip);
      }
      const clipEnd = clip.timelineStartBeats + clip.durationBeats;
      if (clipEnd > p.lengthBeats) {
        p.lengthBeats = Math.ceil(clipEnd / 4) * 4;
      }
      break;
    }

    case "clip.trim": {
      const { clip } = findClip(p, cmd.payload.clipId);
      if (cmd.payload.timelineStartBeats !== undefined) {
        clip.timelineStartBeats = Math.max(0, cmd.payload.timelineStartBeats);
      }
      if (cmd.payload.durationBeats !== undefined) {
        clip.durationBeats = Math.max(0.25, cmd.payload.durationBeats);
      }
      if (cmd.payload.sourceOffsetSec !== undefined) {
        clip.sourceOffsetSec = Math.max(0, cmd.payload.sourceOffsetSec);
      }
      break;
    }

    case "clip.split": {
      const { track, clip } = findClip(p, cmd.payload.clipId);
      const relBeat = cmd.payload.splitBeat - clip.timelineStartBeats;
      if (relBeat <= 0.05 || relBeat >= clip.durationBeats - 0.05) {
        throw new Error("Playhead must be strictly inside the selected clip to split");
      }
      const secPerBeat = 60 / p.bpm;
      const leftNotes: MidiNote[] = [];
      const rightNotes: MidiNote[] = [];
      for (const n of clip.notes) {
        const noteEnd = n.startBeat + n.durationBeats;
        if (noteEnd <= relBeat) {
          leftNotes.push(n);
        } else if (n.startBeat >= relBeat) {
          rightNotes.push({
            ...n,
            id: makeClientId("note"),
            startBeat: Math.round((n.startBeat - relBeat) * 100000) / 100000,
          });
        } else {
          leftNotes.push({
            ...n,
            durationBeats: Math.round((relBeat - n.startBeat) * 100000) / 100000,
          });
          rightNotes.push({
            ...n,
            id: makeClientId("note"),
            startBeat: 0,
            durationBeats: Math.round((noteEnd - relBeat) * 100000) / 100000,
          });
        }
      }

      const rightClip: Clip = {
        ...clip,
        id: cmd.payload.rightClipId ?? makeClientId("clp"),
        name: `${clip.name} (2)`,
        timelineStartBeats: Math.round(cmd.payload.splitBeat * 100000) / 100000,
        durationBeats: Math.round((clip.durationBeats - relBeat) * 100000) / 100000,
        sourceOffsetSec:
          clip.type === "audio"
            ? Math.round((clip.sourceOffsetSec + relBeat * secPerBeat) * 100000) / 100000
            : 0,
        notes: rightNotes,
      };
      clip.durationBeats = Math.round(relBeat * 100000) / 100000;
      clip.notes = leftNotes;
      track.clips.push(rightClip);
      break;
    }

    case "clip.duplicate": {
      const { track, clip } = findClip(p, cmd.payload.clipId);
      const dup: Clip = {
        ...clip,
        id: cmd.payload.newClipId ?? makeClientId("clp"),
        name: `${clip.name} copy`,
        timelineStartBeats:
          cmd.payload.timelineStartBeats ??
          Math.round((clip.timelineStartBeats + clip.durationBeats) * 100000) / 100000,
        notes: clip.notes.map((n) => ({ ...n, id: makeClientId("note") })),
      };
      track.clips.push(dup);
      const clipEnd = dup.timelineStartBeats + dup.durationBeats;
      if (clipEnd > p.lengthBeats) {
        p.lengthBeats = Math.ceil(clipEnd / 4) * 4;
      }
      break;
    }

    case "clip.delete": {
      const { track } = findClip(p, cmd.payload.clipId);
      track.clips = track.clips.filter((c) => c.id !== cmd.payload.clipId);
      break;
    }

    case "clip.setGain": {
      const { clip } = findClip(p, cmd.payload.clipId);
      clip.gainDb = Math.max(-24, Math.min(12, cmd.payload.gainDb));
      break;
    }

    case "clip.setLoop": {
      const { clip } = findClip(p, cmd.payload.clipId);
      clip.loop = cmd.payload.loop;
      break;
    }

    case "clip.rename": {
      const { clip } = findClip(p, cmd.payload.clipId);
      const trimmed = cmd.payload.name.trim();
      if (!trimmed) throw new Error("Clip name cannot be empty");
      clip.name = trimmed;
      break;
    }

    case "midi.addNote": {
      const { clip } = findClip(p, cmd.payload.clipId);
      if (clip.type !== "midi") throw new Error("Target clip is not a MIDI clip");
      clip.notes.push(cmd.payload.note);
      break;
    }

    case "midi.moveNote": {
      const { clip } = findClip(p, cmd.payload.clipId);
      const note = clip.notes.find((n) => n.id === cmd.payload.noteId);
      if (!note) throw new Error("MIDI note not found");
      note.pitch = Math.max(0, Math.min(127, Math.round(cmd.payload.pitch)));
      note.startBeat = Math.max(0, cmd.payload.startBeat);
      break;
    }

    case "midi.resizeNote": {
      const { clip } = findClip(p, cmd.payload.clipId);
      const note = clip.notes.find((n) => n.id === cmd.payload.noteId);
      if (!note) throw new Error("MIDI note not found");
      note.durationBeats = Math.max(0.0625, cmd.payload.durationBeats);
      break;
    }

    case "midi.setVelocity": {
      const { clip } = findClip(p, cmd.payload.clipId);
      const note = clip.notes.find((n) => n.id === cmd.payload.noteId);
      if (!note) throw new Error("MIDI note not found");
      note.velocity = Math.max(1, Math.min(127, Math.round(cmd.payload.velocity)));
      break;
    }

    case "midi.deleteNote": {
      const { clip } = findClip(p, cmd.payload.clipId);
      clip.notes = clip.notes.filter((n) => n.id !== cmd.payload.noteId);
      break;
    }

    case "section.add": {
      p.sections.push({
        id: cmd.payload.id ?? makeClientId("sec"),
        name: cmd.payload.name.trim() || "SECTION",
        startBeats: Math.max(0, cmd.payload.startBeats),
        endBeats: Math.max(cmd.payload.startBeats + 1, cmd.payload.endBeats),
        color: cmd.payload.color ?? "#4b5563",
      });
      p.sections.sort((a, b) => a.startBeats - b.startBeats);
      break;
    }

    case "section.rename": {
      const sec = p.sections.find((s) => s.id === cmd.payload.sectionId);
      if (!sec) throw new Error("Section not found");
      sec.name = cmd.payload.name.trim() || sec.name;
      break;
    }

    case "section.remove": {
      p.sections = p.sections.filter((s) => s.id !== cmd.payload.sectionId);
      break;
    }

    case "chord.setTrack": {
      p.chordTrack = cmd.payload.chords
        .map((c) => ({
          ...c,
          id: c.id || makeClientId("chd"),
          startBeat: Math.max(0, Number(c.startBeat)),
          endBeat: Math.max(Math.max(0, Number(c.startBeat)) + 0.25, Number(c.endBeat)),
        }))
        .sort((a, b) => a.startBeat - b.startBeat);
      if (cmd.payload.locked !== undefined) {
        p.chordTrackLocked = cmd.payload.locked;
      }
      break;
    }

    case "chord.upsert": {
      const existing = p.chordTrack ?? [];
      const incoming: ChordEvent = {
        ...cmd.payload.chord,
        id: cmd.payload.chord.id || makeClientId("chd"),
        startBeat: Math.max(0, Number(cmd.payload.chord.startBeat)),
        endBeat: Math.max(Math.max(0, Number(cmd.payload.chord.startBeat)) + 0.25, Number(cmd.payload.chord.endBeat)),
      };
      const idx = existing.findIndex((c) => c.id === incoming.id);
      const next = idx >= 0 ? existing.map((c, i) => (i === idx ? incoming : c)) : [...existing, incoming];
      p.chordTrack = next.sort((a, b) => a.startBeat - b.startBeat);
      break;
    }

    case "chord.delete": {
      p.chordTrack = (p.chordTrack ?? []).filter((c) => c.id !== cmd.payload.chordId);
      break;
    }

    case "chord.setLocked": {
      p.chordTrackLocked = Boolean(cmd.payload.locked);
      break;
    }
  }

  p.updatedAt = new Date().toISOString();
  return p;
}
