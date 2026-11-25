import type {
  Asset,
  AutomationLane,
  ChordEvent,
  Clip,
  EffectSlot,
  MidiNote,
  TakeLane,
  TimeSignature,
  Track,
} from "../project/types";

export type ProjectCommand =
  | { type: "project.rename"; payload: { name: string } }
  | { type: "project.setTempo"; payload: { bpm: number } }
  | { type: "project.setTimeSignature"; payload: TimeSignature }
  | { type: "project.setLength"; payload: { lengthBeats: number } }
  | { type: "project.setMasterGain"; payload: { gainDb: number } }
  | { type: "transport.setLoop"; payload: { enabled?: boolean; startBeats?: number; endBeats?: number } }
  | { type: "asset.register"; payload: { asset: Asset } }
  | {
      type: "track.add";
      payload: {
        id?: string;
        name?: string;
        type: Track["type"];
        color?: string;
        stemLabel?: string;
        instrumentRef?: string | null;
      };
    }
  | { type: "track.remove"; payload: { trackId: string } }
  | { type: "track.rename"; payload: { trackId: string; name: string } }
  | { type: "track.reorder"; payload: { fromIndex: number; toIndex: number } }
  | { type: "track.setColor"; payload: { trackId: string; color: string } }
  | { type: "track.setGain"; payload: { trackId: string; gainDb: number } }
  | { type: "track.setPan"; payload: { trackId: string; pan: number } }
  | { type: "track.setMute"; payload: { trackId: string; mute: boolean } }
  | { type: "track.setSolo"; payload: { trackId: string; solo: boolean } }
  | {
      type: "track.setInstrument";
      payload: {
        trackId: string;
        instrumentRef: string | null;
        preset?: string | null;
        parameters?: Record<string, unknown>;
      };
    }
  | {
      type: "instrument.setPreset";
      payload: { trackId: string; preset: string | null; parameters?: Record<string, unknown> };
    }
  | {
      type: "instrument.setParams";
      payload: {
        trackId: string;
        parameters: Record<string, unknown>;
        articulation?: string;
        samplerConfig?: Record<string, unknown>;
        drumRackConfig?: Record<string, unknown>;
      };
    }
  | {
      type: "fx.add";
      payload: {
        trackId?: string;
        busId?: string;
        target?: "track" | "bus" | "master";
        slot: EffectSlot;
        index?: number;
      };
    }
  | {
      type: "fx.remove";
      payload: { trackId?: string; busId?: string; target?: "track" | "bus" | "master"; fxId: string };
    }
  | {
      type: "fx.move";
      payload: {
        trackId?: string;
        busId?: string;
        target?: "track" | "bus" | "master";
        fromIndex: number;
        toIndex: number;
      };
    }
  | {
      type: "fx.setParams";
      payload: {
        trackId?: string;
        busId?: string;
        target?: "track" | "bus" | "master";
        fxId: string;
        parameters?: Record<string, unknown>;
        preset?: string | null;
        wetDry?: number;
        sidechainTrackId?: string | null;
      };
    }
  | {
      type: "fx.setBypass";
      payload: {
        trackId?: string;
        busId?: string;
        target?: "track" | "bus" | "master";
        fxId: string;
        bypass: boolean;
      };
    }
  | {
      type: "bus.add";
      payload: { id?: string; name: string; kind?: "return" | "group"; effects?: EffectSlot[] };
    }
  | { type: "bus.remove"; payload: { busId: string } }
  | { type: "bus.setGain"; payload: { busId: string; gainDb: number } }
  | { type: "bus.setMute"; payload: { busId: string; mute: boolean } }
  | { type: "bus.setSolo"; payload: { busId: string; solo: boolean } }
  | {
      type: "send.set";
      payload: { trackId: string; busId: string; levelDb: number; preFader?: boolean; enabled?: boolean };
    }
  | { type: "send.remove"; payload: { trackId: string; busId: string } }
  | { type: "automation.upsertLane"; payload: { trackId: string; lane: AutomationLane } }
  | { type: "automation.removeLane"; payload: { trackId: string; laneId: string } }
  | { type: "track.addTakeLane"; payload: { trackId: string; lane: TakeLane } }
  | { type: "track.renameTakeLane"; payload: { trackId: string; laneId: string; name: string } }
  | { type: "track.removeTakeLane"; payload: { trackId: string; laneId: string } }
  | { type: "clip.setFades"; payload: { clipId: string; fadeInBeats?: number; fadeOutBeats?: number } }
  | { type: "clip.add"; payload: { trackId: string; clip: Clip } }
  | {
      type: "clip.move";
      payload: { clipId: string; timelineStartBeats: number; targetTrackId?: string };
    }
  | {
      type: "clip.trim";
      payload: {
        clipId: string;
        timelineStartBeats?: number;
        durationBeats?: number;
        sourceOffsetSec?: number;
      };
    }
  | { type: "clip.split"; payload: { clipId: string; splitBeat: number; rightClipId?: string } }
  | {
      type: "clip.duplicate";
      payload: { clipId: string; timelineStartBeats?: number; newClipId?: string };
    }
  | { type: "clip.delete"; payload: { clipId: string } }
  | { type: "clip.setGain"; payload: { clipId: string; gainDb: number } }
  | { type: "clip.setLoop"; payload: { clipId: string; loop: boolean } }
  | { type: "clip.rename"; payload: { clipId: string; name: string } }
  | { type: "midi.addNote"; payload: { clipId: string; note: MidiNote } }
  | { type: "midi.moveNote"; payload: { clipId: string; noteId: string; pitch: number; startBeat: number } }
  | { type: "midi.resizeNote"; payload: { clipId: string; noteId: string; durationBeats: number } }
  | { type: "midi.setVelocity"; payload: { clipId: string; noteId: string; velocity: number } }
  | { type: "midi.deleteNote"; payload: { clipId: string; noteId: string } }
  | {
      type: "section.add";
      payload: { id?: string; name: string; startBeats: number; endBeats: number; color?: string };
    }
  | { type: "section.rename"; payload: { sectionId: string; name: string } }
  | { type: "section.remove"; payload: { sectionId: string } }
  | { type: "chord.setTrack"; payload: { chords: ChordEvent[]; locked?: boolean } }
  | { type: "chord.upsert"; payload: { chord: ChordEvent } }
  | { type: "chord.delete"; payload: { chordId: string } }
  | { type: "chord.setLocked"; payload: { locked: boolean } };

export const NON_UNDOABLE_COMMANDS = new Set<string>(["transport.setLoop", "asset.register"]);
