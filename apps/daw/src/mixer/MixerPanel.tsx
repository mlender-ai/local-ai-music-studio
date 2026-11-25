import React from "react";
import { Plus, Trash2 } from "lucide-react";
import { makeClientId } from "../commands/executor";
import { useDaw } from "../commands/store";
import { useI18n } from "../i18n";
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
  const { t } = useI18n();
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

  const buses = project.buses ?? [];
  const masterPeakDb = linearToDb(Math.max(masterMeter.peakL, masterMeter.peakR));

  const handleAddReverbBus = () => {
    const busNum = buses.length + 1;
    dispatch({
      type: "bus.add",
      payload: {
        id: makeClientId("bus"),
        name: busNum === 1 ? "Room Reverb" : `Aux Bus ${busNum}`,
        kind: "return",
        effects: [
          {
            id: makeClientId("fx"),
            type: "reverb",
            name: "Room Reverb",
            nameKo: "룸 리버브",
            enabled: true,
            bypass: false,
            wetDry: 1.0,
            parameters: { mode: "studio_room", decaySec: 1.3, preDelayMs: 16, damping: 0.48, mix: 1.0 },
          },
        ],
      },
    });
  };

  return (
    <div className="mixer-strip-list" data-testid="mixer-panel">
      {project.tracks.map((track) => {
        const meter = trackMeters[track.id] ?? ZERO_METER;
        const peakDb = linearToDb(Math.max(meter.peakL, meter.peakR));
        const selected = selection.selectedTrackId === track.id;
        const fxCount = (track.effects ?? []).filter((e) => !e.bypass).length;
        const isFrozen = Boolean(track.freezeState?.frozen);

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
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
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
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 3 }}>
                <span className="track-type-label">{track.type === "stem" ? "STEM · est." : track.type}</span>
                <div style={{ display: "flex", gap: 2 }}>
                  {fxCount > 0 && (
                    <span
                      style={{
                        fontSize: 8.5,
                        padding: "0 3px",
                        borderRadius: 2,
                        background: "rgba(133,196,155,0.16)",
                        color: "#9fd4b2",
                      }}
                    >
                      {t("mixer.fxBadge", { count: fxCount })}
                    </span>
                  )}
                  {isFrozen && (
                    <span
                      style={{
                        fontSize: 8.5,
                        padding: "0 3px",
                        borderRadius: 2,
                        background: "rgba(123,167,201,0.2)",
                        color: "#9fc5e2",
                      }}
                      title="Frozen Studio WAV"
                    >
                      ❄
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Compact Send Knob when Return Buses exist */}
            {buses.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                {buses.slice(0, 2).map((bus) => {
                  const send = (track.sends ?? []).find((s) => s.busId === bus.id);
                  const sendDb = send ? send.levelDb : -60;
                  return (
                    <div key={bus.id} style={{ display: "flex", alignItems: "center", gap: 3 }}>
                      <span
                        style={{
                          fontSize: 8.5,
                          color: "var(--text-muted)",
                          width: 34,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        title={`Send → ${bus.name}`}
                      >
                        {bus.name.slice(0, 6)}
                      </span>
                      <input
                        type="range"
                        className="mini-slider"
                        style={{ flex: 1, minWidth: 28 }}
                        min={-60}
                        max={0}
                        step={1}
                        value={sendDb}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value);
                          if (val <= -59) {
                            dispatch({ type: "send.remove", payload: { trackId: track.id, busId: bus.id } });
                          } else {
                            dispatch({
                              type: "send.set",
                              payload: { trackId: track.id, busId: bus.id, levelDb: val },
                            });
                          }
                        }}
                      />
                    </div>
                  );
                })}
              </div>
            )}

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

      {/* Return / Group Bus Channel Strips */}
      {buses.map((bus) => (
        <div
          key={bus.id}
          className="mixer-channel"
          style={{
            borderTop: "3px solid #6b85a8",
            background: "rgba(32, 38, 48, 0.72)",
          }}
          data-testid={`mixer-bus-${bus.id}`}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontWeight: 600,
                  fontSize: 11,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  color: "#bcd1ea",
                }}
              >
                {bus.name}
              </div>
              <div className="track-type-label">{bus.kind.toUpperCase()} BUS</div>
            </div>
            <button
              className="icon-btn"
              title="Remove Bus"
              onClick={() => dispatch({ type: "bus.remove", payload: { busId: bus.id } })}
            >
              <Trash2 size={10} />
            </button>
          </div>

          <div style={{ fontSize: 9, color: "#9fc5e2" }}>
            {t("mixer.fxBadge", { count: (bus.effects ?? []).length })}
          </div>

          <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
            <button
              className={`ms-btn ${bus.mute ? "mute-on" : ""}`}
              onClick={() => dispatch({ type: "bus.setMute", payload: { busId: bus.id, mute: !bus.mute } })}
            >
              M
            </button>
            <button
              className={`ms-btn ${bus.solo ? "solo-on" : ""}`}
              onClick={() => dispatch({ type: "bus.setSolo", payload: { busId: bus.id, solo: !bus.solo } })}
            >
              S
            </button>
          </div>

          <div className="mixer-fader-wrap">
            <input
              type="range"
              className="vertical-fader"
              min={-60}
              max={6}
              step={0.5}
              value={bus.gainDb}
              aria-label={`${bus.name} gain`}
              onPointerDown={beginTransaction}
              onPointerUp={commitTransaction}
              onChange={(e) =>
                dispatch({
                  type: "bus.setGain",
                  payload: { busId: bus.id, gainDb: parseFloat(e.target.value) },
                })
              }
            />
            <StereoMeterBar meter={ZERO_METER} />
          </div>

          <div
            className="mono"
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 10,
              color: "#bcd1ea",
              borderTop: "1px solid var(--border-subtle)",
              paddingTop: 4,
            }}
          >
            <span>{formatDb(bus.gainDb)}</span>
            <span>BUS</span>
          </div>
        </div>
      ))}

      {/* Compact + Return Bus Action Column */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          padding: "0 4px",
          flexShrink: 0,
        }}
      >
        <button
          onClick={handleAddReverbBus}
          data-testid="btn-mixer-add-bus"
          style={{
            fontSize: 10,
            padding: "6px 8px",
            minWidth: 52,
            whiteSpace: "nowrap",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 4,
            borderStyle: "dashed",
            color: "var(--text-secondary)",
          }}
          title={t("deviceRack.addReverbBus")}
        >
          <Plus size={12} />
          <span>{t("mixer.addBus")}</span>
        </button>
      </div>

      {/* Master Channel Strip */}
      <div className="mixer-channel master" style={{ borderTop: "3px solid var(--accent-playhead)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 11 }}>{t("mixer.master")}</div>
            <div className="track-type-label">{t("mixer.stereoOut")}</div>
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
