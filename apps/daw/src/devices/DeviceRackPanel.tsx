import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Play,
  Plus,
  Power,
  Snowflake,
  Sparkles,
  Trash2,
  Waves,
} from "lucide-react";
import { makeClientId } from "../commands/executor";
import { useDaw } from "../commands/store";
import { useI18n } from "../i18n";
import { dawApi } from "../project/api";
import type { EffectSlot, FxCatalogEntry, InstrumentCatalogEntry } from "../project/types";

interface EqBand {
  id: string;
  type: string;
  freqHz: number;
  gainDb: number;
  q: number;
  enabled: boolean;
}

/** Exact analytical RBJ biquad magnitude curve (dB) matching backend engine/fx/eq.py 1:1. */
function computeAnalyticalEqSvgPath(bands: EqBand[], width = 188, height = 66): string {
  const sr = 48000;
  const nPts = 56;
  const minLog = Math.log10(25);
  const maxLog = Math.log10(18500);
  const pts: string[] = [];

  for (let i = 0; i < nPts; i++) {
    const frac = i / (nPts - 1);
    const f = Math.pow(10, minLog + frac * (maxLog - minLog));
    const w = (2 * Math.PI * f) / sr;
    const cosW = Math.cos(w);
    const sinW = Math.sin(w);
    const cos2W = Math.cos(2 * w);
    const sin2W = Math.sin(2 * w);

    let totalDb = 0;
    for (const band of bands) {
      if (!band.enabled) continue;
      const f0 = Math.max(20, Math.min(20000, Number(band.freqHz) || 1000));
      const gdb = Number(band.gainDb) || 0;
      const q = Math.max(0.2, Math.min(12, Number(band.q) || 0.9));
      if ((band.type === "peak" || band.type === "low_shelf" || band.type === "high_shelf") && Math.abs(gdb) < 0.05) {
        continue;
      }
      const w0 = (2 * Math.PI * f0) / sr;
      const cw0 = Math.cos(w0);
      const sw0 = Math.sin(w0);
      const alpha = sw0 / (2 * q);
      const A = Math.pow(10, gdb / 40);
      let b0 = 1, b1 = 0, b2 = 0, a0 = 1, a1 = 0, a2 = 0;

      if (band.type === "highpass") {
        b0 = (1 + cw0) / 2; b1 = -(1 + cw0); b2 = (1 + cw0) / 2;
        a0 = 1 + alpha; a1 = -2 * cw0; a2 = 1 - alpha;
      } else if (band.type === "lowpass") {
        b0 = (1 - cw0) / 2; b1 = 1 - cw0; b2 = (1 - cw0) / 2;
        a0 = 1 + alpha; a1 = -2 * cw0; a2 = 1 - alpha;
      } else if (band.type === "low_shelf") {
        const sq = 2 * Math.sqrt(A) * alpha;
        b0 = A * (A + 1 - (A - 1) * cw0 + sq);
        b1 = 2 * A * (A - 1 - (A + 1) * cw0);
        b2 = A * (A + 1 - (A - 1) * cw0 - sq);
        a0 = A + 1 + (A - 1) * cw0 + sq;
        a1 = -2 * (A - 1 + (A + 1) * cw0);
        a2 = A + 1 + (A - 1) * cw0 - sq;
      } else if (band.type === "high_shelf") {
        const sq = 2 * Math.sqrt(A) * alpha;
        b0 = A * (A + 1 + (A - 1) * cw0 + sq);
        b1 = -2 * A * (A - 1 + (A + 1) * cw0);
        b2 = A * (A + 1 + (A - 1) * cw0 - sq);
        a0 = A + 1 - (A - 1) * cw0 + sq;
        a1 = 2 * (A - 1 - (A + 1) * cw0);
        a2 = A + 1 - (A - 1) * cw0 - sq;
      } else {
        b0 = 1 + alpha * A; b1 = -2 * cw0; b2 = 1 - alpha * A;
        a0 = 1 + alpha / A; a1 = -2 * cw0; a2 = 1 - alpha / A;
      }

      const nr = b0 + b1 * cosW + b2 * cos2W;
      const ni = -(b1 * sinW + b2 * sin2W);
      const dr = a0 + a1 * cosW + a2 * cos2W;
      const di = -(a1 * sinW + a2 * sin2W);
      const mag = Math.sqrt((nr * nr + ni * ni) / Math.max(1e-12, dr * dr + di * di));
      totalDb += 20 * Math.log10(Math.max(1e-4, mag));
    }

    const clamped = Math.max(-18, Math.min(18, totalDb));
    const x = frac * width;
    const y = height * 0.5 - (clamped / 18) * (height * 0.44);
    pts.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return pts.join(" ");
}

function CompressorTransferSvg({ thresholdDb, ratio }: { thresholdDb: number; ratio: number }) {
  const w = 132;
  const h = 44;
  const mapX = (db: number) => ((db + 48) / 48) * w;
  const mapY = (db: number) => h - ((db + 48) / 48) * h;
  const tx = mapX(Math.max(-48, Math.min(0, thresholdDb)));
  const ty = mapY(Math.max(-48, Math.min(0, thresholdDb)));
  const outAt0 = thresholdDb + (0 - thresholdDb) / Math.max(1, ratio);
  const endY = mapY(Math.max(-48, Math.min(0, outAt0)));
  return (
    <svg width={w} height={h} style={{ background: "#14171c", borderRadius: 4, border: "1px solid var(--border-subtle)" }}>
      <line x1={0} y1={h} x2={w} y2={0} stroke="#2e3542" strokeDasharray="3 3" strokeWidth={1} />
      <polyline points={`0,${h} ${tx.toFixed(1)},${ty.toFixed(1)} ${w},${endY.toFixed(1)}`} fill="none" stroke="#85c49b" strokeWidth={2} />
      <circle cx={tx} cy={ty} r={3} fill="#e8c37a" />
    </svg>
  );
}

function ReverbDepthSvg({ decaySec, preDelayMs, wetDry }: { decaySec: number; preDelayMs: number; wetDry: number }) {
  const w = 136;
  const h = 58;
  const preX = Math.min(28, (preDelayMs / 100) * 26);
  const scale = Math.min(1, decaySec / 4.2);
  return (
    <svg width={w} height={h} style={{ background: "#14171c", borderRadius: 4, border: "1px solid var(--border-subtle)" }}>
      {[0, 1, 2, 3].map((idx) => {
        const bw = 30 + idx * (16 + scale * 12);
        const bh = 22 + idx * 7;
        const x = 8 + preX + idx * 14;
        const y = h - bh - 6 - idx * 2;
        return (
          <rect
            key={idx}
            x={Math.min(w - 18, x)}
            y={Math.max(4, y)}
            width={Math.min(w - x - 4, bw)}
            height={bh}
            rx={3}
            fill="none"
            stroke="#6ea3c9"
            strokeOpacity={Math.max(0.2, 0.85 - idx * 0.18) * (0.4 + 0.6 * wetDry)}
            strokeWidth={1.3}
          />
        );
      })}
    </svg>
  );
}

export function DeviceRackPanel() {
  const { t, locale } = useI18n();
  const {
    project,
    selectedTrack,
    dispatch,
    saveCurrentProject,
    applyExternalProjectUpdate,
    showToast,
  } = useDaw();

  const [instruments, setInstruments] = useState<InstrumentCatalogEntry[]>([]);
  const [fxCatalog, setFxCatalog] = useState<FxCatalogEntry[]>([]);
  const [addFxChoice, setAddFxChoice] = useState("parametric_eq");
  const [isFreezing, setIsFreezing] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [diagnosisText, setDiagnosisText] = useState<string | null>(null);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([dawApi.getInstrumentCatalog(), dawApi.getFxCatalog()])
      .then(([instRes, fxRes]) => {
        if (!active) return;
        setInstruments(instRes.instruments ?? []);
        setFxCatalog(fxRes.effects ?? []);
      })
      .catch(() => {
        // graceful offline
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setDiagnosisText(null);
  }, [selectedTrack?.id]);

  const activeInstrument = useMemo(
    () => instruments.find((i) => i.instrumentId === selectedTrack?.instrumentRef) ?? null,
    [instruments, selectedTrack?.instrumentRef]
  );

  if (!project) return null;

  if (!selectedTrack) {
    return (
      <div
        data-testid="device-rack-panel"
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
          fontSize: 12,
        }}
      >
        {t("deviceRack.noTrack")}
      </div>
    );
  }

  const instConfig = (selectedTrack.instrumentConfig ?? {}) as Record<string, unknown>;
  const instParams = (instConfig.parameters ?? {}) as Record<string, number>;
  const currentPreset = (instConfig.preset as string | undefined) ?? activeInstrument?.presetList?.[0]?.id ?? "";
  const currentArticulation = (instConfig.articulation as string | undefined) ?? "natural";
  const effects = selectedTrack.effects ?? [];
  const buses = project.buses ?? [];
  const otherTracks = project.tracks.filter((tr) => tr.id !== selectedTrack.id);

  const handleAuditionInstrument = async () => {
    if (!selectedTrack.instrumentRef || previewing) return;
    setPreviewing(true);
    try {
      const blob = await dawApi.previewInstrumentBlob({
        instrumentRef: selectedTrack.instrumentRef,
        presetId: currentPreset || null,
        parameters: instParams,
      });
      const url = URL.createObjectURL(blob);
      if (previewAudioRef.current) {
        previewAudioRef.current.pause();
      }
      const audio = new Audio(url);
      previewAudioRef.current = audio;
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setPreviewing(false);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        setPreviewing(false);
      };
      await audio.play();
    } catch (err) {
      setPreviewing(false);
      showToast(err instanceof Error ? err.message : "Preview failed", "error");
    }
  };

  const handleToggleFreeze = async () => {
    if (isFreezing) return;
    setIsFreezing(true);
    try {
      await saveCurrentProject();
      if (selectedTrack.freezeState?.frozen) {
        const res = await dawApi.unfreezeTrack(project.id, selectedTrack.id);
        applyExternalProjectUpdate(res.project, `${selectedTrack.name} Unfreeze 완료`);
      } else {
        const res = await dawApi.freezeTrack(project.id, selectedTrack.id);
        applyExternalProjectUpdate(res.project, `${selectedTrack.name} 48 kHz Freeze 완료`);
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Freeze failed", "error");
    } finally {
      setIsFreezing(false);
    }
  };

  const handleDiagnoseTrack = async () => {
    try {
      await saveCurrentProject();
      const diag = await dawApi.diagnoseTrack(project.id, selectedTrack.id);
      const findings = (diag.findingsKo as string[] | undefined) ?? [];
      const cent = diag.spectralCentroidHz ?? 0;
      const w = diag.stereoWidth ?? 0;
      setDiagnosisText(`중심 ${cent}Hz · 폭 ${w} · ${findings[0] ?? "진단 완료"}`);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Diagnosis failed", "error");
    }
  };

  const handleAddFx = (fxType: string) => {
    const spec = fxCatalog.find((f) => f.type === fxType);
    const defaultParams = spec ? JSON.parse(JSON.stringify(spec.defaultParams)) : {};
    const slot: EffectSlot = {
      id: makeClientId("fx"),
      type: fxType,
      name: spec?.name ?? fxType,
      nameKo: spec?.nameKo ?? fxType,
      enabled: true,
      bypass: false,
      wetDry: Number(defaultParams.wetDry ?? 1.0),
      preset: spec?.presets?.[0]?.id ?? null,
      parameters: defaultParams,
      sidechainTrackId: fxType === "sidechain_compressor" ? (otherTracks[0]?.id ?? null) : null,
    };
    dispatch({ type: "fx.add", payload: { trackId: selectedTrack.id, slot } });
  };

  const handleAddRoomReverbBus = () => {
    const busId = makeClientId("bus");
    const revSpec = fxCatalog.find((f) => f.type === "reverb");
    const revSlot: EffectSlot = {
      id: makeClientId("fx"),
      type: "reverb",
      name: "Room Reverb",
      nameKo: "룸 리버브",
      enabled: true,
      bypass: false,
      wetDry: 1.0,
      preset: "studio_room",
      parameters: { ...(revSpec?.defaultParams ?? {}), roomType: "studio_room", wetDry: 1.0 },
    };
    dispatch({ type: "bus.add", payload: { id: busId, name: "Room Reverb", kind: "return", effects: [revSlot] } });
    dispatch({ type: "send.set", payload: { trackId: selectedTrack.id, busId, levelDb: -10, preFader: false } });
  };

  const handleQuickCutoffAutomation = () => {
    const filterFx = effects.find((f) => f.type === "filter");
    const fxId = filterFx?.id ?? makeClientId("fx");
    if (!filterFx) {
      dispatch({
        type: "fx.add",
        payload: {
          trackId: selectedTrack.id,
          slot: {
            id: fxId,
            type: "filter",
            name: "Resonant Ladder Filter",
            nameKo: "래더 필터",
            enabled: true,
            bypass: false,
            wetDry: 1.0,
            preset: "buildup_lp",
            parameters: { mode: "lpf24", cutoffHz: 400, resonance: 0.42, drive: 1.3 },
          },
        },
      });
    }
    const endB = Math.min(project.lengthBeats, 16);
    dispatch({
      type: "automation.upsertLane",
      payload: {
        trackId: selectedTrack.id,
        lane: {
          id: makeClientId("auto"),
          targetType: "fx",
          targetId: fxId,
          parameterId: "cutoffHz",
          enabled: true,
          points: [
            { id: makeClientId("apt"), beat: 0, value: 280, interpolation: "linear" },
            { id: makeClientId("apt"), beat: endB * 0.5, value: 1400, interpolation: "linear" },
            { id: makeClientId("apt"), beat: endB, value: 9200, interpolation: "linear" },
          ],
        },
      },
    });
    showToast("컷오프 오토메이션 추가됨 (280Hz → 9.2kHz)");
  };

  return (
    <div
      data-testid="device-rack-panel"
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
      }}
    >
      {/* Compact Device Rack Header Strip */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          padding: "5px 10px",
          borderBottom: "1px solid var(--border-subtle)",
          background: "var(--bg-elevated)",
          fontSize: 11,
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: selectedTrack.color,
              flexShrink: 0,
            }}
          />
          <strong style={{ color: "var(--text-primary)" }}>{selectedTrack.name}</strong>
          {selectedTrack.freezeState?.frozen && (
            <span
              className="tag-badge"
              style={{ background: "#23394a", color: "#8bd0f5", borderColor: "#3a5f7a" }}
              data-testid="badge-track-frozen"
            >
              ❄ {t("deviceRack.frozenBadge")}
            </span>
          )}
          {(selectedTrack.automationLanes?.length ?? 0) > 0 && (
            <span className="tag-badge" style={{ color: "#e8c37a", borderColor: "#6e5c34" }}>
              AUTO ({selectedTrack.automationLanes?.length})
            </span>
          )}
          {diagnosisText && (
            <span
              style={{
                fontSize: 10,
                color: "#a8d5ba",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              data-testid="track-diagnosis-banner"
            >
              {diagnosisText}
            </span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          <select
            value={addFxChoice}
            onChange={(e) => setAddFxChoice(e.target.value)}
            style={{ fontSize: 10, padding: "2px 6px", height: 22 }}
            aria-label="Select FX to insert"
            data-testid="select-add-fx"
          >
            {fxCatalog.map((fx) => (
              <option key={fx.type} value={fx.type}>
                {locale === "ko" ? fx.nameKo : fx.name}
              </option>
            ))}
          </select>
          <button
            style={{ fontSize: 10, padding: "2px 8px", display: "flex", alignItems: "center", gap: 3 }}
            onClick={() => handleAddFx(addFxChoice)}
            data-testid="btn-add-fx-slot"
          >
            <Plus size={11} />
            {t("deviceRack.addFx")}
          </button>
          <button
            style={{ fontSize: 10, padding: "2px 7px", display: "flex", alignItems: "center", gap: 3 }}
            onClick={handleQuickCutoffAutomation}
            title="Resonant Filter Cutoff Sweep"
            data-testid="btn-quick-cutoff-auto"
          >
            <Waves size={11} />
            {t("deviceRack.autoAddCutoff")}
          </button>
          <button
            style={{ fontSize: 10, padding: "2px 7px", display: "flex", alignItems: "center", gap: 3 }}
            onClick={() => void handleDiagnoseTrack()}
            data-testid="btn-diagnose-track"
          >
            <Activity size={11} />
            {t("deviceRack.diagnoseTrack")}
          </button>
          <button
            style={{
              fontSize: 10,
              padding: "2px 8px",
              display: "flex",
              alignItems: "center",
              gap: 3,
              background: selectedTrack.freezeState?.frozen ? "#243b4d" : undefined,
              borderColor: selectedTrack.freezeState?.frozen ? "#5498c4" : undefined,
            }}
            disabled={isFreezing}
            onClick={() => void handleToggleFreeze()}
            data-testid="btn-toggle-freeze"
          >
            <Snowflake size={11} />
            {isFreezing
              ? "..."
              : selectedTrack.freezeState?.frozen
                ? t("deviceRack.unfreeze")
                : t("deviceRack.freeze")}
          </button>
        </div>
      </div>

      {/* Horizontal Device Cards matching Image 1 */}
      <div
        style={{
          flex: 1,
          display: "flex",
          gap: 8,
          padding: "6px 10px",
          overflowX: "auto",
          overflowY: "auto",
          alignItems: "flex-start",
        }}
      >
        {/* CARD 1: Instrument Device Card (MIDI Tracks) */}
        {selectedTrack.type === "midi" && (
          <div
            data-testid="device-card-instrument"
            style={{
              width: 222,
              flexShrink: 0,
              background: "#1c2028",
              border: "1px solid #353d4d",
              borderTop: "2px solid #b89458",
              borderRadius: 6,
              padding: "6px 8px",
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 4 }}>
              <span style={{ fontWeight: 700, fontSize: 11, color: "var(--text-primary)" }}>
                {locale === "ko"
                  ? activeInstrument?.nameKo ?? selectedTrack.instrumentRef ?? "Instrument"
                  : activeInstrument?.name ?? selectedTrack.instrumentRef ?? "Instrument"}
              </span>
              <button
                className="icon-btn"
                title={t("browser.previewBtn")}
                onClick={() => void handleAuditionInstrument()}
                disabled={previewing}
                data-testid="btn-preview-rack-instrument"
                style={{ padding: "2px 6px", fontSize: 10, display: "flex", alignItems: "center", gap: 3 }}
              >
                <Play size={10} />
                {previewing ? "…" : ""}
              </button>
            </div>

            <select
              value={selectedTrack.instrumentRef ?? "basic-poly-synth"}
              onChange={(e) => {
                const nextInst = instruments.find((i) => i.instrumentId === e.target.value);
                dispatch({
                  type: "track.setInstrument",
                  payload: {
                    trackId: selectedTrack.id,
                    instrumentRef: e.target.value,
                    preset: nextInst?.presetList?.[0]?.id ?? null,
                  },
                });
              }}
              style={{ fontSize: 10, padding: "2px 4px" }}
              data-testid="select-track-instrument"
            >
              {instruments.map((inst) => (
                <option key={inst.instrumentId} value={inst.instrumentId}>
                  [{inst.engineType === "pro_soundfont" ? "SF3" : inst.engineType === "pro_synth" ? "SYNTH" : inst.engineType === "pro_drum_rack" ? "RACK" : inst.engineType === "pro_sampler" ? "SAMP" : "PREV"}]{" "}
                  {locale === "ko" ? inst.nameKo : inst.name}
                </option>
              ))}
            </select>

            {(activeInstrument?.presetList?.length ?? 0) > 1 && (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 10, color: "var(--text-muted)", minWidth: 36 }}>{t("deviceRack.preset")}</span>
                <select
                  value={currentPreset}
                  onChange={(e) =>
                    dispatch({
                      type: "instrument.setPreset",
                      payload: { trackId: selectedTrack.id, preset: e.target.value },
                    })
                  }
                  style={{ flex: 1, fontSize: 10, padding: "2px 4px" }}
                  data-testid="select-instrument-preset"
                >
                  {activeInstrument?.presetList.map((pr) => (
                    <option key={pr.id} value={pr.id}>
                      {locale === "ko" ? pr.nameKo ?? pr.name : pr.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Instrument Key Parameters (Cutoff, Reso, Decay, Tone, etc.) */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 8px", marginTop: 2 }}>
              {(activeInstrument?.supportedParameters ?? []).slice(0, 4).map((param) => {
                const val = Number(instParams[param.id] ?? param.default);
                return (
                  <label key={param.id} style={{ display: "flex", flexDirection: "column", gap: 1, fontSize: 9, color: "var(--text-secondary)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>{locale === "ko" ? param.labelKo ?? param.label : param.label}</span>
                      <span className="mono" style={{ color: "#d4b472" }}>
                        {param.unit === "Hz" && val >= 1000 ? `${(val / 1000).toFixed(1)}k` : Number.isInteger(val) ? val : val.toFixed(2)}
                      </span>
                    </div>
                    <input
                      type="range"
                      className="mini-slider"
                      min={param.min}
                      max={param.max}
                      step={(param.max - param.min) / 80}
                      value={val}
                      onChange={(e) =>
                        dispatch({
                          type: "instrument.setParams",
                          payload: {
                            trackId: selectedTrack.id,
                            parameters: { [param.id]: parseFloat(e.target.value) },
                          },
                        })
                      }
                    />
                  </label>
                );
              })}
            </div>

            {(activeInstrument?.supportedArticulations?.length ?? 0) > 1 && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: "auto" }}>
                <span style={{ fontSize: 9, color: "var(--text-muted)" }}>Articulation</span>
                <select
                  value={currentArticulation}
                  onChange={(e) =>
                    dispatch({
                      type: "instrument.setParams",
                      payload: { trackId: selectedTrack.id, parameters: {}, articulation: e.target.value },
                    })
                  }
                  style={{ flex: 1, fontSize: 9, padding: "1px 4px" }}
                >
                  {activeInstrument?.supportedArticulations?.map((art) => (
                    <option key={art} value={art}>
                      {art}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}

        {/* CARDS 2..N: Insert FX Chain Cards */}
        {effects.length === 0 ? (
          <div
            style={{
              flex: 1,
              minWidth: 240,
              border: "1px dashed var(--border-subtle)",
              borderRadius: 6,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--text-muted)",
              fontSize: 11,
              padding: 12,
              textAlign: "center",
            }}
          >
            {t("deviceRack.emptyFx")}
          </div>
        ) : (
          effects.map((slot, idx) => {
            const p = (slot.parameters ?? {}) as Record<string, unknown>;
            const borderAccent =
              slot.type === "parametric_eq"
                ? "#68a885"
                : slot.type === "compressor" || slot.type === "sidechain_compressor" || slot.type === "limiter"
                  ? "#79a8c9"
                  : slot.type === "reverb" || slot.type === "delay"
                    ? "#9b87c4"
                    : "#c4915e";

            return (
              <div
                key={slot.id}
                data-testid={`fx-card-${slot.type}`}
                style={{
                  width: slot.type === "parametric_eq" ? 236 : 194,
                  flexShrink: 0,
                  background: "#1c2028",
                  border: `1px solid ${slot.bypass ? "#2b303a" : "#353d4d"}`,
                  borderTop: `2px solid ${slot.bypass ? "#525866" : borderAccent}`,
                  borderRadius: 6,
                  padding: "6px 8px",
                  opacity: slot.bypass ? 0.58 : 1,
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                }}
              >
                {/* Card Header: Bypass + Name + Reorder + Delete */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 5, minWidth: 0 }}>
                    <button
                      className="icon-btn"
                      title={slot.bypass ? t("deviceRack.bypass") : t("deviceRack.active")}
                      onClick={() =>
                        dispatch({
                          type: "fx.setBypass",
                          payload: { trackId: selectedTrack.id, fxId: slot.id, bypass: !slot.bypass },
                        })
                      }
                      style={{
                        color: slot.bypass ? "var(--text-muted)" : borderAccent,
                        padding: 2,
                      }}
                      data-testid={`btn-fx-bypass-${slot.id}`}
                    >
                      <Power size={11} />
                    </button>
                    <span
                      style={{
                        fontWeight: 600,
                        fontSize: 11,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {locale === "ko" ? slot.nameKo ?? slot.name : slot.name}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 2 }}>
                    {idx > 0 && (
                      <button
                        className="icon-btn"
                        style={{ padding: 1 }}
                        onClick={() =>
                          dispatch({
                            type: "fx.move",
                            payload: { trackId: selectedTrack.id, fromIndex: idx, toIndex: idx - 1 },
                          })
                        }
                      >
                        <ArrowLeft size={10} />
                      </button>
                    )}
                    {idx < effects.length - 1 && (
                      <button
                        className="icon-btn"
                        style={{ padding: 1 }}
                        onClick={() =>
                          dispatch({
                            type: "fx.move",
                            payload: { trackId: selectedTrack.id, fromIndex: idx, toIndex: idx + 1 },
                          })
                        }
                      >
                        <ArrowRight size={10} />
                      </button>
                    )}
                    <button
                      className="icon-btn"
                      style={{ padding: 1 }}
                      onClick={() =>
                        dispatch({
                          type: "fx.remove",
                          payload: { trackId: selectedTrack.id, fxId: slot.id },
                        })
                      }
                      data-testid={`btn-fx-remove-${slot.id}`}
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                </div>

                {/* Specialized UI per FX Type */}
                {slot.type === "parametric_eq" && (() => {
                  const bands = ((p.bands as EqBand[] | undefined) ?? [
                    { id: "hpf", type: "highpass", freqHz: 80, gainDb: 0, q: 0.707, enabled: false },
                    { id: "low_mid", type: "peak", freqHz: 320, gainDb: 0, q: 1.1, enabled: true },
                    { id: "high_mid", type: "peak", freqHz: 2800, gainDb: 0, q: 1.0, enabled: true },
                    { id: "high", type: "high_shelf", freqHz: 8500, gainDb: 0, q: 0.707, enabled: true },
                  ]);
                  const svgPath = computeAnalyticalEqSvgPath(bands, 214, 46);
                  const updateBand = (bIdx: number, patch: Partial<EqBand>) => {
                    const nextBands = bands.map((b, i) => (i === bIdx ? { ...b, ...patch } : b));
                    dispatch({
                      type: "fx.setParams",
                      payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { bands: nextBands } },
                    });
                  };
                  return (
                    <>
                      <svg width={214} height={46} style={{ background: "#14171c", borderRadius: 4, border: "1px solid var(--border-subtle)" }}>
                        <line x1={0} y1={23} x2={214} y2={23} stroke="#2a303c" strokeWidth={1} />
                        <path d={svgPath} fill="none" stroke="#7dd19d" strokeWidth={2} />
                      </svg>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4, fontSize: 9 }}>
                        {bands.filter((b) => b.type === "peak" || b.type === "high_shelf").slice(0, 3).map((b) => {
                          const realIdx = bands.findIndex((x) => x.id === b.id);
                          return (
                            <label key={b.id} style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                              <span style={{ color: "var(--text-muted)" }}>
                                {b.freqHz >= 1000 ? `${(b.freqHz / 1000).toFixed(1)}k` : `${Math.round(b.freqHz)}Hz`}{" "}
                                <strong className="mono" style={{ color: "#7dd19d" }}>
                                  {b.gainDb > 0 ? `+${b.gainDb.toFixed(1)}` : b.gainDb.toFixed(1)}
                                </strong>
                              </span>
                              <input
                                type="range"
                                className="mini-slider"
                                min={-12}
                                max={12}
                                step={0.5}
                                value={b.gainDb}
                                onChange={(e) => updateBand(realIdx, { gainDb: parseFloat(e.target.value), enabled: true })}
                              />
                            </label>
                          );
                        })}
                      </div>
                    </>
                  );
                })()}

                {(slot.type === "compressor" || slot.type === "sidechain_compressor") && (
                  <>
                    <CompressorTransferSvg
                      thresholdDb={Number(p.thresholdDb ?? -18)}
                      ratio={Number(p.ratio ?? 4)}
                    />
                    {slot.type === "sidechain_compressor" && (
                      <select
                        value={slot.sidechainTrackId ?? ""}
                        onChange={(e) =>
                          dispatch({
                            type: "fx.setParams",
                            payload: {
                              trackId: selectedTrack.id,
                              fxId: slot.id,
                              sidechainTrackId: e.target.value || null,
                            },
                          })
                        }
                        style={{ fontSize: 9, padding: "1px 4px" }}
                        data-testid={`select-sidechain-src-${slot.id}`}
                      >
                        <option value="">{t("deviceRack.sidechainNone")}</option>
                        {otherTracks.map((ot) => (
                          <option key={ot.id} value={ot.id}>
                            SC: {ot.name}
                          </option>
                        ))}
                      </select>
                    )}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, fontSize: 9 }}>
                      <label style={{ display: "flex", flexDirection: "column" }}>
                        <span>Thresh <b className="mono">{Number(p.thresholdDb ?? -18).toFixed(0)}dB</b></span>
                        <input
                          type="range"
                          className="mini-slider"
                          min={-42}
                          max={0}
                          step={1}
                          value={Number(p.thresholdDb ?? -18)}
                          onChange={(e) =>
                            dispatch({
                              type: "fx.setParams",
                              payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { thresholdDb: parseFloat(e.target.value) } },
                            })
                          }
                        />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column" }}>
                        <span>Ratio <b className="mono">{Number(p.ratio ?? 4).toFixed(1)}:1</b></span>
                        <input
                          type="range"
                          className="mini-slider"
                          min={1}
                          max={12}
                          step={0.5}
                          value={Number(p.ratio ?? 4)}
                          onChange={(e) =>
                            dispatch({
                              type: "fx.setParams",
                              payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { ratio: parseFloat(e.target.value) } },
                            })
                          }
                        />
                      </label>
                    </div>
                  </>
                )}

                {slot.type === "reverb" && (
                  <>
                    <ReverbDepthSvg
                      decaySec={Number(p.decaySec ?? 1.2)}
                      preDelayMs={Number(p.preDelayMs ?? 14)}
                      wetDry={Number(slot.wetDry ?? p.wetDry ?? 0.28)}
                    />
                    <select
                      value={String(p.roomType ?? "studio_room")}
                      onChange={(e) =>
                        dispatch({
                          type: "fx.setParams",
                          payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { roomType: e.target.value } },
                        })
                      }
                      style={{ fontSize: 9, padding: "1px 4px" }}
                    >
                      <option value="small_room">Small Room</option>
                      <option value="studio_room">Studio Room</option>
                      <option value="chamber">Chamber</option>
                      <option value="plate">Plate</option>
                      <option value="hall">Concert Hall</option>
                      <option value="large_ambient">Large Ambient</option>
                    </select>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, fontSize: 9 }}>
                      <label style={{ display: "flex", flexDirection: "column" }}>
                        <span>Decay <b className="mono">{Number(p.decaySec ?? 1.2).toFixed(1)}s</b></span>
                        <input
                          type="range"
                          className="mini-slider"
                          min={0.3}
                          max={5.0}
                          step={0.1}
                          value={Number(p.decaySec ?? 1.2)}
                          onChange={(e) =>
                            dispatch({
                              type: "fx.setParams",
                              payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { decaySec: parseFloat(e.target.value) } },
                            })
                          }
                        />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column" }}>
                        <span>Mix <b className="mono">{Math.round(Number(slot.wetDry ?? 0.28) * 100)}%</b></span>
                        <input
                          type="range"
                          className="mini-slider"
                          min={0}
                          max={1}
                          step={0.02}
                          value={Number(slot.wetDry ?? 0.28)}
                          onChange={(e) =>
                            dispatch({
                              type: "fx.setParams",
                              payload: { trackId: selectedTrack.id, fxId: slot.id, wetDry: parseFloat(e.target.value) },
                            })
                          }
                        />
                      </label>
                    </div>
                  </>
                )}

                {slot.type === "delay" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9 }}>
                    <select
                      value={String(p.subdivision ?? "1/8 dotted")}
                      onChange={(e) =>
                        dispatch({
                          type: "fx.setParams",
                          payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { tempoSync: true, subdivision: e.target.value } },
                        })
                      }
                      style={{ fontSize: 9, padding: "1px 4px" }}
                    >
                      <option value="1/16">1/16 Sync</option>
                      <option value="1/8">1/8 Sync</option>
                      <option value="1/8 dotted">1/8 Dotted</option>
                      <option value="1/4">1/4 Sync</option>
                    </select>
                    <label style={{ display: "flex", flexDirection: "column" }}>
                      <span>Feedback <b className="mono">{Math.round(Number(p.feedback ?? 0.36) * 100)}%</b></span>
                      <input
                        type="range"
                        className="mini-slider"
                        min={0}
                        max={0.85}
                        step={0.02}
                        value={Number(p.feedback ?? 0.36)}
                        onChange={(e) =>
                          dispatch({
                            type: "fx.setParams",
                            payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { feedback: parseFloat(e.target.value) } },
                          })
                        }
                      />
                    </label>
                    <label style={{ display: "flex", flexDirection: "column" }}>
                      <span>Mix <b className="mono">{Math.round(Number(slot.wetDry ?? 0.25) * 100)}%</b></span>
                      <input
                        type="range"
                        className="mini-slider"
                        min={0}
                        max={1}
                        step={0.02}
                        value={Number(slot.wetDry ?? 0.25)}
                        onChange={(e) =>
                          dispatch({
                            type: "fx.setParams",
                            payload: { trackId: selectedTrack.id, fxId: slot.id, wetDry: parseFloat(e.target.value) },
                          })
                        }
                      />
                    </label>
                  </div>
                )}

                {slot.type === "guitar_amp" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9 }}>
                    <select
                      value={String(p.ampModel ?? "crunch")}
                      onChange={(e) =>
                        dispatch({
                          type: "fx.setParams",
                          payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { ampModel: e.target.value } },
                        })
                      }
                      style={{ fontSize: 9, padding: "1px 4px" }}
                    >
                      <option value="clean">Twin Clean</option>
                      <option value="edge_of_breakup">Edge of Breakup</option>
                      <option value="crunch">British Crunch</option>
                      <option value="overdrive">Tube Overdrive</option>
                      <option value="high_gain">High Gain Stack</option>
                    </select>
                    <select
                      value={String(p.cabinet ?? "2x12_british")}
                      onChange={(e) =>
                        dispatch({
                          type: "fx.setParams",
                          payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { cabinet: e.target.value } },
                        })
                      }
                      style={{ fontSize: 9, padding: "1px 4px" }}
                    >
                      <option value="1x12_open">Cab: 1x12 Open</option>
                      <option value="2x12_british">Cab: 2x12 British</option>
                      <option value="4x12_modern">Cab: 4x12 Modern</option>
                      <option value="direct_di">Direct DI</option>
                    </select>
                    <label style={{ display: "flex", flexDirection: "column" }}>
                      <span>Drive <b className="mono">{Math.round(Number(p.drive ?? 0.55) * 100)}%</b></span>
                      <input
                        type="range"
                        className="mini-slider"
                        min={0.1}
                        max={1}
                        step={0.02}
                        value={Number(p.drive ?? 0.55)}
                        onChange={(e) =>
                          dispatch({
                            type: "fx.setParams",
                            payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { drive: parseFloat(e.target.value) } },
                          })
                        }
                      />
                    </label>
                  </div>
                )}

                {!["parametric_eq", "compressor", "sidechain_compressor", "reverb", "delay", "guitar_amp"].includes(slot.type) && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9, marginTop: 2 }}>
                    {Object.entries(p)
                      .filter(([, v]) => typeof v === "number")
                      .slice(0, 3)
                      .map(([k, v]) => {
                        const num = Number(v);
                        const maxV = k.includes("Hz") ? 16000 : k.includes("Db") ? 24 : k.includes("bit") ? 16 : 1;
                        const minV = k.includes("Hz") ? 80 : k.includes("Db") ? -12 : k.includes("bit") ? 3 : 0;
                        return (
                          <label key={k} style={{ display: "flex", flexDirection: "column" }}>
                            <span>
                              {k} <b className="mono">{num >= 1000 ? `${(num / 1000).toFixed(1)}k` : num.toFixed(1)}</b>
                            </span>
                            <input
                              type="range"
                              className="mini-slider"
                              min={minV}
                              max={maxV}
                              step={(maxV - minV) / 60}
                              value={num}
                              onChange={(e) =>
                                dispatch({
                                  type: "fx.setParams",
                                  payload: { trackId: selectedTrack.id, fxId: slot.id, parameters: { [k]: parseFloat(e.target.value) } },
                                })
                              }
                            />
                          </label>
                        );
                      })}
                  </div>
                )}
              </div>
            );
          })
        )}

        {/* Rightmost Compact Sends / Return Bus Card */}
        <div
          style={{
            width: 162,
            flexShrink: 0,
            background: "#181b21",
            border: "1px solid var(--border-subtle)",
            borderRadius: 6,
            padding: "7px 8px",
            display: "flex",
            flexDirection: "column",
            gap: 5,
            fontSize: 10,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>{t("deviceRack.sendsTitle")}</span>
            <Sparkles size={11} color="#9b87c4" />
          </div>
          {buses.length === 0 ? (
            <button style={{ fontSize: 10, padding: "4px 6px" }} onClick={handleAddRoomReverbBus} data-testid="btn-add-room-reverb-bus">
              {t("deviceRack.addReverbBus")}
            </button>
          ) : (
            buses.map((bus) => {
              const snd = (selectedTrack.sends ?? []).find((s) => s.busId === bus.id);
              const lvl = snd ? snd.levelDb : -60;
              return (
                <label key={bus.id} style={{ display: "flex", flexDirection: "column", gap: 1, fontSize: 9 }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>{bus.name}</span>
                    <span className="mono">{lvl <= -59 ? "-∞" : `${lvl.toFixed(0)}dB`}</span>
                  </div>
                  <input
                    type="range"
                    className="mini-slider"
                    min={-60}
                    max={0}
                    step={1}
                    value={lvl}
                    onChange={(e) =>
                      dispatch({
                        type: "send.set",
                        payload: { trackId: selectedTrack.id, busId: bus.id, levelDb: parseFloat(e.target.value) },
                      })
                    }
                  />
                </label>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
