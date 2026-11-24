import React, { useMemo, useState } from "react";
import { ChevronRight, Code2, Radio } from "lucide-react";
import { useDaw } from "../commands/store";
import { useI18n } from "../i18n";
import { beatsToSeconds, formatBarRange } from "../project/time";

interface AIProducerPanelProps {
  width: number;
  onCollapse: () => void;
}

export function AIProducerPanel({ width, onCollapse }: AIProducerPanelProps) {
  const { t } = useI18n();
  const { project, selection, selectedTrack, selectedClip, health, savedRevision } = useDaw();
  const [draftPrompt, setDraftPrompt] = useState("");
  const [showPayload, setShowPayload] = useState(false);

  const activeSection = useMemo(() => {
    if (!project) return null;
    if (selection.selectedSectionId) {
      return project.sections.find((s) => s.id === selection.selectedSectionId) ?? null;
    }
    const targetBeat = selection.timeRangeBeats?.startBeats ?? selectedClip?.timelineStartBeats ?? null;
    if (targetBeat === null) return null;
    return project.sections.find((s) => targetBeat >= s.startBeats && targetBeat < s.endBeats) ?? null;
  }, [project, selection.selectedSectionId, selection.timeRangeBeats, selectedClip]);

  const commandPayload = useMemo(() => {
    if (!project) return null;
    return {
      commandSchemaVersion: "1.0.0",
      status: "not_connected_phase_01",
      projectId: project.id,
      bpm: project.bpm,
      timeSignature: `${project.timeSignature.numerator}/${project.timeSignature.denominator}`,
      selectionContext: {
        trackId: selection.selectedTrackId,
        trackName: selectedTrack?.name ?? null,
        trackType: selectedTrack?.type ?? null,
        clipIds: selection.selectedClipIds,
        timeRangeBeats: selection.timeRangeBeats,
        sectionId: activeSection?.id ?? null,
        sectionName: activeSection?.name ?? null,
      },
      draftInstruction: draftPrompt.trim() || null,
    };
  }, [project, selection, selectedTrack, activeSection, draftPrompt]);

  if (!project) return null;

  const barSummary = selection.timeRangeBeats
    ? formatBarRange(selection.timeRangeBeats.startBeats, selection.timeRangeBeats.endBeats, project.timeSignature)
    : selectedClip
      ? formatBarRange(
          selectedClip.timelineStartBeats,
          selectedClip.timelineStartBeats + selectedClip.durationBeats,
          project.timeSignature
        )
      : "Full timeline";

  const timeRangeSecLabel = selection.timeRangeBeats
    ? `${beatsToSeconds(selection.timeRangeBeats.startBeats, project.bpm).toFixed(2)}s – ${beatsToSeconds(
        selection.timeRangeBeats.endBeats,
        project.bpm
      ).toFixed(2)}s`
    : null;

  return (
    <aside className="sidebar-right" style={{ width }} data-testid="ai-producer-panel">
      <div className="panel-header">
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {t("producer.title")}
          <span
            style={{
              fontSize: 9,
              padding: "1px 5px",
              borderRadius: 3,
              background: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-muted)",
              textTransform: "none",
              letterSpacing: 0,
            }}
          >
            {t("producer.offline")}
          </span>
        </span>
        <button className="icon-btn" title={t("producer.collapseTooltip")} onClick={onCollapse}>
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="producer-body">
        {/* Live Project & Selection Context */}
        <div className="producer-card" data-testid="producer-context-card">
          <div className="producer-label">{t("producer.projectContext")}</div>
          <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)" }}>
            {selectedTrack ? `${selectedTrack.name} · ${barSummary}` : barSummary}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
            {selectedClip
              ? t("producer.clipSelected", {
                  kind: selectedClip.type === "midi" ? "MIDI" : selectedTrack?.type === "stem" ? "STEM" : "Audio",
                  name: selectedClip.name,
                })
              : selectedTrack
                ? t("producer.trackSelected", { kind: selectedTrack.type.toUpperCase() })
                : t("producer.selectPrompt")}
          </div>

          <div
            style={{
              borderTop: "1px solid var(--border-subtle)",
              marginTop: 4,
              paddingTop: 6,
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            <div className="producer-kv">
              <span style={{ color: "var(--text-muted)" }}>{t("producer.tempoMeter")}</span>
              <span className="mono">
                {project.bpm.toFixed(2)} BPM · {project.timeSignature.numerator}/{project.timeSignature.denominator}
              </span>
            </div>
            <div className="producer-kv">
              <span style={{ color: "var(--text-muted)" }}>{t("producer.section")}</span>
              <span>{activeSection ? activeSection.name : "—"}</span>
            </div>
            <div className="producer-kv">
              <span style={{ color: "var(--text-muted)" }}>{t("producer.selectedClips")}</span>
              <span className="mono">{selection.selectedClipIds.length}</span>
            </div>
            <div className="producer-kv">
              <span style={{ color: "var(--text-muted)" }}>{t("producer.revision")}</span>
              <span className="mono">rev {savedRevision}</span>
            </div>
            {timeRangeSecLabel && (
              <div className="producer-kv">
                <span style={{ color: "var(--text-muted)" }}>{t("producer.timeSpan")}</span>
                <span className="mono">{timeRangeSecLabel}</span>
              </div>
            )}
          </div>
        </div>

        {/* Honest AI Status Card */}
        <div className="producer-card dashed">
          <div style={{ fontWeight: 600, fontSize: 12, color: "var(--text-primary)" }}>
            {t("producer.aiStatusTitle")}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5 }}>
            {t("producer.aiStatusDesc")}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
            <Radio size={11} color="var(--text-muted)" />
            <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{t("producer.notConnected")}</span>
          </div>
        </div>

        {/* Inspectable Shared Command Payload */}
        <div className="producer-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span className="producer-label">{t("producer.payloadTitle")}</span>
            <button
              style={{ fontSize: 10, padding: "2px 6px" }}
              onClick={() => setShowPayload((s) => !s)}
            >
              <Code2 size={11} />
              {showPayload ? t("producer.hideJson") : t("producer.inspectJson")}
            </button>
          </div>
          {showPayload ? (
            <pre className="payload-pre">{JSON.stringify(commandPayload, null, 2)}</pre>
          ) : (
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{t("producer.payloadDesc")}</div>
          )}
        </div>

        {/* Audio Engine / REAPER Adapter Status */}
        <div style={{ fontSize: 10, color: "var(--text-muted)", padding: "2px 2px" }}>
          <div>{t("producer.engineWebAudio")}</div>
          <div>
            {health?.reaper.available ? t("producer.hostReaperFound") : t("producer.hostStandalone")}
          </div>
        </div>
      </div>

      {/* Bottom Prompt Box */}
      <div className="producer-footer">
        <textarea
          rows={2}
          placeholder={t("producer.inputPlaceholder")}
          value={draftPrompt}
          onChange={(e) => setDraftPrompt(e.target.value)}
          style={{
            width: "100%",
            resize: "none",
            padding: "7px 8px",
            fontSize: 11,
            background: "var(--bg-input)",
          }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{t("producer.notConnected")}</span>
          <button disabled>{t("producer.send")}</button>
        </div>
      </div>
    </aside>
  );
}
