import { describe, expect, it } from "vitest";
import { encodeStereoWav24 } from "../src/audio/wavEncoder";
import { isTrackAudible } from "../src/audio/audioEngine";
import { executeCommand } from "../src/commands/executor";
import {
  beatsToSeconds,
  beatsToTicks,
  dbToLinear,
  formatBarBeatTick,
  formatBarRange,
  midiPitchToName,
  secondsToBeats,
  snapBeats,
} from "../src/project/time";
import type { Project, Track } from "../src/project/types";

function makeSampleProject(): Project {
  return {
    id: "proj_test",
    schemaVersion: "1.0.0",
    name: "Test Session",
    bpm: 120,
    timeSignature: { numerator: 4, denominator: 4 },
    ppq: 480,
    sampleRate: 48000,
    lengthBeats: 64,
    masterGainDb: 0,
    loopRegion: { enabled: false, startBeats: 0, endBeats: 16 },
    sections: [{ id: "sec_1", name: "INTRO", startBeats: 0, endBeats: 16, color: "#49505e" }],
    assets: [],
    tracks: [
      {
        id: "trk_a",
        name: "Drums",
        type: "audio",
        color: "#6a997c",
        gainDb: 0,
        pan: 0,
        mute: false,
        solo: false,
        instrumentRef: null,
        effects: [],
        clips: [
          {
            id: "clp_a",
            name: "Drums 1",
            type: "audio",
            assetId: "ast_1",
            timelineStartBeats: 0,
            durationBeats: 8,
            sourceOffsetSec: 0,
            sourceDurationSec: 4,
            loop: false,
            loopLengthSec: 4,
            loopLengthBeats: null,
            gainDb: 0,
            notes: [],
          },
        ],
      },
      {
        id: "trk_m",
        name: "Synth",
        type: "midi",
        color: "#648ea8",
        gainDb: 0,
        pan: 0,
        mute: false,
        solo: false,
        instrumentRef: "basic-poly-synth",
        effects: [],
        clips: [
          {
            id: "clp_m",
            name: "Synth 1",
            type: "midi",
            assetId: null,
            timelineStartBeats: 4,
            durationBeats: 8,
            sourceOffsetSec: 0,
            sourceDurationSec: 0,
            loop: false,
            loopLengthSec: null,
            loopLengthBeats: 8,
            gainDb: 0,
            notes: [
              { id: "n1", pitch: 60, velocity: 100, startBeat: 0, durationBeats: 2 },
              { id: "n2", pitch: 67, velocity: 90, startBeat: 3, durationBeats: 2 },
            ],
          },
        ],
      },
    ],
    notes: "",
    createdAt: "2026-11-24T00:00:00Z",
    updatedAt: "2026-11-24T00:00:00Z",
  };
}

describe("Time & unit conversions", () => {
  it("converts beats, seconds, ticks, and bar formatting accurately", () => {
    expect(beatsToSeconds(4, 120)).toBeCloseTo(2.0, 6);
    expect(secondsToBeats(2.0, 120)).toBeCloseTo(4.0, 6);
    expect(beatsToTicks(1.5, 480)).toBe(720);
    expect(formatBarBeatTick(0, { numerator: 4, denominator: 4 })).toBe("001.1.1");
    expect(formatBarBeatTick(32, { numerator: 4, denominator: 4 })).toBe("009.1.1");
    expect(formatBarRange(16, 32, { numerator: 4, denominator: 4 })).toBe("Bars 5–8");
    expect(snapBeats(2.38, 0.5, true)).toBe(2.5);
    expect(midiPitchToName(60)).toBe("C4");
    expect(dbToLinear(-60)).toBe(0);
    expect(dbToLinear(0)).toBeCloseTo(1, 6);
  });
});

describe("Shared Command System (Frontend Executor)", () => {
  it("splits audio and MIDI clips cleanly and preserves source offsets", () => {
    const proj = makeSampleProject();
    const afterAudioSplit = executeCommand(proj, {
      type: "clip.split",
      payload: { clipId: "clp_a", splitBeat: 4, rightClipId: "clp_a_r" },
    });
    const audioClips = afterAudioSplit.tracks[0].clips;
    expect(audioClips).toHaveLength(2);
    expect(audioClips[0].durationBeats).toBe(4);
    expect(audioClips[1].timelineStartBeats).toBe(4);
    expect(audioClips[1].durationBeats).toBe(4);
    // At 120 BPM, 4 beats = 2.0 seconds offset
    expect(audioClips[1].sourceOffsetSec).toBeCloseTo(2.0, 5);

    const afterMidiSplit = executeCommand(afterAudioSplit, {
      type: "clip.split",
      payload: { clipId: "clp_m", splitBeat: 8, rightClipId: "clp_m_r" },
    });
    const midiClips = afterMidiSplit.tracks[1].clips;
    expect(midiClips).toHaveLength(2);
    expect(midiClips[0].notes).toHaveLength(2); // n2 split across boundary at relBeat 4
    expect(midiClips[0].notes[1].durationBeats).toBeCloseTo(1.0, 5);
    expect(midiClips[1].notes).toHaveLength(1);
    expect(midiClips[1].notes[0].startBeat).toBe(0);
    expect(midiClips[1].notes[0].durationBeats).toBeCloseTo(1.0, 5);
  });

  it("edits MIDI notes and enforces track type safety on clip moves", () => {
    let proj = makeSampleProject();
    proj = executeCommand(proj, {
      type: "midi.addNote",
      payload: { clipId: "clp_m", note: { id: "n3", pitch: 72, velocity: 110, startBeat: 1, durationBeats: 1 } },
    });
    expect(proj.tracks[1].clips[0].notes).toHaveLength(3);

    proj = executeCommand(proj, {
      type: "midi.moveNote",
      payload: { clipId: "clp_m", noteId: "n3", pitch: 74, startBeat: 2 },
    });
    const moved = proj.tracks[1].clips[0].notes.find((n) => n.id === "n3");
    expect(moved?.pitch).toBe(74);
    expect(moved?.startBeat).toBe(2);

    expect(() =>
      executeCommand(proj, {
        type: "clip.move",
        payload: { clipId: "clp_m", timelineStartBeats: 0, targetTrackId: "trk_a" },
      })
    ).toThrow(/Cannot move MIDI clip/);
  });
});

describe("Mute/Solo logic & 24-bit Stereo WAV encoder", () => {
  it("resolves solo and mute precedence accurately", () => {
    const tracks: Track[] = [
      { ...makeSampleProject().tracks[0], id: "t1", mute: false, solo: false },
      { ...makeSampleProject().tracks[0], id: "t2", mute: false, solo: true },
      { ...makeSampleProject().tracks[0], id: "t3", mute: true, solo: true },
    ];
    expect(isTrackAudible(tracks[0], tracks)).toBe(false);
    expect(isTrackAudible(tracks[1], tracks)).toBe(true);
    expect(isTrackAudible(tracks[2], tracks)).toBe(false);
  });

  it("encodes valid RIFF/WAVE 24-bit stereo headers and PCM frames", () => {
    const left = new Float32Array([0, 0.5, -0.5, 1.0]);
    const right = new Float32Array([0, -0.25, 0.25, -1.0]);
    const buf = encodeStereoWav24(left, right, 48000);
    const view = new DataView(buf);
    expect(String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3))).toBe("RIFF");
    expect(String.fromCharCode(view.getUint8(8), view.getUint8(9), view.getUint8(10), view.getUint8(11))).toBe("WAVE");
    expect(view.getUint16(22, true)).toBe(2); // Stereo
    expect(view.getUint32(24, true)).toBe(48000); // 48 kHz
    expect(view.getUint16(34, true)).toBe(24); // 24-bit
    expect(buf.byteLength).toBe(44 + 4 * 2 * 3);
  });
});
