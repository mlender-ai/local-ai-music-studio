import { beatsToSeconds, dbToLinear } from "../project/time";
import type { Project } from "../project/types";
import { RealtimeAudioEngine } from "./audioEngine";
import {
  collectMidiEventsForWindow,
  computeAudioClipSegment,
  findBrokenAudibleAssets,
  isTrackAudible,
} from "./scheduler";
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
 * Shares the EXACT `computeAudioClipSegment` and `collectMidiEventsForWindow`
 * scheduling rules as RealtimeAudioEngine, and refuses silent omission of
 * missing/broken audio assets.
 */
export async function renderProjectOfflineWav(
  project: Project,
  engine: RealtimeAudioEngine,
  options?: { useLoopRange?: boolean }
): Promise<OfflineExportResult> {
  await engine.preloadProjectAudio(project);

  // Refuse to silently omit broken/missing audible audio assets
  const broken = findBrokenAudibleAssets(
    project,
    engine.getAssetStates(project.id),
    (assetId) => Boolean(engine.getCachedBuffer(project.id, assetId))
  );
  if (broken.length > 0) {
    const first = broken[0];
    throw new Error(
      `Cannot export: audio asset for "${first.trackName} / ${first.clipName}" failed to load (${first.reason}). Relink or retry loading first.`
    );
  }

  const sr = project.sampleRate || 48000;
  const startBeats = options?.useLoopRange && project.loopRegion.enabled ? project.loopRegion.startBeats : 0;
  const endBeats =
    options?.useLoopRange && project.loopRegion.enabled ? project.loopRegion.endBeats : project.lengthBeats;
  const startSec = beatsToSeconds(startBeats, project.bpm);
  const endSec = beatsToSeconds(endBeats, project.bpm);
  const durationSec = Math.max(0.25, endSec - startSec);
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
      if (clip.type === "audio" && clip.assetId) {
        const buf = engine.getCachedBuffer(project.id, clip.assetId);
        if (!buf) continue;
        const seg = computeAudioClipSegment(clip, project.bpm, buf.duration, startSec, endSec, endSec);
        if (!seg) continue;

        const when = Math.max(0, seg.songStartSec - startSec);
        const src = offline.createBufferSource();
        src.buffer = buf;

        const cg = offline.createGain();
        cg.gain.setValueAtTime(0.0001, when);
        cg.gain.linearRampToValueAtTime(seg.clipGainLinear, when + 0.003);
        if (seg.playDurSec > 0.008) {
          cg.gain.setValueAtTime(seg.clipGainLinear, when + seg.playDurSec - 0.004);
          cg.gain.linearRampToValueAtTime(0.0001, when + seg.playDurSec);
        }
        src.connect(cg);
        cg.connect(trackGain);

        if (seg.loop) {
          src.loop = true;
          src.loopStart = seg.loopStartSec;
          src.loopEnd = seg.loopEndSec;
        }
        src.start(when, seg.sourceStartSec, seg.playDurSec);
      } else if (clip.type === "midi" && clip.notes.length > 0) {
        const events = collectMidiEventsForWindow(clip, project.bpm, startSec, endSec, endSec, true, 0);
        for (const ev of events) {
          const when = Math.max(0, ev.songStartSec - startSec);
          scheduleSynthVoice(
            offline,
            trackGain,
            ev.pitch,
            ev.velocity,
            when,
            ev.durationSec,
            ev.clipGainLinear,
            ev.chased
          );
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
