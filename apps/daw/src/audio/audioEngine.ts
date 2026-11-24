import { dawApi } from "../project/api";
import { beatsToSeconds, dbToLinear, secondsToBeats } from "../project/time";
import type { AssetLoadState, Project, Track, TrackMeterLevel, WaveformData } from "../project/types";
import {
  collectMidiEventsForWindow,
  computeAudioClipSegment,
  isTrackAudible,
} from "./scheduler";
import { scheduleSynthVoice } from "./synth";

export { isTrackAudible } from "./scheduler";

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

/**
 * Sample-accurate Web Audio multitrack playback engine (Phase 01.1 hardened):
 * - Single shared scheduling math with OfflineAudioContext WAV export (`scheduler.ts`)
 * - Full MIDI Chase when starting/seeking/looping mid-note
 * - Monotonic playToken to prevent ghost/duplicate playback on rapid Play/Stop clicks
 * - Per-asset decode status tracking with failed-cache eviction and retry/relink support
 * - Standalone Reference audio preview player (strictly excluded from project export)
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
  private assetStates = new Map<string, AssetLoadState>(); // keyed by `${projectId}:${assetId}`
  private stateListeners = new Set<() => void>();
  private activeSources = new Set<AudioScheduledSourceNode>();

  // Standalone reference audition state
  private refSource: AudioBufferSourceNode | null = null;
  private refBufferCache = new Map<string, AudioBuffer>();
  private refPlayingKey: string | null = null;
  private refStartAudioTime = 0;
  private refStartOffsetSec = 0;
  private refDurationSec = 0;

  private project: Project | null = null;
  private playing = false;
  private playheadBeats = 0;
  private playToken = 0;

  // Audio-clock synchronization anchors
  private anchorAudioTime = 0;
  private anchorSongBeats = 0;
  private scheduledUntilSongSec = 0;
  private schedulerTimer: number | null = null;
  private scheduledAudioClipKeys = new Set<string>();
  private scheduledMidiNoteKeys = new Set<string>();
  private chasedCycleKeys = new Set<string>();
  private meterScratch = new Float32Array(256);

  subscribeAssetStates(listener: () => void): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  private emitAssetStates(): void {
    for (const fn of this.stateListeners) fn();
  }

  getAssetStates(projectId: string): Record<string, AssetLoadState> {
    const out: Record<string, AssetLoadState> = {};
    const prefix = `${projectId}:`;
    for (const [k, v] of this.assetStates.entries()) {
      if (k.startsWith(prefix)) {
        out[k.slice(prefix.length)] = v;
      }
    }
    return out;
  }

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
      this.stopReferencePreview();
      for (const key of Array.from(this.audioBuffers.keys())) {
        if (!key.startsWith(`${project.id}:`)) {
          this.audioBuffers.delete(key);
        }
      }
      for (const key of Array.from(this.assetStates.keys())) {
        if (!key.startsWith(`${project.id}:`)) {
          this.assetStates.delete(key);
        }
      }
      this.refBufferCache.clear();
      this.trackNodes.forEach((nodes) => {
        nodes.input.disconnect();
        nodes.gain.disconnect();
        nodes.panner.disconnect();
      });
      this.trackNodes.clear();
      this.emitAssetStates();
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

  invalidateAssetBuffer(projectId: string, assetId: string): void {
    const key = `${projectId}:${assetId}`;
    this.audioBuffers.delete(key);
    this.pendingDecodes.delete(key);
    this.assetStates.delete(key);
    this.emitAssetStates();
  }

  async loadAssetBuffer(projectId: string, assetId: string, forceReload = false): Promise<AudioBuffer> {
    const key = `${projectId}:${assetId}`;
    if (forceReload) {
      this.audioBuffers.delete(key);
      this.pendingDecodes.delete(key);
    }
    const cached = this.audioBuffers.get(key);
    if (cached) return cached;
    const inflight = this.pendingDecodes.get(key);
    if (inflight) return inflight;

    this.assetStates.set(key, { status: "loading" });
    this.emitAssetStates();

    const promise = (async () => {
      try {
        const ctx = this.ensureContext();
        const url = `${dawApi.assetFileUrl(projectId, assetId)}${forceReload ? `?t=${Date.now()}` : ""}`;
        const resp = await fetch(url);
        if (!resp.ok) {
          throw new Error(
            resp.status === 404 ? "Audio file missing on disk" : `HTTP ${resp.status} loading audio`
          );
        }
        const arr = await resp.arrayBuffer();
        const decoded = await ctx.decodeAudioData(arr);
        this.audioBuffers.set(key, decoded);
        this.assetStates.set(key, { status: "ready" });
        this.pendingDecodes.delete(key);
        this.emitAssetStates();
        return decoded;
      } catch (err) {
        // Never leave failed promises cached!
        this.pendingDecodes.delete(key);
        this.audioBuffers.delete(key);
        const msg = err instanceof Error ? err.message : "Audio decode failed";
        this.assetStates.set(key, { status: "error", error: msg });
        this.emitAssetStates();
        throw err;
      }
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
      return loop.startBeats + (((rawBeats - loop.startBeats) % loopLen) + loopLen) % loopLen;
    }

    if (rawBeats >= this.project.lengthBeats) {
      return this.project.lengthBeats;
    }
    return rawBeats;
  }

  async play(fromBeats?: number): Promise<void> {
    if (!this.project) return;
    this.stopReferencePreview();
    const myToken = ++this.playToken;
    const targetProject = this.project;

    const ctx = this.ensureContext();
    if (ctx.state === "suspended") {
      await ctx.resume();
    }
    await this.preloadProjectAudio(targetProject);

    // Abort if stop/pause/another play or project switch happened while decoding
    if (myToken !== this.playToken || this.project?.id !== targetProject.id) {
      return;
    }

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
    this.playToken++;
    if (!this.playing) return;
    this.playheadBeats = this.getPlayheadBeats();
    this.clearPlayback();
    this.playing = false;
  }

  stop(): void {
    this.playToken++;
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

  resyncActivePlayback(): void {
    if (this.playing) {
      const nowBeats = this.getPlayheadBeats();
      this.restartFromBeats(nowBeats);
    }
  }

  auditionMidiNote(pitch: number, velocity = 100, durationSec = 0.28, instrumentRef?: string | null): void {
    const ctx = this.ensureContext();
    if (this.masterGain) {
      scheduleSynthVoice(
        ctx,
        this.masterGain,
        pitch,
        velocity,
        ctx.currentTime + 0.005,
        durationSec,
        0.9,
        false,
        instrumentRef
      );
    }
  }

  // Standalone Reference / Take Level-Matched Audition (never mixed into project export)
  async playReferencePreview(url: string, startSec = 0, gainDb = 0): Promise<void> {
    this.pause();
    this.stopReferencePreview();
    const ctx = this.ensureContext();
    if (ctx.state === "suspended") await ctx.resume();

    let buf = this.refBufferCache.get(url);
    if (!buf) {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status} loading preview audio`);
      buf = await ctx.decodeAudioData(await resp.arrayBuffer());
      this.refBufferCache.set(url, buf);
    }

    const offset = Math.max(0, Math.min(buf.duration - 0.05, startSec));
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const previewGain = ctx.createGain();
    previewGain.gain.value = dbToLinear(Math.max(-18, Math.min(12, gainDb)));
    src.connect(previewGain);
    previewGain.connect(this.masterGain!);
    src.start(ctx.currentTime + 0.01, offset);
    this.refSource = src;
    this.refPlayingKey = url;
    this.refStartAudioTime = ctx.currentTime + 0.01;
    this.refStartOffsetSec = offset;
    this.refDurationSec = buf.duration;
    src.onended = () => {
      previewGain.disconnect();
      if (this.refSource === src) {
        this.refSource = null;
        this.refPlayingKey = null;
      }
    };
  }

  stopReferencePreview(): void {
    if (this.refSource) {
      try {
        this.refSource.stop();
        this.refSource.disconnect();
      } catch {
        // already stopped
      }
      this.refSource = null;
      this.refPlayingKey = null;
    }
  }

  getReferencePreviewState(): { playingUrl: string | null; positionSec: number; durationSec: number } {
    if (!this.refSource || !this.ctx) {
      return { playingUrl: null, positionSec: 0, durationSec: this.refDurationSec };
    }
    const elapsed = Math.max(0, this.ctx.currentTime - this.refStartAudioTime);
    return {
      playingUrl: this.refPlayingKey,
      positionSec: Math.min(this.refDurationSec, this.refStartOffsetSec + elapsed),
      durationSec: this.refDurationSec,
    };
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
    this.chasedCycleKeys.clear();
  }

  private restartFromBeats(startBeats: number): void {
    if (!this.project) return;
    const ctx = this.ensureContext();
    this.clearPlayback();
    this.syncMixerNodes(this.project);

    this.playing = true;
    this.playheadBeats = startBeats;
    this.anchorAudioTime = ctx.currentTime + 0.025;
    this.anchorSongBeats = startBeats;
    this.scheduledUntilSongSec = 0;

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

    if (!loop.enabled && anchorSongSec + elapsedSinceAnchor >= songLengthSec) {
      this.playheadBeats = project.lengthBeats;
      this.clearPlayback();
      this.playing = false;
      return;
    }

    const slices = this.computeSongSlices(windowStartRelSec, windowEndRelSec, project);
    for (const slice of slices) {
      this.scheduleSlice(
        project,
        slice.audioStartTime,
        slice.songStartSec,
        slice.songEndSec,
        slice.boundaryLimitSec,
        slice.cycleIndex
      );
    }

    this.scheduledUntilSongSec = windowEndRelSec;
  }

  private computeSongSlices(
    relStartSec: number,
    relEndSec: number,
    project: Project
  ): Array<{
    audioStartTime: number;
    songStartSec: number;
    songEndSec: number;
    boundaryLimitSec: number;
    cycleIndex: number;
  }> {
    const slices: Array<{
      audioStartTime: number;
      songStartSec: number;
      songEndSec: number;
      boundaryLimitSec: number;
      cycleIndex: number;
    }> = [];
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
          boundaryLimitSec: loopEndSec,
          cycleIndex,
        });
        cursorRel += segDur;
      } else {
        const limitSec =
          loop.enabled && loopLenSec > 0.05 && rawSongSec < loopStartSec ? loopStartSec : songLenSec;
        const remaining = limitSec - rawSongSec;
        if (remaining <= 1e-6) break;
        const segDur = Math.min(relEndSec - cursorRel, remaining);
        slices.push({
          audioStartTime: this.anchorAudioTime + cursorRel,
          songStartSec: rawSongSec,
          songEndSec: rawSongSec + segDur,
          boundaryLimitSec: limitSec,
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
    boundaryLimitSec: number,
    cycleIndex: number
  ): void {
    if (!this.ctx) return;

    // Allow MIDI Chase once per playback anchor or loop cycle entry!
    const cycleChaseKey = `chase:${cycleIndex}`;
    const allowChase = !this.chasedCycleKeys.has(cycleChaseKey);
    if (allowChase) {
      this.chasedCycleKeys.add(cycleChaseKey);
    }

    for (const track of project.tracks) {
      const nodes = this.ensureTrackNode(track);
      for (const clip of track.clips) {
        if (clip.type === "audio" && clip.assetId) {
          const buf = this.audioBuffers.get(`${project.id}:${clip.assetId}`);
          if (!buf) continue;

          const seg = computeAudioClipSegment(
            clip,
            project.bpm,
            buf.duration,
            songStartSec,
            songEndSec,
            boundaryLimitSec
          );
          if (!seg) continue;

          const scheduleKey = `${clip.id}:${cycleIndex}`;
          if (this.scheduledAudioClipKeys.has(scheduleKey)) continue;
          this.scheduledAudioClipKeys.add(scheduleKey);

          const when = audioStartTime + Math.max(0, seg.songStartSec - songStartSec);
          const src = this.ctx.createBufferSource();
          src.buffer = buf;

          const clipGain = this.ctx.createGain();
          clipGain.gain.setValueAtTime(0.0001, when);
          clipGain.gain.linearRampToValueAtTime(seg.clipGainLinear, when + 0.003);
          if (seg.playDurSec > 0.008) {
            clipGain.gain.setValueAtTime(seg.clipGainLinear, when + seg.playDurSec - 0.004);
            clipGain.gain.linearRampToValueAtTime(0.0001, when + seg.playDurSec);
          }

          src.connect(clipGain);
          clipGain.connect(nodes.input);

          if (seg.loop) {
            src.loop = true;
            src.loopStart = seg.loopStartSec;
            src.loopEnd = seg.loopEndSec;
          }
          src.start(when, seg.sourceStartSec, seg.playDurSec);

          this.activeSources.add(src);
          src.onended = () => {
            this.activeSources.delete(src);
            src.disconnect();
            clipGain.disconnect();
          };
        } else if (clip.type === "midi") {
          const events = collectMidiEventsForWindow(
            clip,
            project.bpm,
            songStartSec,
            songEndSec,
            boundaryLimitSec,
            allowChase,
            cycleIndex
          );
          for (const ev of events) {
            if (this.scheduledMidiNoteKeys.has(ev.key)) continue;
            this.scheduledMidiNoteKeys.add(ev.key);
            const when = audioStartTime + Math.max(0, ev.songStartSec - songStartSec);
            const oscs = scheduleSynthVoice(
              this.ctx,
              nodes.input,
              ev.pitch,
              ev.velocity,
              when,
              ev.durationSec,
              ev.clipGainLinear,
              ev.chased,
              track.instrumentRef
            );
            for (const osc of oscs) {
              this.activeSources.add(osc);
              osc.onended = () => this.activeSources.delete(osc);
            }
          }
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
