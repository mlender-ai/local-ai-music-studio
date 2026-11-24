import { beatsToSeconds, dbToLinear } from "../project/time";
import type { Project } from "../project/types";
import { isTrackAudible, RealtimeAudioEngine } from "./audioEngine";
import { scheduleSynthVoice } from "./synth";
import { audioBufferToWavBlob } from "./wavEncoder";

export interface OfflineExportResult {
  blob: Blob;
  filename: string;
  sampleRate: number;
  durationSec: number;
  peakLinear: number;
  rmsLinear: number;
  clippedSamples: number;
}

/**
 * Offline Stereo WAV Renderer using Web Audio OfflineAudioContext.
 * Mirrors RealtimeAudioEngine scheduling, clip trim/loop, track gain/pan,
 * mute/solo, MIDI synthesis, and master gain identically.
 */
export async function renderProjectOfflineWav(
  project: Project,
  engine: RealtimeAudioEngine,
  options?: { useLoopRange?: boolean }
): Promise<OfflineExportResult> {
  await engine.preloadProjectAudio(project);

  const sr = project.sampleRate || 48000;
  const secPerBeat = 60 / project.bpm;
  const startBeats = options?.useLoopRange && project.loopRegion.enabled ? project.loopRegion.startBeats : 0;
  const endBeats =
    options?.useLoopRange && project.loopRegion.enabled ? project.loopRegion.endBeats : project.lengthBeats;
  const durationSec = Math.max(0.25, beatsToSeconds(endBeats - startBeats, project.bpm));
  const frameCount = Math.ceil(durationSec * sr);

  const offline = new OfflineAudioContext(2, frameCount, sr);
  const masterGain = offline.createGain();
  masterGain.gain.value = dbToLinear(project.masterGainDb);
  masterGain.connect(offline.destination);

  for (const track of project.tracks) {
    if (!isTrackAudible(track, project.tracks)) continue;
    const trackGain = offline.createGain();
    trackGain.gain.value = dbToLinear(track.gainDb);
    const panner = offline.createStereoPanner();
    panner.pan.value = Math.max(-1, Math.min(1, track.pan));
    trackGain.connect(panner);
    panner.connect(masterGain);

    for (const clip of track.clips) {
      const clipStartSec = (clip.timelineStartBeats - startBeats) * secPerBeat;
      const clipDurSec = clip.durationBeats * secPerBeat;
      const clipEndSec = clipStartSec + clipDurSec;
      if (clipEndSec <= 0 || clipStartSec >= durationSec) continue;

      const clipGainLin = dbToLinear(clip.gainDb);
      if (clipGainLin <= 0) continue;

      if (clip.type === "audio" && clip.assetId) {
        const buf = engine.getCachedBuffer(project.id, clip.assetId);
        if (!buf) continue;
        const loopWindowSec = Math.max(
          0.05,
          Math.min(buf.duration - clip.sourceOffsetSec, clip.loopLengthSec ?? buf.duration - clip.sourceOffsetSec)
        );
        const startInRender = Math.max(0, clipStartSec);
        const intoClipSec = startInRender - clipStartSec;
        const playDurSec = Math.min(durationSec, clipEndSec) - startInRender;
        if (playDurSec <= 0.005) continue;

        const src = offline.createBufferSource();
        src.buffer = buf;
        const cg = offline.createGain();
        cg.gain.setValueAtTime(0.0001, startInRender);
        cg.gain.linearRampToValueAtTime(clipGainLin, startInRender + 0.003);
        if (playDurSec > 0.008) {
          cg.gain.setValueAtTime(clipGainLin, startInRender + playDurSec - 0.004);
          cg.gain.linearRampToValueAtTime(0.0001, startInRender + playDurSec);
        }
        src.connect(cg);
        cg.connect(trackGain);

        if (clip.loop) {
          src.loop = true;
          src.loopStart = clip.sourceOffsetSec;
          src.loopEnd = Math.min(buf.duration, clip.sourceOffsetSec + loopWindowSec);
          src.start(startInRender, clip.sourceOffsetSec + (intoClipSec % loopWindowSec), playDurSec);
        } else {
          const offset = clip.sourceOffsetSec + intoClipSec;
          const avail = buf.duration - offset;
          if (avail > 0.005) {
            src.start(startInRender, offset, Math.min(playDurSec, avail));
          }
        }
      } else if (clip.type === "midi" && clip.notes.length > 0) {
        const maxNoteEnd = clip.notes.reduce((m, n) => Math.max(m, n.startBeat + n.durationBeats), 4);
        const loopLenBeats = clip.loopLengthBeats ?? Math.max(4, Math.ceil(maxNoteEnd / 4) * 4);
        const reps = clip.loop ? Math.ceil(clip.durationBeats / loopLenBeats) : 1;

        for (let rep = 0; rep < reps; rep++) {
          const repOffset = rep * loopLenBeats;
          for (const note of clip.notes) {
            const relStart = repOffset + note.startBeat;
            if (relStart >= clip.durationBeats) continue;
            const clippedDur = Math.min(note.durationBeats, clip.durationBeats - relStart);
            if (clippedDur <= 0) continue;
            const noteStartSec = clipStartSec + relStart * secPerBeat;
            const noteDurSec = clippedDur * secPerBeat;
            if (noteStartSec + noteDurSec <= 0 || noteStartSec >= durationSec) continue;
            scheduleSynthVoice(
              offline,
              trackGain,
              note.pitch,
              note.velocity,
              Math.max(0, noteStartSec),
              noteDurSec,
              clipGainLin
            );
          }
        }
      }
    }
  }

  const rendered = await offline.startRendering();
  const chL = rendered.getChannelData(0);
  const chR = rendered.numberOfChannels > 1 ? rendered.getChannelData(1) : chL;
  let peakLinear = 0;
  let sumSq = 0;
  let clippedSamples = 0;
  for (let i = 0; i < chL.length; i++) {
    const aL = Math.abs(chL[i]);
    const aR = Math.abs(chR[i]);
    if (aL > peakLinear) peakLinear = aL;
    if (aR > peakLinear) peakLinear = aR;
    if (aL >= 1.0) clippedSamples++;
    if (aR >= 1.0) clippedSamples++;
    sumSq += chL[i] * chL[i] + chR[i] * chR[i];
  }
  const rmsLinear = Math.sqrt(sumSq / Math.max(1, chL.length * 2));

  const safeName = project.name.replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "") || "export";
  return {
    blob: audioBufferToWavBlob(rendered),
    filename: `${safeName}.wav`,
    sampleRate: rendered.sampleRate,
    durationSec: rendered.duration,
    peakLinear,
    rmsLinear,
    clippedSamples,
  };
}
