import React, { useEffect, useRef } from "react";
import { Repeat, Scissors } from "lucide-react";
import { useDaw } from "../commands/store";
import { useI18n } from "../i18n";
import {
  beatsPerBar,
  beatsToSeconds,
  dbToLinear,
  formatBarBeatTick,
  formatDb,
} from "../project/time";

export function ClipEditor() {
  const { t } = useI18n();
  const {
    project,
    selectedClip,
    selectedTrack,
    waveforms,
    playheadBeats,
    dispatch,
    beginTransaction,
    commitTransaction,
  } = useDaw();

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const asset =
    project && selectedClip?.assetId
      ? project.assets.find((a) => a.id === selectedClip.assetId) ?? null
      : null;
  const waveform = selectedClip?.assetId ? waveforms[selectedClip.assetId] : undefined;

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || !project || !selectedClip || selectedClip.type !== "audio") return;

    const draw = () => {
      const rect = container.getBoundingClientRect();
      const w = Math.max(200, Math.floor(rect.width));
      const h = Math.max(80, Math.floor(rect.height));
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);

      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Background
      ctx.fillStyle = "#131519";
      ctx.fillRect(0, 0, w, h);

      // Subtle beat grid inside clip
      const totalBeats = selectedClip.durationBeats;
      ctx.strokeStyle = "#1f232b";
      ctx.lineWidth = 1;
      for (let b = 0; b <= totalBeats; b++) {
        const x = (b / totalBeats) * w;
        ctx.strokeStyle = b % beatsPerBar(project.timeSignature) === 0 ? "#2e3440" : "#1d2027";
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }

      // Center zero line
      ctx.strokeStyle = "#262b34";
      ctx.beginPath();
      ctx.moveTo(0, h / 2);
      ctx.lineTo(w, h / 2);
      ctx.stroke();

      // Real zoomed PCM waveform
      if (waveform && waveform.peaks.length > 0 && waveform.durationSec > 0) {
        const peaks = waveform.peaks;
        const totalDurSec = waveform.durationSec;
        const clipDurSec = beatsToSeconds(selectedClip.durationBeats, project.bpm);
        const loopLenSec = selectedClip.loop
          ? Math.max(0.05, selectedClip.loopLengthSec ?? totalDurSec - selectedClip.sourceOffsetSec)
          : totalDurSec;
        const gainLin = Math.min(2.2, dbToLinear(selectedClip.gainDb));
        const midY = h / 2;
        const maxAmp = (h - 16) / 2;
        const color = selectedTrack?.color ?? "#b89458";

        ctx.fillStyle = color;
        const barStep = 3;
        for (let x = 0; x < w; x += barStep) {
          const tInClip = (x / w) * clipDurSec;
          const tInSrc = selectedClip.loop
            ? selectedClip.sourceOffsetSec + (tInClip % loopLenSec)
            : selectedClip.sourceOffsetSec + tInClip;
          if (tInSrc < 0 || tInSrc >= totalDurSec) continue;
          const idx = Math.min(peaks.length - 1, Math.floor((tInSrc / totalDurSec) * peaks.length));
          const amp = Math.min(1, peaks[idx] * gainLin);
          const barH = Math.max(2, amp * maxAmp * 2);
          ctx.fillRect(x, midY - barH / 2, 1.8, barH);
        }
      }

      // Playhead cursor if inside clip
      if (
        playheadBeats >= selectedClip.timelineStartBeats &&
        playheadBeats <= selectedClip.timelineStartBeats + selectedClip.durationBeats
      ) {
        const relX =
          ((playheadBeats - selectedClip.timelineStartBeats) / selectedClip.durationBeats) * w;
        ctx.strokeStyle = "#e5b84b";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(relX, 0);
        ctx.lineTo(relX, h);
        ctx.stroke();
      }
    };

    draw();
    const obs = new ResizeObserver(draw);
    obs.observe(container);
    return () => obs.disconnect();
  }, [project, selectedClip, selectedTrack, waveform, playheadBeats]);

  if (!project) return null;

  if (!selectedClip) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
          fontSize: 12,
        }}
      >
        {t("clipEditor.empty")}
      </div>
    );
  }

  if (selectedClip.type === "midi") {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-secondary)",
          fontSize: 12,
        }}
      >
        {t("clipEditor.midiNotice", { name: selectedClip.name, count: selectedClip.notes.length })}
      </div>
    );
  }

  const bpb = beatsPerBar(project.timeSignature);
  const lengthBars = selectedClip.durationBeats / bpb;
  const lengthSec = beatsToSeconds(selectedClip.durationBeats, project.bpm);
  const canSplit =
    playheadBeats > selectedClip.timelineStartBeats + 0.05 &&
    playheadBeats < selectedClip.timelineStartBeats + selectedClip.durationBeats - 0.05;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }} data-testid="clip-editor">
      {/* Zoomed Real Waveform Canvas */}
      <div ref={containerRef} style={{ flex: 1, minHeight: 74, position: "relative", padding: "6px 10px 4px" }}>
        <canvas
          ref={canvasRef}
          style={{
            width: "100%",
            height: "100%",
            display: "block",
            borderRadius: 4,
            border: "1px solid var(--border-subtle)",
          }}
        />
      </div>

      {/* Bottom Precision Inspector Bar */}
      <div
        style={{
          height: 36,
          minHeight: 36,
          padding: "0 10px",
          borderTop: "1px solid var(--border-subtle)",
          background: "#16181c",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          fontSize: 11,
          overflowX: "auto",
          overflowY: "hidden",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0, whiteSpace: "nowrap" }}>
          <span className="mono" style={{ color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
            {t("clipEditor.start")}{" "}
            <strong style={{ color: "var(--text-primary)" }}>
              {formatBarBeatTick(selectedClip.timelineStartBeats, project.timeSignature)}
            </strong>
          </span>

          <label style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
            {t("clipEditor.length")}
            <input
              type="number"
              className="mono"
              step={0.5}
              min={0.25}
              max={512}
              value={Number(selectedClip.durationBeats.toFixed(1))}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (Number.isFinite(v) && v >= 0.25) {
                  dispatch({ type: "clip.trim", payload: { clipId: selectedClip.id, durationBeats: v } });
                }
              }}
              style={{ width: 62, height: 22, padding: "0 4px" }}
            />
            <span className="mono" style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }}>
              ({t("clipEditor.barsShort", { bars: lengthBars.toFixed(1), sec: lengthSec.toFixed(1) })})
            </span>
          </label>

          <label style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
            {t("clipEditor.offset")}
            <input
              type="number"
              className="mono"
              step={0.05}
              min={0}
              max={Math.max(0, (asset?.durationSec ?? 60) - 0.1)}
              value={Number(selectedClip.sourceOffsetSec.toFixed(2))}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (Number.isFinite(v) && v >= 0) {
                  dispatch({ type: "clip.trim", payload: { clipId: selectedClip.id, sourceOffsetSec: v } });
                }
              }}
              style={{ width: 52, height: 22, padding: "0 4px" }}
            />
            <span className="mono" style={{ color: "var(--text-muted)" }}>s</span>
          </label>

          <label style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
            {t("clipEditor.gain")}
            <input
              type="range"
              className="mini-slider"
              style={{ width: 56 }}
              min={-24}
              max={12}
              step={0.5}
              value={selectedClip.gainDb}
              onPointerDown={beginTransaction}
              onPointerUp={commitTransaction}
              onChange={(e) =>
                dispatch({
                  type: "clip.setGain",
                  payload: { clipId: selectedClip.id, gainDb: parseFloat(e.target.value) },
                })
              }
            />
            <span className="mono" style={{ minWidth: 48, color: "var(--text-primary)", whiteSpace: "nowrap" }}>
              {formatDb(selectedClip.gainDb)}
            </span>
          </label>

          <button
            className={selectedClip.loop ? "pill-toggle active" : ""}
            style={{ height: 22, padding: "0 7px", fontSize: 11, whiteSpace: "nowrap" }}
            onClick={() =>
              dispatch({ type: "clip.setLoop", payload: { clipId: selectedClip.id, loop: !selectedClip.loop } })
            }
          >
            <Repeat size={11} />
            {t("transport.loop")}
          </button>

          <button
            style={{ height: 22, padding: "0 7px", fontSize: 11, whiteSpace: "nowrap" }}
            disabled={!canSplit}
            title={t("timeline.splitTooltip")}
            onClick={() =>
              dispatch({
                type: "clip.split",
                payload: { clipId: selectedClip.id, splitBeat: playheadBeats },
              })
            }
          >
            <Scissors size={11} />
            {t("timeline.split")}
          </button>
        </div>

        <div
          className="mono"
          style={{ color: "var(--text-muted)", fontSize: 10, whiteSpace: "nowrap", flexShrink: 0 }}
          title={t("clipEditor.noWarpTooltip")}
        >
          {asset && asset.sampleRate > 0
            ? `${(asset.sampleRate / 1000).toFixed(1)} kHz · ${asset.channels === 1 ? t("clipEditor.mono") : t("clipEditor.stereo")}`
            : "48.0 kHz"}
        </div>
      </div>
    </div>
  );
}
