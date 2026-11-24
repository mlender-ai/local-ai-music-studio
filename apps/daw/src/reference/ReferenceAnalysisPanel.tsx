import React, { useEffect, useRef, useState } from "react";
import { Activity, GitCompare, Play, RefreshCw, Square, Upload, XCircle } from "lucide-react";
import { audioEngine } from "../audio/audioEngine";
import { useDaw } from "../commands/store";
import { useI18n } from "../i18n";
import { dawApi } from "../project/api";
import type { ReferenceComparisonResult, ReferenceItem } from "../project/types";

const BAND_LABELS: Array<{ key: string; label: string }> = [
  { key: "sub_20_60", label: "Sub 20–60" },
  { key: "bass_60_200", label: "Bass 60–200" },
  { key: "low_mid_200_500", label: "Low-Mid" },
  { key: "mid_500_2000", label: "Mid 0.5–2k" },
  { key: "presence_2k_6k", label: "Pres 2–6k" },
  { key: "air_6k_20k", label: "Air 6–20k" },
];

function EnergyCurveCanvas({
  refItem,
  playingSec,
  onSeekSec,
}: {
  refItem: ReferenceItem;
  playingSec: number | null;
  onSeekSec: (sec: number) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const analysis = refItem.analysis;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !analysis) return;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(240, Math.floor(rect.width));
    const h = Math.max(56, Math.floor(rect.height));
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.fillStyle = "#121418";
    ctx.fillRect(0, 0, w, h);

    const dur = Math.max(0.1, analysis.durationSec);
    const sections = analysis.arrangement.sections;
    const sectionColors = ["#384252", "#354d42", "#473f5b", "#5c493b", "#394f56", "#4f3e48"];

    // Draw real detected sections
    sections.forEach((sec, idx) => {
      const x0 = (sec.startSec / dur) * w;
      const x1 = (sec.endSec / dur) * w;
      ctx.fillStyle = sectionColors[idx % sectionColors.length];
      ctx.globalAlpha = 0.28;
      ctx.fillRect(x0, 0, Math.max(1, x1 - x0), h);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = "#2d333d";
      ctx.beginPath();
      ctx.moveTo(x0, 0);
      ctx.lineTo(x0, h);
      ctx.stroke();

      ctx.fillStyle = "#c8d0dc";
      ctx.font = "600 9px Inter, sans-serif";
      ctx.fillText(sec.label, x0 + 4, 11);
    });

    // Draw real time-aligned Energy Curve
    const curve = analysis.arrangement.energyCurve;
    if (curve.length > 1) {
      ctx.beginPath();
      ctx.moveTo(0, h);
      for (const pt of curve) {
        const x = (pt.timeSec / dur) * w;
        const y = h - 4 - pt.normEnergy * (h - 20);
        ctx.lineTo(x, y);
      }
      ctx.lineTo(w, h);
      ctx.closePath();
      ctx.fillStyle = "rgba(184, 148, 88, 0.28)";
      ctx.fill();

      ctx.beginPath();
      curve.forEach((pt, idx) => {
        const x = (pt.timeSec / dur) * w;
        const y = h - 4 - pt.normEnergy * (h - 20);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = "#d9b468";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    if (playingSec !== null && playingSec >= 0) {
      const px = (playingSec / dur) * w;
      ctx.strokeStyle = "#63b47c";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(px, 0);
      ctx.lineTo(px, h);
      ctx.stroke();
    }
  }, [analysis, playingSec]);

  if (!analysis) return null;

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: "100%",
        height: 62,
        display: "block",
        borderRadius: 4,
        border: "1px solid var(--border-subtle)",
        cursor: "pointer",
      }}
      onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        onSeekSec(ratio * analysis.durationSec);
      }}
    />
  );
}

export function ReferenceAnalysisPanel() {
  const { locale, t } = useI18n();
  const {
    project,
    activeReference,
    activeAnalysisJob,
    runReferenceAnalysis,
    cancelReferenceAnalysis,
    toggleBlueprintInfluence,
    attachAudioToReference,
    showToast,
  } = useDaw();

  const [refPlaying, setRefPlaying] = useState(false);
  const [refPlaySec, setRefPlaySec] = useState<number | null>(null);
  const [compareTarget, setCompareTarget] = useState<string>("project_mix");
  const [comparing, setComparing] = useState(false);
  const [comparison, setComparison] = useState<ReferenceComparisonResult | null>(null);
  const attachInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setComparison(null);
  }, [activeReference?.id]);

  useEffect(() => {
    if (!refPlaying || !project || !activeReference) return;
    const expectedUrl = dawApi.referenceAudioUrl(project.id, activeReference.id);
    const id = window.setInterval(() => {
      const st = audioEngine.getReferencePreviewState();
      if (st.playingUrl === expectedUrl) {
        setRefPlaySec(st.positionSec);
      } else {
        setRefPlaying(false);
        setRefPlaySec(null);
      }
    }, 80);
    return () => window.clearInterval(id);
  }, [refPlaying, project?.id, activeReference?.id]);

  if (!project) return null;

  if (!activeReference) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
          fontSize: 12,
          padding: 16,
        }}
        data-testid="reference-panel-empty"
      >
        {t("ref.empty")}
      </div>
    );
  }

  const audioUrl = dawApi.referenceAudioUrl(project.id, activeReference.id);
  const isAnalyzing =
    activeAnalysisJob?.referenceId === activeReference.id &&
    (activeAnalysisJob.status === "queued" || activeAnalysisJob.status === "running");

  const playAt = async (sec = 0) => {
    try {
      await audioEngine.playReferencePreview(audioUrl, sec);
      setRefPlaying(true);
      setRefPlaySec(sec);
    } catch (err) {
      showToast((err as Error).message, "error");
    }
  };

  const stopPlay = () => {
    audioEngine.stopReferencePreview();
    setRefPlaying(false);
    setRefPlaySec(null);
  };

  const handleCompare = async () => {
    setComparing(true);
    try {
      const isMix = compareTarget === "project_mix";
      const res = await dawApi.compareReference(
        project.id,
        activeReference.id,
        isMix ? "project_mix" : "asset",
        isMix ? undefined : compareTarget
      );
      setComparison(res);
    } catch (err) {
      showToast((err as Error).message, "error");
    } finally {
      setComparing(false);
    }
  };

  const analysis = activeReference.analysis;
  const bp = activeReference.blueprint;
  const audioAssets = project.assets.filter((a) => a.kind !== "midi");

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        overflow: "hidden",
      }}
      data-testid="reference-analysis-panel"
    >
      <input
        ref={attachInputRef}
        type="file"
        accept=".wav,.mp3,.flac,.ogg,.aiff,.aif,.m4a,.mp4,.mov"
        style={{ display: "none" }}
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (f) await attachAudioToReference(activeReference.id, f);
          e.target.value = "";
        }}
      />

      {/* Top Reference Control Bar */}
      <div
        style={{
          height: 32,
          minHeight: 32,
          padding: "0 10px",
          background: "#16181c",
          borderBottom: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <strong style={{ fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {activeReference.name}
          </strong>
          {activeReference.durationSec > 0 && (
            <span className="mono" style={{ fontSize: 10, color: "var(--text-muted)" }}>
              {activeReference.durationSec.toFixed(1)}s · {(activeReference.sampleRate / 1000).toFixed(1)} kHz
            </span>
          )}
          <span style={{ fontSize: 10, color: "var(--text-muted)" }}>· {t("browser.refExcludedNote")}</span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          {activeReference.audioAvailable ? (
            <>
              <button
                style={{ height: 22, padding: "0 8px", fontSize: 11 }}
                onClick={() => (refPlaying ? stopPlay() : void playAt(0))}
                data-testid="btn-ref-play"
              >
                {refPlaying ? <Square size={10} fill="currentColor" /> : <Play size={10} fill="currentColor" />}
                {refPlaying ? t("ref.stop") : t("ref.play")}
              </button>
              {isAnalyzing ? (
                <button
                  style={{ height: 22, padding: "0 8px", fontSize: 11, borderColor: "var(--accent-playhead)" }}
                  onClick={() => void cancelReferenceAnalysis()}
                >
                  <XCircle size={11} />
                  {t("ref.analyzing", {
                    pct: activeAnalysisJob.progress,
                    stage: activeAnalysisJob.stage,
                  })}
                </button>
              ) : (
                <button
                  className="btn-primary"
                  style={{ height: 22, padding: "0 9px", fontSize: 11 }}
                  onClick={() => void runReferenceAnalysis(activeReference.id)}
                  data-testid="btn-run-ref-analysis"
                >
                  {analysis ? <RefreshCw size={11} /> : <Activity size={11} />}
                  {analysis ? t("ref.reanalyze") : t("ref.runAnalysis")}
                </button>
              )}
            </>
          ) : (
            <button
              className="btn-primary"
              style={{ height: 22, padding: "0 9px", fontSize: 11 }}
              onClick={() => attachInputRef.current?.click()}
            >
              <Upload size={11} />
              {t("ref.attachAudioForUrl")}
            </button>
          )}
        </div>
      </div>

      {/* Main Scrollable Analysis Content */}
      {!activeReference.audioAvailable ? (
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            padding: 16,
            color: "var(--text-secondary)",
          }}
        >
          <div style={{ fontWeight: 600 }}>
            {locale === "ko"
              ? activeReference.noticeKo || t("ref.urlOnlyNotice")
              : activeReference.noticeEn || t("ref.urlOnlyNotice")}
          </div>
          {activeReference.url && (
            <div className="mono" style={{ fontSize: 10, color: "var(--text-muted)" }}>
              {activeReference.url}
            </div>
          )}
        </div>
      ) : !analysis ? (
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            color: "var(--text-secondary)",
            fontSize: 12,
          }}
        >
          <span>{t("ref.measuredVsEstimated")}</span>
          <button
            className="btn-primary"
            onClick={() => void runReferenceAnalysis(activeReference.id)}
          >
            <Activity size={12} />
            {t("ref.runAnalysis")}
          </button>
        </div>
      ) : (
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "8px 10px",
            display: "grid",
            gridTemplateColumns: "1.35fr 1fr",
            gap: 10,
          }}
        >
          {/* Left Column: Summary Metrics + Structure/Energy Curve + Blueprint Influences */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
            {/* Top 4 Key Metrics */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 }}>
              <div className="producer-card" style={{ padding: "6px 8px" }}>
                <span className="producer-label">{t("ref.bpm")}</span>
                <strong className="mono" style={{ fontSize: 13 }} data-testid="ref-bpm-value">
                  {analysis.rhythm.adoptedTempoBpm ?? analysis.rhythm.estimatedBpm ?? "?"} BPM
                </strong>
                <span style={{ fontSize: 9, color: "var(--text-muted)" }}>
                  {analysis.rhythm.halfDoubleRelation
                    ? `${analysis.rhythm.halfDoubleRelation} (pulse ${analysis.rhythm.measuredPulseBpm ?? "?"})`
                    : analysis.rhythm.halfDoubleAmbiguous
                    ? t("ref.ambiguousHalfDouble")
                    : `${analysis.rhythm.meterEstimate} · ${analysis.rhythm.grooveFeel ?? "straight"}`}
                </span>
              </div>
              <div className="producer-card" style={{ padding: "6px 8px" }}>
                <span className="producer-label">{t("ref.key")}</span>
                <strong style={{ fontSize: 13 }} data-testid="ref-key-value">
                  {analysis.harmony.estimatedKey}
                </strong>
                <span className="mono" style={{ fontSize: 9, color: "var(--text-muted)" }}>
                  conf {(analysis.harmony.confidence * 100).toFixed(0)}% · harm {(analysis.harmony.harmonicRepetitionScore ?? analysis.harmony.motifRepetitionScore).toFixed(2)}
                </span>
              </div>
              <div className="producer-card" style={{ padding: "6px 8px" }}>
                <span className="producer-label">{t("ref.loudness")}</span>
                <strong className="mono" style={{ fontSize: 12 }} data-testid="ref-lufs-value">
                  {analysis.sound.measured.integratedLufs ?? analysis.sound.measured.approxLufs} LUFS
                </strong>
                <span className="mono" style={{ fontSize: 9, color: "var(--text-muted)" }}>
                  TP {analysis.sound.measured.truePeakDbtp ?? analysis.sound.measured.samplePeakDbfs} dBTP · LRA {analysis.sound.measured.loudnessRangeLu ?? analysis.sound.measured.dynamicRangeDb} LU
                </span>
              </div>
              <div className="producer-card" style={{ padding: "6px 8px" }}>
                <span className="producer-label">{t("ref.stereo")}</span>
                <strong className="mono" style={{ fontSize: 12 }}>
                  {analysis.sound.measured.stereoWidth.toFixed(2)}
                </strong>
                <span className="mono" style={{ fontSize: 9, color: "var(--text-muted)" }}>
                  corr {analysis.sound.measured.lrCorrelation} · {analysis.sound.estimated.reverbCharacter}
                </span>
              </div>
            </div>

            {/* Energy Curve & Clickable Sections */}
            <div className="producer-card" style={{ padding: "6px 8px" }}>
              <div className="producer-label">{t("ref.sections")}</div>
              <EnergyCurveCanvas
                refItem={activeReference}
                playingSec={refPlaySec}
                onSeekSec={(sec) => void playAt(sec)}
              />
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                {analysis.arrangement.sections.map((sec) => (
                  <button
                    key={sec.id}
                    style={{ fontSize: 10, padding: "2px 6px", height: 20 }}
                    onClick={() => void playAt(sec.startSec)}
                    title={`${sec.startSec}s – ${sec.endSec}s · ${sec.energyDbfs} dBFS`}
                  >
                    {sec.label} <span className="mono" style={{ color: "var(--text-muted)" }}>{sec.startSec}s</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Reference Blueprint Influence Selector */}
            {bp && (
              <div className="producer-card" style={{ padding: "6px 8px" }} data-testid="ref-blueprint-card">
                <div className="producer-label">{t("ref.blueprint")}</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                  {bp.availableInfluences.map((inf) => {
                    const active = (activeReference.selectedInfluences ?? []).includes(inf.id);
                    return (
                      <button
                        key={inf.id}
                        className={active ? "pill-toggle active" : ""}
                        style={{ height: 22, padding: "0 8px", fontSize: 10 }}
                        onClick={() => void toggleBlueprintInfluence(activeReference.id, inf.id)}
                        data-testid={`bp-influence-${inf.id}`}
                      >
                        {locale === "ko" ? inf.labelKo : inf.labelEn}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Frequency Bands + HPSS Instrument Estimate + Reference Comparison */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
            {/* Measured 6-band Frequency Distribution */}
            <div className="producer-card" style={{ padding: "6px 8px" }}>
              <div className="producer-label">{t("ref.freqBands")}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                {BAND_LABELS.map((b) => {
                  const pct = analysis.sound.measured.frequencyBandsPct[b.key] ?? 0;
                  return (
                    <div key={b.key} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10 }}>
                      <span style={{ width: 68, color: "var(--text-secondary)" }}>{b.label}</span>
                      <div style={{ flex: 1, height: 6, background: "#121418", borderRadius: 2, overflow: "hidden" }}>
                        <div
                          style={{
                            width: `${Math.min(100, pct * 1.6)}%`,
                            height: "100%",
                            background: "#648ea8",
                          }}
                        />
                      </div>
                      <span className="mono" style={{ width: 38, textAlign: "right", color: "var(--text-muted)" }}>
                        {pct.toFixed(1)}%
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* HPSS Estimated Instrumentation */}
            <div className="producer-card" style={{ padding: "6px 8px" }}>
              <div className="producer-label">{t("ref.instruments")}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {analysis.instrumentation.elements.map((el) => {
                  const isUnconfirmed = el.status === "unconfirmed" || el.confidence < 0.35;
                  return (
                  <span
                    key={el.name}
                    className="tag-badge"
                    title={el.method || undefined}
                    style={{
                      color:
                        isUnconfirmed
                          ? "var(--text-muted)"
                          : el.level === "prominent"
                          ? "var(--text-primary)"
                          : "var(--text-secondary)",
                      borderColor:
                        isUnconfirmed
                          ? "var(--border-subtle)"
                          : el.level === "prominent"
                          ? "#5f8772"
                          : undefined,
                      opacity: isUnconfirmed ? 0.65 : 1,
                    }}
                  >
                    {el.name} ·{" "}
                    {isUnconfirmed
                      ? locale === "ko"
                        ? "미확인"
                        : "unconfirmed"
                      : `${Math.round(el.confidence * 100)}%`}
                  </span>
                  );
                })}
              </div>
            </div>

            {/* Phase 02-C: Compare Reference vs Project Mix / Track Asset */}
            <div className="producer-card" style={{ padding: "6px 8px" }} data-testid="ref-compare-card">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
                <span className="producer-label">{t("ref.compareTitle")}</span>
                <div style={{ display: "flex", gap: 4 }}>
                  <select
                    value={compareTarget}
                    onChange={(e) => setCompareTarget(e.target.value)}
                    style={{ height: 22, fontSize: 10, maxWidth: 150 }}
                  >
                    <option value="project_mix">{t("ref.compareTargetProject")}</option>
                    {audioAssets.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                  <button
                    style={{ height: 22, padding: "0 7px", fontSize: 10 }}
                    disabled={comparing}
                    onClick={() => void handleCompare()}
                    data-testid="btn-compare-ref"
                  >
                    <GitCompare size={11} />
                    {t("ref.compareRun")}
                  </button>
                </div>
              </div>

              {comparison && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4, fontSize: 10 }}>
                  <div className="mono" style={{ color: "var(--text-secondary)" }}>
                    Crest {comparison.measuredDeltas.crestFactorDeltaDb >= 0 ? "+" : ""}
                    {comparison.measuredDeltas.crestFactorDeltaDb} dB · DR{" "}
                    {comparison.measuredDeltas.dynamicRangeDeltaDb >= 0 ? "+" : ""}
                    {comparison.measuredDeltas.dynamicRangeDeltaDb} dB · Stereo{" "}
                    {comparison.measuredDeltas.stereoWidthDelta >= 0 ? "+" : ""}
                    {comparison.measuredDeltas.stereoWidthDelta}
                  </div>
                  {comparison.observations.map((obs, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: "#14161a",
                        borderLeft: "2px solid var(--accent-playhead)",
                        padding: "3px 6px",
                        color: "var(--text-primary)",
                      }}
                    >
                      {locale === "ko" ? obs.ko : obs.en}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
