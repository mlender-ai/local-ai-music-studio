import { dbToLinear } from "../project/time";
import type { Clip, Project, Track } from "../project/types";

export interface ScheduledAudioSegment {
  clipId: string;
  assetId: string;
  songStartSec: number;
  playDurSec: number;
  sourceStartSec: number;
  loop: boolean;
  loopStartSec: number;
  loopEndSec: number;
  clipGainLinear: number;
}

export interface ScheduledMidiEvent {
  key: string;
  clipId: string;
  noteId: string;
  pitch: number;
  velocity: number;
  songStartSec: number;
  durationSec: number;
  clipGainLinear: number;
  chased: boolean;
}

export function isTrackAudible(track: Track, allTracks: Track[]): boolean {
  const anySolo = allTracks.some((t) => t.solo);
  if (anySolo) return track.solo && !track.mute;
  return !track.mute;
}

/**
 * Shared pure audio clip scheduling calculation used by BOTH RealtimeAudioEngine
 * and OfflineAudioContext WAV export so both paths produce identical timing, trims,
 * loops, and gain.
 */
export function computeAudioClipSegment(
  clip: Clip,
  bpm: number,
  bufferDurationSec: number,
  windowStartSec: number,
  windowEndSec: number,
  boundaryLimitSec: number
): ScheduledAudioSegment | null {
  if (clip.type !== "audio" || !clip.assetId || bufferDurationSec <= 0.005) return null;
  const secPerBeat = 60 / bpm;
  const clipStartSec = clip.timelineStartBeats * secPerBeat;
  const clipEndSec = Math.min(clipStartSec + clip.durationBeats * secPerBeat, boundaryLimitSec);

  if (clipEndSec <= windowStartSec || clipStartSec >= windowEndSec) return null;

  const overlapStart = Math.max(clipStartSec, windowStartSec);
  const playDurSec = clipEndSec - overlapStart;
  if (playDurSec <= 0.004) return null;

  const intoClipSec = overlapStart - clipStartSec;
  const maxAvailFromOffset = Math.max(0, bufferDurationSec - clip.sourceOffsetSec);
  const loopWindowSec = Math.max(
    0.05,
    Math.min(maxAvailFromOffset, clip.loopLengthSec ?? maxAvailFromOffset)
  );
  if (loopWindowSec <= 0.01) return null;

  const clipGainLinear = dbToLinear(clip.gainDb);
  if (clipGainLinear <= 0) return null;

  if (clip.loop) {
    return {
      clipId: clip.id,
      assetId: clip.assetId,
      songStartSec: overlapStart,
      playDurSec,
      sourceStartSec: clip.sourceOffsetSec + (intoClipSec % loopWindowSec),
      loop: true,
      loopStartSec: clip.sourceOffsetSec,
      loopEndSec: Math.min(bufferDurationSec, clip.sourceOffsetSec + loopWindowSec),
      clipGainLinear,
    };
  }

  const sourceStartSec = clip.sourceOffsetSec + intoClipSec;
  const remainingBuf = bufferDurationSec - sourceStartSec;
  if (remainingBuf <= 0.004) return null;

  return {
    clipId: clip.id,
    assetId: clip.assetId,
    songStartSec: overlapStart,
    playDurSec: Math.min(playDurSec, remainingBuf),
    sourceStartSec,
    loop: false,
    loopStartSec: 0,
    loopEndSec: 0,
    clipGainLinear,
  };
}

/**
 * Shared pure MIDI note scheduling calculation with full MIDI Chase support.
 * - Normal trigger: notes starting inside [windowStartSec, windowEndSec)
 * - MIDI Chase (`allowChase = true`): notes already sounding across `windowStartSec`
 *   (started before `windowStartSec` and still sounding past `windowStartSec`) are
 *   triggered immediately at `windowStartSec` for their remaining duration clipped to
 *   `boundaryLimitSec` (loop end or project end).
 */
export function collectMidiEventsForWindow(
  clip: Clip,
  bpm: number,
  windowStartSec: number,
  windowEndSec: number,
  boundaryLimitSec: number,
  allowChase: boolean,
  cycleIndex = 0
): ScheduledMidiEvent[] {
  if (clip.type !== "midi" || clip.notes.length === 0) return [];
  const secPerBeat = 60 / bpm;
  const clipStartSec = clip.timelineStartBeats * secPerBeat;
  const clipEndSec = Math.min(clipStartSec + clip.durationBeats * secPerBeat, boundaryLimitSec);
  if (clipEndSec <= windowStartSec || clipStartSec >= windowEndSec) return [];

  const clipGainLinear = dbToLinear(clip.gainDb);
  if (clipGainLinear <= 0) return [];

  const maxNoteEnd = clip.notes.reduce((m, n) => Math.max(m, n.startBeat + n.durationBeats), 4);
  const loopLenBeats = clip.loopLengthBeats ?? Math.max(4, Math.ceil(maxNoteEnd / 4) * 4);
  const reps = clip.loop ? Math.ceil(clip.durationBeats / loopLenBeats) : 1;

  const events: ScheduledMidiEvent[] = [];
  for (let rep = 0; rep < reps; rep++) {
    const repOffsetBeats = rep * loopLenBeats;
    for (const note of clip.notes) {
      const relStartBeats = repOffsetBeats + note.startBeat;
      if (relStartBeats >= clip.durationBeats) continue;
      const clippedDurBeats = Math.min(note.durationBeats, clip.durationBeats - relStartBeats);
      if (clippedDurBeats <= 0) continue;

      const noteStartSec = clipStartSec + relStartBeats * secPerBeat;
      const noteEndSec = Math.min(noteStartSec + clippedDurBeats * secPerBeat, clipEndSec);
      if (noteEndSec <= noteStartSec + 0.005) continue;

      // Case 1: Normal note start within this lookahead slice
      if (noteStartSec >= windowStartSec - 0.001 && noteStartSec < windowEndSec) {
        const clampedStart = Math.max(windowStartSec, noteStartSec);
        const dur = noteEndSec - clampedStart;
        if (dur > 0.005) {
          events.push({
            key: `${clip.id}:${rep}:${note.id}:${cycleIndex}:norm`,
            clipId: clip.id,
            noteId: note.id,
            pitch: note.pitch,
            velocity: note.velocity,
            songStartSec: clampedStart,
            durationSec: dur,
            clipGainLinear,
            chased: false,
          });
        }
      }
      // Case 2: MIDI Chase — playback/seek/loop-entry landed mid-note
      else if (allowChase && noteStartSec < windowStartSec - 0.001 && noteEndSec > windowStartSec + 0.015) {
        const remainingDur = noteEndSec - windowStartSec;
        events.push({
          key: `${clip.id}:${rep}:${note.id}:${cycleIndex}:chase`,
          clipId: clip.id,
          noteId: note.id,
          pitch: note.pitch,
          velocity: note.velocity,
          songStartSec: windowStartSec,
          durationSec: remainingDur,
          clipGainLinear,
          chased: true,
        });
      }
    }
  }
  return events;
}

/** Identify audible audio clips whose assets are missing or failed to decode. */
export function findBrokenAudibleAssets(
  project: Project,
  assetStatuses: Record<string, { status: string; error?: string }>,
  hasBuffer: (assetId: string) => boolean
): Array<{ trackName: string; clipName: string; assetId: string; reason: string }> {
  const broken: Array<{ trackName: string; clipName: string; assetId: string; reason: string }> = [];
  for (const track of project.tracks) {
    if (!isTrackAudible(track, project.tracks)) continue;
    for (const clip of track.clips) {
      if (clip.type !== "audio" || !clip.assetId) continue;
      const st = assetStatuses[clip.assetId];
      if (st?.status === "error" || !hasBuffer(clip.assetId)) {
        broken.push({
          trackName: track.name,
          clipName: clip.name,
          assetId: clip.assetId,
          reason: st?.error || "Audio asset not loaded or missing on disk",
        });
      }
    }
  }
  return broken;
}
