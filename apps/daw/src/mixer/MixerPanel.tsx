import React from "react";
import { useDaw } from "../commands/store";
import { formatDb, formatPan, linearToDb } from "../project/time";
import type { TrackMeterLevel } from "../project/types";

function StereoMeterBar({ meter }: { meter: TrackMeterLevel }) {
  const toPct = (lin: number) => {
    const db = linearToDb(lin);
    return Math.max(0, Math.min(100, ((db + 60) / 60) * 100));
  };
  const pctL = toPct(meter.peakL);
  const pctR = toPct(meter.peakR);
  const rmsL = toPct(meter.rmsL);
  const rmsR = toPct(meter.rmsR);

  const colorFor = (pct: number) =>
    pct > 94 ? "var(--accent-danger)" : pct > 78 ? "var(--accent-playhead)" : "var(--accent-play)";

  return (
    <div style={{ display: "flex", gap: 3, height: "100%", minHeight: 44, alignItems: "flex-end" }}>
      {[
        { peak: pctL, rms: rmsL },
        { peak: pctR, rms: rmsR },
      ].map((ch, idx) => (
        <div
          key={idx}
          style={{
            width: 7,
            height: "100%",
            background: "#111317",
            border: "1px solid var(--border-subtle)",
            borderRadius: 2,
            position: "relative",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              position: "absolute",
              bottom: 0,
              left: 0,
              right: 0,
              height: `${ch.rms}%`,
              background: colorFor(ch.peak),
              opacity: 0.45,
            }}
          />
          <div
            style={{
              position: "absolute",
              bottom: 0,
              left: 0,
              right: 0,
              height: `${ch.peak}%`,
              background: colorFor(ch.peak),
              opacity: 0.85,
            }}
          />
        </div>
      ))}
    </div>
  );
}

const ZERO_METER: TrackMeterLevel = { peakL: 0, peakR: 0, rmsL: 0, rmsR: 0, clipping: false };

export function MixerPanel() {
  const {
    project,
    selection,
    setSelection,
    trackMeters,
    masterMeter,
    dispatch,
    beginTransaction,
    commitTransaction,
    resetMasterClip,
  } = useDaw();

  if (!project) return null;

  const masterPeakDb = linearToDb(Math.max(masterMeter.peakL, masterMeter.peakR));

  return (
    <div className="mixer-strip-list" data-testid="mixer-panel">
      {project.tracks.map((track) => {
        const meter = trackMeters[track.id] ?? ZERO_METER;
        const peakDb = linearToDb(Math.max(meter.peakL, meter.peakR));
        const selected = selection.selectedTrackId === track.id;

        return (
          <div
            key={track.id}
            className="mixer-channel"
            style={{
              borderColor: selected ? "var(--accent-playhead)" : undefined,
              borderTop: `3px solid ${track.color}`,
            }}
            onClick={() => setSelection((prev) => ({ ...prev, selectedTrackId: track.id }))}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <div
                style={{
                  fontWeight: 600,
                  fontSize: 11,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {track.name}
              </div>
              <div className="track-type-label">{track.type === "stem" ? "STEM · est." : track.type}</div>
            </div>

            {/* Pan */}
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)" }}>
                <span>Pan</span>
                <span className="mono">{formatPan(track.pan)}</span>
              </div>
              <input
                type="range"
                className="mini-slider"
                min={-1}
                max={1}
                step={0.02}
                value={track.pan}
                onPointerDown={beginTransaction}
                onPointerUp={commitTransaction}
                onChange={(e) =>
                  dispatch({
                    type: "track.setPan",
                    payload: { trackId: track.id, pan: parseFloat(e.target.value) },
                  })
                }
              />
            </div>

            {/* Mute / Solo */}
            <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
              <button
                className={`ms-btn ${track.mute ? "mute-on" : ""}`}
                onClick={(e) => {
                  e.stopPropagation();
                  dispatch({ type: "track.setMute", payload: { trackId: track.id, mute: !track.mute } });
                }}
              >
                M
              </button>
              <button
                className={`ms-btn ${track.solo ? "solo-on" : ""}`}
                onClick={(e) => {
                  e.stopPropagation();
                  dispatch({ type: "track.setSolo", payload: { trackId: track.id, solo: !track.solo } });
                }}
              >
                S
              </button>
            </div>

            {/* Vertical Fader + Live Signal Meter */}
            <div className="mixer-fader-wrap">
              <input
                type="range"
                className="vertical-fader"
                min={-60}
                max={6}
                step={0.5}
                value={track.gainDb}
                aria-label={`${track.name} gain`}
                onPointerDown={beginTransaction}
                onPointerUp={commitTransaction}
                onChange={(e) =>
                  dispatch({
                    type: "track.setGain",
                    payload: { trackId: track.id, gainDb: parseFloat(e.target.value) },
                  })
                }
              />
              <StereoMeterBar meter={meter} />
            </div>

            <div
              className="mono"
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 10,
                color: "var(--text-secondary)",
                borderTop: "1px solid var(--border-subtle)",
                paddingTop: 4,
              }}
            >
              <span>{formatDb(track.gainDb)}</span>
              <span style={{ color: peakDb > -1 ? "var(--accent-danger)" : "var(--text-muted)" }}>
                {peakDb <= -59 ? "-∞" : peakDb.toFixed(0)}
              </span>
            </div>
          </div>
        );
      })}

      {/* Master Channel Strip */}
      <div className="mixer-channel master" style={{ borderTop: "3px solid var(--accent-playhead)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 11 }}>MASTER</div>
            <div className="track-type-label">STEREO OUT</div>
          </div>
          <button
            onClick={resetMasterClip}
            disabled={!masterMeter.clipping}
            style={{
              padding: "1px 5px",
              fontSize: 9,
              fontWeight: 700,
              background: masterMeter.clipping ? "var(--accent-danger)" : "var(--bg-input)",
              borderColor: masterMeter.clipping ? "#f07575" : "var(--border-subtle)",
              color: masterMeter.clipping ? "#fff" : "var(--text-muted)",
              opacity: 1,
            }}
          >
            CLIP
          </button>
        </div>

        <div className="mixer-fader-wrap">
          <input
            type="range"
            className="vertical-fader"
            min={-60}
            max={6}
            step={0.5}
            value={project.masterGainDb}
            aria-label="Master gain"
            onPointerDown={beginTransaction}
            onPointerUp={commitTransaction}
            onChange={(e) =>
              dispatch({
                type: "project.setMasterGain",
                payload: { gainDb: parseFloat(e.target.value) },
              })
            }
          />
          <StereoMeterBar meter={masterMeter} />
        </div>

        <div
          className="mono"
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 10,
            color: "var(--text-primary)",
            borderTop: "1px solid var(--border-subtle)",
            paddingTop: 4,
          }}
        >
          <span>{formatDb(project.masterGainDb)}</span>
          <span>{masterPeakDb <= -59 ? "-∞" : `${masterPeakDb.toFixed(1)}`}</span>
        </div>
      </div>
    </div>
  );
}
