import { dawApi } from "../project/api";
import { beatsToSeconds, dbToLinear, secondsToBeats } from "../project/time";
import type { Clip, Project, Track, TrackMeterLevel, WaveformData } from "../project/types";
import { scheduleSynthVoice } from "./synth";

interface TrackNodes {
  input: GainNode;
  gain: GainNode;
  panner: StereoPannerNode;
  splitter: ChannelSplitterNode;
  analyserL: AnalyserNode;
  analyserR: AnalyserNode;
}

const LOOKAHEAD_MS = 25;
const SCHEDULE_AHEAD_SEC = 0.18;

export function isTrackAudible(track: Track, allTracks: Track[]): boolean {
  const anySolo = allTracks.some((t) => t.solo);
  if (anySolo) return track.solo && !track.mute;
  return !track.mute;
}

/**
 * Sample-accurate Web Audio multitrack playback engine.
 * - Uses AudioContext.currentTime as the single source of truth for playhead & scheduling.
 * - Supports mid-song seek, seamless loop wrap without cumulative drift, live gain/pan/mute/solo,
 *   real AnalyserNode Peak/RMS metering, and MIDI auditioning.
 */
export class RealtimeAudioEngine {
  private ctx: AudioContext | null = null;
  private masterGain: GainNode | null = null;
  private masterSplitter: ChannelSplitterNode | null = null;
  private masterAnalyserL: AnalyserNode | null = null;
  private masterAnalyserR: AnalyserNode | null = null;
  private masterClipLatch = false;

  private trackNodes = new Map<string, TrackNodes>();
  private audioBuffers = new Map<string, AudioBuffer>(); // keyed by `${projectId}:${assetId}`
  private pendingDecodes = new Map<string, Promise<AudioBuffer>>();
  private activeSources = new Set<AudioScheduledSourceNode>();

  private project: Project | null = null;
  private playing = false;
  private playheadBeats = 0;

  // Audio-clock synchronization anchors
  private anchorAudioTime = 0;
  private anchorSongBeats = 0;
  private scheduledUntilSongSec = 0;
  private schedulerTimer: number | null = null;
  private scheduledAudioClipKeys = new Set<string>();
  private scheduledMidiNoteKeys = new Set<string>();
  private meterScratch = new Float32Array(256);

  ensureContext(): AudioContext {
    if (!this.ctx) {
      this.ctx = new AudioContext({ sampleRate: 48000 });
      this.masterGain = this.ctx.createGain();
      this.masterSplitter = this.ctx.createChannelSplitter(2);
      this.masterAnalyserL = this.ctx.createAnalyser();
      this.masterAnalyserR = this.ctx.createAnalyser();
      this.masterAnalyserL.fftSize = 256;
      this.masterAnalyserR.fftSize = 256;

      this.masterGain.connect(this.ctx.destination);
      this.masterGain.connect(this.masterSplitter);
      this.masterSplitter.connect(this.masterAnalyserL, 0);
      this.masterSplitter.connect(this.masterAnalyserR, 1);
    }
    if (this.ctx.state === "suspended") {
      void this.ctx.resume();
    }
    return this.ctx;
  }

  get isPlaying(): boolean {
    return this.playing;
  }

  resetMasterClip(): void {
    this.masterClipLatch = false;
  }

  syncProject(project: Project): void {
    const prevProjectId = this.project?.id;
    const prevBpm = this.project?.bpm;
    const prevLoop = this.project?.loopRegion;
    this.project = project;

    // Release decoded buffers from previous project to conserve Apple Silicon unified memory
    if (prevProjectId && prevProjectId !== project.id) {
      this.stop();
      for (const key of Array.from(this.audioBuffers.keys())) {
        if (!key.startsWith(`${project.id}:`)) {
          this.audioBuffers.delete(key);
        }
      }
      this.trackNodes.forEach((nodes) => {
        nodes.input.disconnect();
        nodes.gain.disconnect();
        nodes.panner.disconnect();
      });
      this.trackNodes.clear();
    }

    if (this.ctx) {
      this.syncMixerNodes(project);
    }

    // If playing and tempo/loop changed, seamlessly re-anchor scheduler
    if (
      this.playing &&
      (prevBpm !== project.bpm ||
        prevLoop?.enabled !== project.loopRegion.enabled ||
        prevLoop?.startBeats !== project.loopRegion.startBeats ||
        prevLoop?.endBeats !== project.loopRegion.endBeats)
    ) {
      const nowBeats = this.getPlayheadBeats();
      this.restartFromBeats(nowBeats);
    }
  }

  private ensureTrackNode(track: Track): TrackNodes {
    const ctx = this.ensureContext();
    let nodes = this.trackNodes.get(track.id);
    if (!nodes) {
      const input = ctx.createGain();
      const gain = ctx.createGain();
      const panner = ctx.createStereoPanner();
      const splitter = ctx.createChannelSplitter(2);
      const analyserL = ctx.createAnalyser();
      const analyserR = ctx.createAnalyser();
      analyserL.fftSize = 256;
      analyserR.fftSize = 256;

      input.connect(gain);
      gain.connect(panner);
      panner.connect(this.masterGain!);
      panner.connect(splitter);
      splitter.connect(analyserL, 0);
      splitter.connect(analyserR, 1);

      nodes = { input, gain, panner, splitter, analyserL, analyserR };
      this.trackNodes.set(track.id, nodes);
    }
    return nodes;
  }

  private syncMixerNodes(project: Project): void {
    if (!this.ctx || !this.masterGain) return;
    const now = this.ctx.currentTime;
    this.masterGain.gain.setTargetAtTime(dbToLinear(project.masterGainDb), now, 0.012);

    const activeIds = new Set(project.tracks.map((t) => t.id));
    for (const [id, nodes] of this.trackNodes.entries()) {
      if (!activeIds.has(id)) {
        nodes.input.disconnect();
        nodes.panner.disconnect();
        this.trackNodes.delete(id);
      }
    }

    for (const track of project.tracks) {
      const nodes = this.ensureTrackNode(track);
      const audible = isTrackAudible(track, project.tracks);
      const targetGain = audible ? dbToLinear(track.gainDb) : 0;
      nodes.gain.gain.setTargetAtTime(targetGain, now, 0.012);
      nodes.panner.pan.setTargetAtTime(Math.max(-1, Math.min(1, track.pan)), now, 0.012);
    }
  }

  async loadAssetBuffer(projectId: string, assetId: string): Promise<AudioBuffer> {
    const key = `${projectId}:${assetId}`;
    const cached = this.audioBuffers.get(key);
    if (cached) return cached;
    const inflight = this.pendingDecodes.get(key);
    if (inflight) return inflight;

    const promise = (async () => {
      const ctx = this.ensureContext();
      const resp = await fetch(dawApi.assetFileUrl(projectId, assetId));
      if (!resp.ok) throw new Error(`Failed to fetch audio asset ${assetId}`);
      const arr = await resp.arrayBuffer();
      const decoded = await ctx.decodeAudioData(arr);
      this.audioBuffers.set(key, decoded);
      this.pendingDecodes.delete(key);
      return decoded;
    })();

    this.pendingDecodes.set(key, promise);
    return promise;
  }

  getCachedBuffer(projectId: string, assetId: string): AudioBuffer | undefined {
    return this.audioBuffers.get(`${projectId}:${assetId}`);
  }

  async preloadProjectAudio(project: Project): Promise<void> {
    const audioAssets = project.assets.filter((a) => a.kind !== "midi");
    await Promise.allSettled(audioAssets.map((a) => this.loadAssetBuffer(project.id, a.id)));
  }

  /** Extract real waveform peaks directly from a decoded AudioBuffer (client fallback for MP3/M4A). */
  extractWaveformFromBuffer(buf: AudioBuffer, bins = 1024): WaveformData {
    const total = buf.length;
    const ch0 = buf.getChannelData(0);
    const ch1 = buf.numberOfChannels > 1 ? buf.getChannelData(1) : ch0;
    const actualBins = Math.min(bins, Math.max(1, total));
    const step = total / actualBins;
    const peaks: number[] = new Array(actualBins);
    const rms: number[] = new Array(actualBins);
    for (let b = 0; b < actualBins; b++) {
      const s = Math.floor(b * step);
      const e = Math.min(total, Math.max(s + 1, Math.floor((b + 1) * step)));
      let maxAbs = 0;
      let sumSq = 0;
      for (let i = s; i < e; i++) {
        const m = 0.5 * (ch0[i] + ch1[i]);
        const a = Math.abs(m);
        if (a > maxAbs) maxAbs = a;
        sumSq += m * m;
      }
      peaks[b] = maxAbs;
      rms[b] = Math.sqrt(sumSq / (e - s));
    }
    return {
      sampleRate: buf.sampleRate,
      channels: buf.numberOfChannels,
      durationSamples: total,
      durationSec: buf.duration,
      bins: actualBins,
      peaks,
      rms,
    };
  }

  getPlayheadBeats(): number {
    if (!this.project) return 0;
    if (!this.playing || !this.ctx) return this.playheadBeats;

    const elapsedSec = Math.max(0, this.ctx.currentTime - this.anchorAudioTime);
    const rawBeats = this.anchorSongBeats + secondsToBeats(elapsedSec, this.project.bpm);
    const loop = this.project.loopRegion;

    if (loop.enabled && loop.endBeats > loop.startBeats && rawBeats >= loop.startBeats) {
      const loopLen = loop.endBeats - loop.startBeats;
      const wrapped = loop.startBeats + (((rawBeats - loop.startBeats) % loopLen) + loopLen) % loopLen;
      return wrapped;
    }

    if (rawBeats >= this.project.lengthBeats) {
      return this.project.lengthBeats;
    }
    return rawBeats;
  }

  async play(fromBeats?: number): Promise<void> {
    if (!this.project) return;
    const ctx = this.ensureContext();
    if (ctx.state === "suspended") {
      await ctx.resume();
    }
    await this.preloadProjectAudio(this.project);
    this.syncMixerNodes(this.project);

    const startBeats =
      fromBeats !== undefined
        ? Math.max(0, fromBeats)
        : this.playheadBeats >= this.project.lengthBeats - 0.05
          ? 0
          : this.playheadBeats;

    this.restartFromBeats(startBeats);
  }

  pause(): void {
    if (!this.playing) return;
    this.playheadBeats = this.getPlayheadBeats();
    this.clearPlayback();
    this.playing = false;
  }

  stop(): void {
    this.clearPlayback();
    this.playing = false;
    this.playheadBeats = 0;
  }

  seek(beats: number): void {
    const clamped = Math.max(0, this.project ? Math.min(this.project.lengthBeats, beats) : beats);
    this.playheadBeats = clamped;
    if (this.playing) {
      this.restartFromBeats(clamped);
    }
  }

  /** Re-schedule active playback after clips/notes are edited mid-playback. */
  resyncActivePlayback(): void {
    if (this.playing) {
      const nowBeats = this.getPlayheadBeats();
      this.restartFromBeats(nowBeats);
    }
  }

  auditionMidiNote(pitch: number, velocity = 100, durationSec = 0.28): void {
    const ctx = this.ensureContext();
    if (this.masterGain) {
      scheduleSynthVoice(ctx, this.masterGain, pitch, velocity, ctx.currentTime + 0.005, durationSec, 0.9);
    }
  }

  private clearPlayback(): void {
    if (this.schedulerTimer !== null) {
      window.clearInterval(this.schedulerTimer);
      this.schedulerTimer = null;
    }
    for (const src of this.activeSources) {
      try {
        src.stop();
        src.disconnect();
      } catch {
        // already stopped
      }
    }
    this.activeSources.clear();
    this.scheduledAudioClipKeys.clear();
    this.scheduledMidiNoteKeys.clear();
  }

  private restartFromBeats(startBeats: number): void {
    if (!this.project) return;
    const ctx = this.ensureContext();
    this.clearPlayback();
    this.syncMixerNodes(this.project);

    this.playing = true;
    this.playheadBeats = startBeats;
    this.anchorAudioTime = ctx.currentTime + 0.03;
    this.anchorSongBeats = startBeats;
    this.scheduledUntilSongSec = 0; // relative to anchorAudioTime

    this.runSchedulerTick();
    this.schedulerTimer = window.setInterval(() => this.runSchedulerTick(), LOOKAHEAD_MS);
  }

  private runSchedulerTick(): void {
    if (!this.playing || !this.project || !this.ctx) return;

    const project = this.project;
    const now = this.ctx.currentTime;
    const elapsedSinceAnchor = now - this.anchorAudioTime;
    const windowStartRelSec = Math.max(0, this.scheduledUntilSongSec);
    const windowEndRelSec = Math.max(windowStartRelSec, elapsedSinceAnchor + SCHEDULE_AHEAD_SEC);

    const loop = project.loopRegion;
    const songLengthSec = beatsToSeconds(project.lengthBeats, project.bpm);
    const anchorSongSec = beatsToSeconds(this.anchorSongBeats, project.bpm);

    // Stop cleanly when reaching project end (if loop is disabled)
    if (!loop.enabled && anchorSongSec + elapsedSinceAnchor >= songLengthSec) {
      this.playheadBeats = project.lengthBeats;
      this.clearPlayback();
      this.playing = false;
      return;
    }

    // Break [windowStartRelSec, windowEndRelSec] into contiguous song-time slices across loop boundaries
    const slices = this.computeSongSlices(windowStartRelSec, windowEndRelSec, project);
    for (const slice of slices) {
      this.scheduleSlice(project, slice.audioStartTime, slice.songStartSec, slice.songEndSec, slice.cycleIndex);
    }

    this.scheduledUntilSongSec = windowEndRelSec;
  }

  private computeSongSlices(
    relStartSec: number,
    relEndSec: number,
    project: Project
  ): Array<{ audioStartTime: number; songStartSec: number; songEndSec: number; cycleIndex: number }> {
    const slices: Array<{ audioStartTime: number; songStartSec: number; songEndSec: number; cycleIndex: number }> = [];
    const anchorSongSec = beatsToSeconds(this.anchorSongBeats, project.bpm);
    const loop = project.loopRegion;
    const loopStartSec = beatsToSeconds(loop.startBeats, project.bpm);
    const loopEndSec = beatsToSeconds(loop.endBeats, project.bpm);
    const loopLenSec = loopEndSec - loopStartSec;
    const songLenSec = beatsToSeconds(project.lengthBeats, project.bpm);

    let cursorRel = relStartSec;
    while (cursorRel < relEndSec - 1e-6) {
      const rawSongSec = anchorSongSec + cursorRel;
      if (loop.enabled && loopLenSec > 0.05 && rawSongSec >= loopStartSec) {
        const intoLoop = rawSongSec - loopStartSec;
        const cycleIndex = Math.floor(intoLoop / loopLenSec);
        const posInLoop = intoLoop - cycleIndex * loopLenSec;
        const songStartSec = loopStartSec + posInLoop;
        const remainingInLoop = loopEndSec - songStartSec;
        const segDur = Math.min(relEndSec - cursorRel, remainingInLoop);
        if (segDur <= 1e-6) break;
        slices.push({
          audioStartTime: this.anchorAudioTime + cursorRel,
          songStartSec,
          songEndSec: songStartSec + segDur,
          cycleIndex,
        });
        cursorRel += segDur;
      } else {
        const limitSec =
          loop.enabled && loopLenSec > 0.05 && rawSongSec < loopStartSec
            ? loopStartSec
            : songLenSec;
        const remaining = limitSec - rawSongSec;
        if (remaining <= 1e-6) break;
        const segDur = Math.min(relEndSec - cursorRel, remaining);
        slices.push({
          audioStartTime: this.anchorAudioTime + cursorRel,
          songStartSec: rawSongSec,
          songEndSec: rawSongSec + segDur,
          cycleIndex: -1,
        });
        cursorRel += segDur;
      }
    }
    return slices;
  }

  private scheduleSlice(
    project: Project,
    audioStartTime: number,
    songStartSec: number,
    songEndSec: number,
    cycleIndex: number
  ): void {
    if (!this.ctx) return;
    const secPerBeat = 60 / project.bpm;

    for (const track of project.tracks) {
      const nodes = this.ensureTrackNode(track);
      for (const clip of track.clips) {
        const clipStartSec = clip.timelineStartBeats * secPerBeat;
        const clipDurSec = clip.durationBeats * secPerBeat;
        const clipEndSec = clipStartSec + clipDurSec;

        if (clipEndSec <= songStartSec || clipStartSec >= songEndSec) continue;

        if (clip.type === "audio" && clip.assetId) {
          this.scheduleAudioClipInSlice(
            project,
            nodes,
            clip,
            clipStartSec,
            clipEndSec,
            audioStartTime,
            songStartSec,
            songEndSec,
            cycleIndex
          );
        } else if (clip.type === "midi") {
          this.scheduleMidiClipInSlice(
            project,
            nodes,
            clip,
            clipStartSec,
            audioStartTime,
            songStartSec,
            songEndSec,
            cycleIndex
          );
        }
      }
    }
  }

  private scheduleAudioClipInSlice(
    project: Project,
    nodes: TrackNodes,
    clip: Clip,
    clipStartSec: number,
    clipEndSec: number,
    audioStartTime: number,
    songStartSec: number,
    songEndSec: number,
    cycleIndex: number
  ): void {
    if (!this.ctx || !clip.assetId) return;
    const buf = this.audioBuffers.get(`${project.id}:${clip.assetId}`);
    if (!buf) return;

    const loopWindowSec = Math.max(
      0.05,
      Math.min(buf.duration - clip.sourceOffsetSec, clip.loopLengthSec ?? buf.duration - clip.sourceOffsetSec)
    );
    if (loopWindowSec <= 0.01) return;

    // Limit playback end to loop boundary if looping project
    const projLoopEnd =
      project.loopRegion.enabled && songStartSec < beatsToSeconds(project.loopRegion.endBeats, project.bpm)
        ? beatsToSeconds(project.loopRegion.endBeats, project.bpm)
        : beatsToSeconds(project.lengthBeats, project.bpm);
    const effectiveClipEnd = Math.min(clipEndSec, projLoopEnd);

    const overlapStart = Math.max(clipStartSec, songStartSec);
    if (overlapStart >= effectiveClipEnd) return;

    // Schedule each audio clip once per loop cycle (or once when non-looping)
    const scheduleKey = `${clip.id}:${cycleIndex}`;
    if (this.scheduledAudioClipKeys.has(scheduleKey)) return;
    this.scheduledAudioClipKeys.add(scheduleKey);

    const when = audioStartTime + (overlapStart - songStartSec);
    const intoClipSec = overlapStart - clipStartSec;
    const playDurSec = effectiveClipEnd - overlapStart;

    const src = this.ctx.createBufferSource();
    src.buffer = buf;

    const clipGain = this.ctx.createGain();
    const linGain = dbToLinear(clip.gainDb);
    // Tiny 3ms de-click fade-in/out
    clipGain.gain.setValueAtTime(0.0001, when);
    clipGain.gain.linearRampToValueAtTime(linGain, when + 0.003);
    if (playDurSec > 0.008) {
      clipGain.gain.setValueAtTime(linGain, when + playDurSec - 0.004);
      clipGain.gain.linearRampToValueAtTime(0.0001, when + playDurSec);
    }

    src.connect(clipGain);
    clipGain.connect(nodes.input);

    if (clip.loop) {
      src.loop = true;
      src.loopStart = clip.sourceOffsetSec;
      src.loopEnd = Math.min(buf.duration, clip.sourceOffsetSec + loopWindowSec);
      const offsetInLoop = clip.sourceOffsetSec + (intoClipSec % loopWindowSec);
      src.start(when, offsetInLoop, playDurSec);
    } else {
      const srcOffset = clip.sourceOffsetSec + intoClipSec;
      const remainingBuf = buf.duration - srcOffset;
      if (remainingBuf <= 0.005) return;
      src.start(when, srcOffset, Math.min(playDurSec, remainingBuf));
    }

    this.activeSources.add(src);
    src.onended = () => {
      this.activeSources.delete(src);
      src.disconnect();
      clipGain.disconnect();
    };
  }

  private scheduleMidiClipInSlice(
    project: Project,
    nodes: TrackNodes,
    clip: Clip,
    clipStartSec: number,
    audioStartTime: number,
    songStartSec: number,
    songEndSec: number,
    cycleIndex: number
  ): void {
    if (!this.ctx || clip.notes.length === 0) return;
    const secPerBeat = 60 / project.bpm;
    const clipGainLin = dbToLinear(clip.gainDb);

    const maxNoteEnd = clip.notes.reduce((m, n) => Math.max(m, n.startBeat + n.durationBeats), 4);
    const loopLenBeats = clip.loopLengthBeats ?? Math.max(4, Math.ceil(maxNoteEnd / 4) * 4);
    const reps = clip.loop ? Math.ceil(clip.durationBeats / loopLenBeats) : 1;

    for (let rep = 0; rep < reps; rep++) {
      const repOffsetBeats = rep * loopLenBeats;
      for (const note of clip.notes) {
        const relStartBeats = repOffsetBeats + note.startBeat;
        if (relStartBeats >= clip.durationBeats) continue;
        const clippedDurBeats = Math.min(note.durationBeats, clip.durationBeats - relStartBeats);
        if (clippedDurBeats <= 0) continue;

        const noteStartSec = clipStartSec + relStartBeats * secPerBeat;
        const noteDurSec = clippedDurBeats * secPerBeat;
        if (noteStartSec < songStartSec - 0.002 || noteStartSec >= songEndSec) continue;

        const noteKey = `${clip.id}:${rep}:${note.id}:${cycleIndex}`;
        if (this.scheduledMidiNoteKeys.has(noteKey)) continue;
        this.scheduledMidiNoteKeys.add(noteKey);

        const when = audioStartTime + Math.max(0, noteStartSec - songStartSec);
        const oscs = scheduleSynthVoice(
          this.ctx,
          nodes.input,
          note.pitch,
          note.velocity,
          when,
          noteDurSec,
          clipGainLin
        );
        for (const osc of oscs) {
          this.activeSources.add(osc);
          osc.onended = () => this.activeSources.delete(osc);
        }
      }
    }
  }

  private sampleAnalyser(analyser: AnalyserNode): { peak: number; rms: number } {
    analyser.getFloatTimeDomainData(this.meterScratch);
    let peak = 0;
    let sumSq = 0;
    for (let i = 0; i < this.meterScratch.length; i++) {
      const v = Math.abs(this.meterScratch[i]);
      if (v > peak) peak = v;
      sumSq += v * v;
    }
    return { peak, rms: Math.sqrt(sumSq / this.meterScratch.length) };
  }

  readMeters(): { tracks: Record<string, TrackMeterLevel>; master: TrackMeterLevel } {
    const tracks: Record<string, TrackMeterLevel> = {};
    if (!this.ctx || !this.masterAnalyserL || !this.masterAnalyserR) {
      return {
        tracks,
        master: { peakL: 0, peakR: 0, rmsL: 0, rmsR: 0, clipping: this.masterClipLatch },
      };
    }

    for (const [id, nodes] of this.trackNodes.entries()) {
      const l = this.sampleAnalyser(nodes.analyserL);
      const r = this.sampleAnalyser(nodes.analyserR);
      tracks[id] = {
        peakL: l.peak,
        peakR: r.peak,
        rmsL: l.rms,
        rmsR: r.rms,
        clipping: l.peak >= 0.99 || r.peak >= 0.99,
      };
    }

    const ml = this.sampleAnalyser(this.masterAnalyserL);
    const mr = this.sampleAnalyser(this.masterAnalyserR);
    if (ml.peak >= 0.99 || mr.peak >= 0.99) {
      this.masterClipLatch = true;
    }
    return {
      tracks,
      master: {
        peakL: ml.peak,
        peakR: mr.peak,
        rmsL: ml.rms,
        rmsR: mr.rms,
        clipping: this.masterClipLatch,
      },
    };
  }
}

export const audioEngine = new RealtimeAudioEngine();
