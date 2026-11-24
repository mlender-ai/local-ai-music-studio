import type { Asset, Clip, MidiNote, TimeSignature, Track } from "../project/types";

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
  | { type: "track.setInstrument"; payload: { trackId: string; instrumentRef: string | null } }
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
  | { type: "section.remove"; payload: { sectionId: string } };

export const NON_UNDOABLE_COMMANDS = new Set<string>(["transport.setLoop", "asset.register"]);
