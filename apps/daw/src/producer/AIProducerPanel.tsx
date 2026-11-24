import React, { useMemo, useState } from "react";
import { Check, ChevronRight, Code2, Radio, Send, X } from "lucide-react";
import { useDaw } from "../commands/store";
import { isImeComposing, useI18n } from "../i18n";
import { beatsToSeconds, formatBarRange } from "../project/time";

interface AIProducerPanelProps {
  width: number;
  onCollapse: () => void;
  onOpenReferenceTab: () => void;
}

export function AIProducerPanel({ width, onCollapse, onOpenReferenceTab }: AIProducerPanelProps) {
  const { locale, t } = useI18n();
  const {
    project,
    selection,
    selectedTrack,
    selectedClip,
    health,
    savedRevision,
    activeReference,
    sseConnected,
    pendingProposals,
    applyPendingProposal,
    rejectPendingProposal,
    submitProducerInstruction,
  } = useDaw();

  const [draftPrompt, setDraftPrompt] = useState("");
  const [showPayload, setShowPayload] = useState(false);
  const [runningCmd, setRunningCmd] = useState(false);
  const [lastFeedback, setLastFeedback] = useState<{ ok: boolean; text: string } | null>(null);

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
      commandSchemaVersion: "1.1.0",
      agentBridge: sseConnected ? "sse_live_mcp_ready" : "local_only",
      projectId: project.id,
      revision: savedRevision,
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
      activeReferenceId: activeReference?.id ?? null,
      draftInstruction: draftPrompt.trim() || null,
    };
  }, [project, savedRevision, sseConnected, selection, selectedTrack, activeSection, activeReference, draftPrompt]);

  if (!project) return null;

  const barSummary = selection.timeRangeBeats
    ? formatBarRange(selection.timeRangeBeats.startBeats, selection.timeRangeBeats.endBeats, project.timeSignature)
    : selectedClip
      ? formatBarRange(
          selectedClip.timelineStartBeats,
          selectedClip.timelineStartBeats + selectedClip.durationBeats,
          project.timeSignature
        )
      : t("producer.fullTimeline");

  const timeRangeSecLabel = selection.timeRangeBeats
    ? `${beatsToSeconds(selection.timeRangeBeats.startBeats, project.bpm).toFixed(2)}s – ${beatsToSeconds(
        selection.timeRangeBeats.endBeats,
        project.bpm
      ).toFixed(2)}s`
    : null;

  const handleSubmit = async () => {
    if (!draftPrompt.trim() || runningCmd) return;
    setRunningCmd(true);
    const res = await submitProducerInstruction(draftPrompt);
    setRunningCmd(false);
    if (res) {
      const msg = locale === "ko" ? res.messageKo || res.messageEn || "" : res.messageEn || res.messageKo || "";
      setLastFeedback({ ok: res.supported, text: msg });
      if (res.supported) {
        setDraftPrompt("");
        if (res.action === "analyze_reference") {
          onOpenReferenceTab();
        }
      }
    }
  };

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
              background: sseConnected ? "rgba(99, 180, 124, 0.14)" : "var(--bg-surface)",
              border: `1px solid ${sseConnected ? "var(--accent-play)" : "var(--border-subtle)"}`,
              color: sseConnected ? "#a9e1ba" : "var(--text-muted)",
              textTransform: "none",
              letterSpacing: 0,
            }}
            data-testid="agent-bridge-badge"
          >
            {sseConnected ? t("producer.connected") : t("producer.offline")}
          </span>
        </span>
        <button className="icon-btn" title={t("producer.collapseTooltip")} onClick={onCollapse}>
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="producer-body">
        {/* Pending AI / External MCP Change Proposals */}
        {pendingProposals.length > 0 && (
          <div
            className="producer-card"
            style={{ borderColor: "var(--accent-playhead)", background: "rgba(229, 184, 75, 0.06)" }}
            data-testid="pending-proposals-card"
          >
            <div className="producer-label" style={{ color: "var(--accent-playhead)" }}>
              {t("producer.pendingProposals", { count: pendingProposals.length })}
            </div>
            {pendingProposals.map((prop) => (
              <div
                key={prop.id}
                style={{
                  background: "var(--bg-panel)",
                  border: "1px solid var(--border-default)",
                  borderRadius: 4,
                  padding: "7px 8px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 5,
                }}
                data-testid={`proposal-${prop.id}`}
              >
                <div style={{ fontWeight: 600, fontSize: 11, color: "var(--text-primary)" }}>
                  {prop.summary}
                </div>
                <div className="mono" style={{ fontSize: 9, color: "var(--text-muted)" }}>
                  {prop.sourceAgent} · rev {prop.baseRevision} · {prop.operationCount} op(s)
                  {prop.affectedTracks.length > 0 ? ` · ${prop.affectedTracks.join(", ")}` : ""}
                </div>
                <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                  <button
                    style={{ height: 22, padding: "0 8px", fontSize: 10 }}
                    onClick={() => void rejectPendingProposal(prop.id)}
                    data-testid={`btn-reject-${prop.id}`}
                  >
                    <X size={11} />
                    {t("producer.rejectProposal")}
                  </button>
                  <button
                    className="pill-toggle active"
                    style={{ height: 22, padding: "0 8px", fontSize: 10 }}
                    onClick={() => void applyPendingProposal(prop.id)}
                    data-testid={`btn-apply-${prop.id}`}
                  >
                    <Check size={11} />
                    {t("producer.applyProposal")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

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
              <span className="mono" data-testid="producer-revision">rev {savedRevision}</span>
            </div>
            {timeRangeSecLabel && (
              <div className="producer-kv">
                <span style={{ color: "var(--text-muted)" }}>{t("producer.timeSpan")}</span>
                <span className="mono">{timeRangeSecLabel}</span>
              </div>
            )}
          </div>
        </div>

        {/* Active Reference Summary Card */}
        {activeReference && (
          <div className="producer-card" data-testid="producer-ref-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="producer-label">{t("producer.refSummary")}</span>
              <button
                style={{ fontSize: 10, padding: "2px 6px" }}
                onClick={onOpenReferenceTab}
                data-testid="btn-open-ref-detail"
              >
                {t("producer.openRefDetail")}
              </button>
            </div>
            <div
              style={{
                fontWeight: 600,
                fontSize: 12,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {activeReference.name}
            </div>
            {activeReference.analysis ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <div className="producer-kv">
                  <span style={{ color: "var(--text-muted)" }}>BPM / Key</span>
                  <span className="mono">
                    {activeReference.analysis.rhythm.estimatedBpm ?? "?"} BPM ·{" "}
                    {activeReference.analysis.harmony.estimatedKey}
                  </span>
                </div>
                <div className="producer-kv">
                  <span style={{ color: "var(--text-muted)" }}>{t("producer.section")}</span>
                  <span className="mono">
                    {activeReference.analysis.arrangement.sections.length} 구간 ·{" "}
                    {activeReference.selectedInfluences?.length ?? 0} 특성 선택
                  </span>
                </div>
              </div>
            ) : (
              <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                {activeReference.audioAvailable ? t("browser.refAnalyze") : t("ref.urlOnlyNotice")}
              </div>
            )}
          </div>
        )}

        {/* Agent Bridge & MCP Info */}
        <div className="producer-card dashed">
          <div style={{ fontWeight: 600, fontSize: 12, color: "var(--text-primary)" }}>
            {t("producer.aiStatusTitle")}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.45 }}>
            {t("producer.aiStatusDesc")}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
            <Radio size={11} color={sseConnected ? "var(--accent-play)" : "var(--text-muted)"} />
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

        <div style={{ fontSize: 10, color: "var(--text-muted)", padding: "2px 2px" }}>
          <div>{t("producer.engineWebAudio")}</div>
          <div>
            {health?.reaper.available ? t("producer.hostReaperFound") : t("producer.hostStandalone")}
          </div>
        </div>
      </div>

      {/* Bottom Korean/English Supported Command Box */}
      <div className="producer-footer">
        {lastFeedback && (
          <div
            data-testid="producer-feedback"
            style={{
              fontSize: 10,
              lineHeight: 1.4,
              padding: "5px 7px",
              borderRadius: 4,
              background: lastFeedback.ok ? "rgba(99, 180, 124, 0.12)" : "rgba(217, 92, 92, 0.12)",
              border: `1px solid ${lastFeedback.ok ? "var(--accent-play)" : "var(--accent-danger)"}`,
              color: lastFeedback.ok ? "#cdecd7" : "#f2b8b8",
            }}
          >
            {lastFeedback.text}
          </div>
        )}
        <textarea
          rows={2}
          placeholder={t("producer.inputPlaceholder")}
          value={draftPrompt}
          onChange={(e) => setDraftPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (!isImeComposing(e) && e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSubmit();
            }
          }}
          data-testid="producer-input"
          style={{
            width: "100%",
            resize: "none",
            padding: "7px 8px",
            fontSize: 11,
            background: "var(--bg-input)",
          }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 9.5, color: "var(--text-muted)" }}>{t("producer.notConnected")}</span>
          <button
            className="btn-primary"
            style={{ height: 24, padding: "0 10px", fontSize: 11 }}
            disabled={!draftPrompt.trim() || runningCmd}
            onClick={() => void handleSubmit()}
            data-testid="btn-producer-send"
          >
            <Send size={11} />
            {t("producer.send")}
          </button>
        </div>
      </div>
    </aside>
  );
}
