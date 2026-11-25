import React, { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  Cpu,
  Disc3,
  Layers,
  Play,
  Plus,
  Radio,
  Send,
  Sparkles,
  Square,
  X,
  XCircle,
} from "lucide-react";
import { audioEngine } from "../audio/audioEngine";
import { useDaw } from "../commands/store";
import { isImeComposing, useI18n } from "../i18n";
import { beatsToSeconds, formatBarRange } from "../project/time";
import { dawApi } from "../project/api";
import type { ArrangementEditPlan, CompositionPlan } from "../project/types";

interface AIProducerPanelProps {
  width: number;
  onCollapse: () => void;
  onOpenReferenceTab: () => void;
}

interface ChatItem {
  id: string;
  role: "user" | "producer";
  text: string;
  ok?: boolean;
  plan?: CompositionPlan;
  arrangementPlan?: ArrangementEditPlan;
}

const TARGET_INSTRUMENT_OPTIONS = [
  { id: "synth_hook", ko: "신스 훅 (Synth Hook)", en: "Synth Hook" },
  { id: "drums", ko: "드럼 (Drums)", en: "Drums" },
  { id: "bass", ko: "베이스 (Bass)", en: "Bass" },
  { id: "keys", ko: "건반 (Electric Piano)", en: "Keys (EP)" },
  { id: "guitar", ko: "기타 (Clean Guitar)", en: "Guitar" },
  { id: "pad", ko: "웜 패드 (Pad)", en: "Warm Pad" },
];

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
    providerSummary,
    generationEngines,
    runtimeRegistry,
    activePlan,
    activeArrangementPlan,
    setActiveArrangementPlan,
    engineUnavailableNotice,
    dismissEngineUnavailableNotice,
    activeGenerationJob,
    takes,
    selectAiProvider,
    requestCompositionPlan,
    startGenerationFromPlan,
    cancelActiveGeneration,
    applyGeneratedTake,
    rejectGeneratedTake,
    executeArrangementPlan,
    showToast,
  } = useDaw();

  const [subTab, setSubTab] = useState<"chat" | "takes" | "engines">("chat");
  const [composeMode, setComposeMode] = useState<"auto" | "full_music" | "instrument_session" | "loop_midi">("auto");
  const [prodMode, setProdMode] = useState<"editable_midi" | "neural_audio" | "hybrid">("editable_midi");
  const [varIntensity, setVarIntensity] = useState<"subtle" | "moderate" | "creative">("moderate");
  const [runningVariation, setRunningVariation] = useState(false);
  const [targetInst, setTargetInst] = useState<string>("synth_hook");
  const [useRef, setUseRef] = useState<boolean>(true);
  const [draftPrompt, setDraftPrompt] = useState("");
  const [runningCmd, setRunningCmd] = useState(false);
  const [chatFeed, setChatFeed] = useState<ChatItem[]>([]);
  const [showDevDetails, setShowDevDetails] = useState(false);
  const [showPayload, setShowPayload] = useState(false);
  const [playingTakeKey, setPlayingTakeKey] = useState<string | null>(null);

  // Sync take preview button when audio stops naturally
  useEffect(() => {
    if (!playingTakeKey) return;
    const id = window.setInterval(() => {
      const st = audioEngine.getReferencePreviewState();
      if (!st.playingUrl) setPlayingTakeKey(null);
    }, 150);
    return () => window.clearInterval(id);
  }, [playingTakeKey]);

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
      commandSchemaVersion: "1.2.0",
      agentBridge: sseConnected ? "sse_live_mcp_ready" : "local_only",
      activeProvider: providerSummary?.activeProviderId ?? "local-music-director",
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
  }, [project, savedRevision, sseConnected, providerSummary, selection, selectedTrack, activeSection, activeReference, draftPrompt]);

  if (!project) return null;

  const isGenerating =
    activeGenerationJob &&
    !["ready_for_preview", "applied", "failed", "cancelled"].includes(activeGenerationJob.status);

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

  const appendChat = (item: Omit<ChatItem, "id">) => {
    setChatFeed((prev) => [...prev.slice(-18), { ...item, id: `${Date.now()}_${Math.random()}` }]);
  };

  const handleSubmitText = async (overrideText?: string, forcedMode?: "full_music" | "instrument_session" | "loop_midi") => {
    const prompt = (overrideText ?? draftPrompt).trim();
    if (!prompt || runningCmd) return;
    setRunningCmd(true);
    setSubTab("chat");
    appendChat({ role: "user", text: prompt });
    if (!overrideText) setDraftPrompt("");

    try {
      const effectiveMode = forcedMode ?? (composeMode === "auto" ? undefined : composeMode);
      // If user explicitly picked a Composition Mode, go straight to Composition Director!
      if (effectiveMode) {
        const plan = await requestCompositionPlan(prompt, {
          mode: effectiveMode,
          targetInstrument: effectiveMode === "full_music" ? undefined : targetInst,
          useReference: useRef,
        });
        if (plan) {
          appendChat({
            role: "producer",
            ok: true,
            text: locale === "ko" ? plan.summaryKo : plan.summaryEn,
            plan,
          });
        }
      } else {
        // Unified conversational router: handles DAW edits, Phase 04 selective arrangement, reference analysis, AND composition!
        const res = await submitProducerInstruction(prompt);
        if (res) {
          const msg = locale === "ko" ? res.messageKo || res.messageEn || "" : res.messageEn || res.messageKo || "";
          appendChat({
            role: "producer",
            ok: res.supported,
            text: msg,
            plan: res.plan,
            arrangementPlan: res.arrangementPlan,
          });
          if (res.action === "arrangement_edit_plan_created" && res.arrangementPlan) {
            setVarIntensity(res.arrangementPlan.intensity);
          }
          if (res.action === "analyze_reference") {
            onOpenReferenceTab();
          }
        }
      }
    } finally {
      setRunningCmd(false);
    }
  };

  const handleGenerate = async (plan: CompositionPlan, overrideEngine?: string) => {
    const engineChoice = overrideEngine ?? (prodMode === "neural_audio" ? "neural_audio" : "auto");
    const started = await startGenerationFromPlan(plan, engineChoice);
    if (started) setSubTab("takes");
  };

  const handleExecuteArrangement = async (plan: ArrangementEditPlan) => {
    if (runningVariation) return;
    setRunningVariation(true);
    try {
      const res = await executeArrangementPlan(plan, { intensity: varIntensity });
      if (res?.take) {
        setActiveArrangementPlan(null);
        setSubTab("takes");
      } else if (res?.applied) {
        setActiveArrangementPlan(null);
        appendChat({ role: "producer", ok: true, text: res.messageKo || plan.summaryKo });
      }
    } finally {
      setRunningVariation(false);
    }
  };

  const handleToggleTakePreview = async (
    takeId: string,
    variant: "solo" | "in_context" | "original_context",
    levelGainDb: number
  ) => {
    const playKey = `${takeId}:${variant}`;
    if (playingTakeKey === playKey) {
      audioEngine.stopReferencePreview();
      setPlayingTakeKey(null);
      return;
    }
    try {
      const url = dawApi.takeAudioUrl(project.id, takeId, variant);
      await audioEngine.playReferencePreview(url, 0, levelGainDb);
      setPlayingTakeKey(playKey);
    } catch (err) {
      showToast((err as Error).message, "error");
    }
  };

  const latestFeedback = chatFeed.filter((m) => m.role === "producer").slice(-1)[0] ?? null;
  const readyTakesCount = takes.filter((tk) => tk.status !== "rejected").length;

  return (
    <aside className="sidebar-right" style={{ width }} data-testid="ai-producer-panel">
      {/* Header */}
      <div className="panel-header">
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Sparkles size={12} color="var(--accent-playhead)" />
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

      {/* Compact 3-Tab Switcher (Music-first UX, Developer details tucked in Engines tab) */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          borderBottom: "1px solid var(--border-subtle)",
          background: "#16181c",
        }}
      >
        {(
          [
            { id: "chat", label: t("producer.tabChat") },
            { id: "takes", label: t("producer.tabTakes", { count: readyTakesCount }) },
            { id: "engines", label: t("producer.tabEngines") },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setSubTab(tab.id)}
            data-testid={`producer-tab-${tab.id}`}
            style={{
              height: 28,
              borderRadius: 0,
              border: "none",
              borderBottom: subTab === tab.id ? "2px solid var(--accent-playhead)" : "2px solid transparent",
              background: subTab === tab.id ? "var(--bg-surface)" : "transparent",
              color: subTab === tab.id ? "var(--text-primary)" : "var(--text-muted)",
              fontSize: 10.5,
              fontWeight: subTab === tab.id ? 600 : 500,
              justifyContent: "center",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Scrollable Body */}
      <div className="producer-body">
        {/* Pending AI / MCP Change Proposals (always visible at top when staged!) */}
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
                  padding: "6px 8px",
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

        {/* Active Generation Job Progress Banner */}
        {isGenerating && activeGenerationJob && (
          <div
            className="producer-card"
            style={{ borderColor: "var(--accent-play)", background: "rgba(99, 180, 124, 0.08)" }}
            data-testid="generation-job-banner"
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "#cdecd7" }}>
                {t("producer.generating", {
                  pct: activeGenerationJob.progress,
                  stage: activeGenerationJob.stage,
                })}
              </span>
              <button
                style={{ height: 20, padding: "0 6px", fontSize: 10 }}
                onClick={() => void cancelActiveGeneration()}
                data-testid="btn-cancel-generation"
              >
                <XCircle size={10} />
                {t("producer.cancelJob")}
              </button>
            </div>
            <div style={{ height: 4, background: "#121418", borderRadius: 2, overflow: "hidden" }}>
              <div
                style={{
                  width: `${activeGenerationJob.progress}%`,
                  height: "100%",
                  background: "var(--accent-play)",
                  transition: "width 180ms ease",
                }}
              />
            </div>
          </div>
        )}

        {/* TAB 1: CONVERSATIONAL COMPOSE & DIRECT */}
        {subTab === "chat" && (
          <>
            {/* Compact Live Scope & Reference Pill */}
            <div className="producer-card" style={{ padding: "7px 8px", gap: 5 }} data-testid="producer-context-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 4 }}>
                <span style={{ fontWeight: 600, fontSize: 11.5, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {selectedTrack ? `${selectedTrack.name} · ${barSummary}` : barSummary}
                </span>
                <span className="mono" style={{ fontSize: 10, color: "var(--text-muted)", flexShrink: 0 }}>
                  {project.bpm.toFixed(0)} BPM
                </span>
              </div>

              {/* Production Mode Selector (No Silent Substitution — Section 3.1) */}
              <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                {(
                  [
                    { id: "editable_midi", label: t("producer.prodModeMidi") },
                    { id: "neural_audio", label: t("producer.prodModeNeural") },
                    { id: "hybrid", label: t("producer.prodModeHybrid") },
                  ] as const
                ).map((pm) => (
                  <button
                    key={pm.id}
                    className={prodMode === pm.id ? "pill-toggle active" : ""}
                    style={{ height: 19, padding: "0 6px", fontSize: 9.5 }}
                    onClick={() => setProdMode(pm.id)}
                    data-testid={`prod-mode-${pm.id}`}
                  >
                    {pm.label}
                  </button>
                ))}
              </div>

              {/* Generation Mode Pills */}
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {(
                  [
                    { id: "auto", label: "Auto" },
                    { id: "full_music", label: t("producer.modeFull") },
                    { id: "instrument_session", label: t("producer.modeSession") },
                    { id: "loop_midi", label: t("producer.modeLoop") },
                  ] as const
                ).map((m) => (
                  <button
                    key={m.id}
                    className={composeMode === m.id ? "pill-toggle active" : ""}
                    style={{ height: 20, padding: "0 7px", fontSize: 10 }}
                    onClick={() => setComposeMode(m.id)}
                    data-testid={`mode-pill-${m.id}`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>

              {/* Instrument Target & Reference Toggle */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, flexWrap: "wrap" }}>
                {(composeMode === "instrument_session" || composeMode === "loop_midi") && (
                  <select
                    value={targetInst}
                    onChange={(e) => setTargetInst(e.target.value)}
                    style={{ height: 20, fontSize: 10, flex: 1 }}
                    data-testid="producer-target-inst"
                  >
                    {TARGET_INSTRUMENT_OPTIONS.map((o) => (
                      <option key={o.id} value={o.id}>
                        {locale === "ko" ? o.ko : o.en}
                      </option>
                    ))}
                  </select>
                )}

                {activeReference && (
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                      fontSize: 10,
                      color: activeReference.analysis ? "var(--text-secondary)" : "var(--text-muted)",
                      cursor: "pointer",
                    }}
                    data-testid="producer-ref-card"
                  >
                    <input
                      type="checkbox"
                      checked={useRef && Boolean(activeReference.analysis)}
                      disabled={!activeReference.analysis}
                      onChange={(e) => setUseRef(e.target.checked)}
                    />
                    <span style={{ maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {t("producer.useActiveRef")}: {activeReference.name}
                    </span>
                    <button
                      style={{ height: 18, padding: "0 5px", fontSize: 9 }}
                      onClick={(e) => {
                        e.preventDefault();
                        onOpenReferenceTab();
                      }}
                      data-testid="btn-open-ref-detail"
                    >
                      {t("producer.openRefDetail")}
                    </button>
                  </label>
                )}
              </div>
            </div>

            {/* Honest Engine Unavailable Banner (Never silently substitutes MIDI for Neural Audio!) */}
            {engineUnavailableNotice && (
              <div
                className="producer-card"
                style={{ borderColor: "var(--accent-danger)", background: "rgba(217, 92, 92, 0.1)" }}
                data-testid="engine-unavailable-banner"
              >
                <div style={{ fontSize: 10.5, fontWeight: 600, color: "#f2b8b8" }}>
                  {locale === "ko" ? engineUnavailableNotice.errorKo : engineUnavailableNotice.errorEn}
                </div>
                <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                  <button
                    className="pill-toggle active"
                    style={{ height: 22, padding: "0 8px", fontSize: 10 }}
                    data-testid="btn-switch-editable-midi"
                    onClick={async () => {
                      const targetPlan = engineUnavailableNotice.plan;
                      setProdMode("editable_midi");
                      dismissEngineUnavailableNotice();
                      await handleGenerate(targetPlan, "local-midi-composer");
                    }}
                  >
                    {t("producer.engineUnavailableSwitch")}
                  </button>
                  <button style={{ height: 22, padding: "0 7px", fontSize: 10 }} onClick={dismissEngineUnavailableNotice}>
                    <X size={10} />
                  </button>
                </div>
              </div>
            )}

            {/* Quick Musical Starters when Chat is Empty */}
            {chatFeed.length === 0 && !activePlan && !activeArrangementPlan && (
              <div className="producer-card" style={{ gap: 5 }}>
                <div className="producer-label">Quick Composition & Arrangement</div>
                <button
                  style={{ justifyContent: "flex-start", fontSize: 10.5, height: 26, padding: "0 8px" }}
                  onClick={() =>
                    void handleSubmitText(
                      "128 BPM 어두운 하우스 풀 트랙 만들어줘. 훅이 분명하고 인스트루멘탈로 구성해줘.",
                      "full_music"
                    )
                  }
                  data-testid="btn-quick-house"
                >
                  <Sparkles size={11} />
                  {t("producer.quickHouse")}
                </button>
                <button
                  style={{ justifyContent: "flex-start", fontSize: 10.5, height: 26, padding: "0 8px" }}
                  onClick={() =>
                    void handleSubmitText(
                      "드럼 5~8마디만 좀 더 다양하게 변주해줘. 마지막에는 필인을 넣어줘."
                    )
                  }
                  data-testid="btn-quick-drum-var"
                >
                  <Layers size={11} />
                  {t("producer.quickDrumVar")}
                </button>
                <button
                  style={{ justifyContent: "flex-start", fontSize: 10.5, height: 26, padding: "0 8px" }}
                  onClick={() =>
                    void handleSubmitText(
                      "신스 훅의 메인 멜로디는 유지하면서 후반부만 좀 더 인상적으로 바꿔줘."
                    )
                  }
                  data-testid="btn-quick-hook-var"
                >
                  <Sparkles size={11} />
                  {t("producer.quickHookVar")}
                </button>
                <button
                  style={{ justifyContent: "flex-start", fontSize: 10.5, height: 26, padding: "0 8px" }}
                  onClick={() =>
                    void handleSubmitText(
                      "현재 코드 진행에 맞는 4마디 신스 훅을 만들어줘. 기존 드럼과 베이스는 유지해줘.",
                      "loop_midi"
                    )
                  }
                  data-testid="btn-quick-hook"
                >
                  <Layers size={11} />
                  {t("producer.quickHook")}
                </button>
                {activeReference?.analysis && (
                  <button
                    style={{ justifyContent: "flex-start", fontSize: 10.5, height: 26, padding: "0 8px" }}
                    onClick={() =>
                      void handleSubmitText(
                        `선택한 레퍼런스(${activeReference.name})의 그루브와 전개 감각을 반영한 새 하우스 트랙을 작곡해줘.`,
                        "full_music"
                      )
                    }
                    data-testid="btn-quick-ref"
                  >
                    <Disc3 size={11} />
                    {t("producer.quickRef")}
                  </button>
                )}
              </div>
            )}

            {/* Conversational History */}
            {chatFeed.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }} data-testid="producer-chat-feed">
                {chatFeed.map((msg) => (
                  <div
                    key={msg.id}
                    style={{
                      padding: "6px 8px",
                      borderRadius: 5,
                      fontSize: 11,
                      lineHeight: 1.45,
                      alignSelf: msg.role === "user" ? "flex-end" : "stretch",
                      maxWidth: msg.role === "user" ? "92%" : "100%",
                      background:
                        msg.role === "user"
                          ? "rgba(100, 142, 168, 0.18)"
                          : msg.ok === false
                            ? "rgba(217, 92, 92, 0.12)"
                            : "var(--bg-surface)",
                      border: `1px solid ${
                        msg.role === "user"
                          ? "#4b6d82"
                          : msg.ok === false
                            ? "var(--accent-danger)"
                            : "var(--border-subtle)"
                      }`,
                      color: msg.ok === false ? "#f2b8b8" : "var(--text-primary)",
                    }}
                  >
                    {msg.text}
                  </div>
                ))}
              </div>
            )}

            {/* Active Phase 04 Arrangement Edit Plan Card */}
            {activeArrangementPlan && (
              <div
                className="producer-card"
                style={{ borderColor: "#7c9b86", background: "rgba(99, 180, 124, 0.08)" }}
                data-testid="arrangement-plan-card"
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="producer-label" style={{ color: "#a9e1ba" }}>
                    {t("producer.arrPlanTitle")}
                  </span>
                  <span className="tag-badge">{activeArrangementPlan.variationKind}</span>
                </div>

                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-primary)", lineHeight: 1.4 }}>
                  {locale === "ko" ? activeArrangementPlan.summaryKo : activeArrangementPlan.summaryEn}
                </div>

                <div className="mono" style={{ fontSize: 9.5, color: "var(--text-secondary)" }}>
                  Bars {activeArrangementPlan.scope.startBar}–{activeArrangementPlan.scope.endBarInclusive} ·{" "}
                  op: {activeArrangementPlan.operation}
                  {activeArrangementPlan.preserveFirstHalf ? " · 1st-half locked" : ""}
                  {activeArrangementPlan.addTurnaroundFill ? " · +Fill" : ""}
                </div>

                {/* Variation Intensity Selector */}
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <span style={{ fontSize: 9.5, color: "var(--text-muted)" }}>{t("producer.intensityLabel")}:</span>
                  {(["subtle", "moderate", "creative"] as const).map((lvl) => (
                    <button
                      key={lvl}
                      className={varIntensity === lvl ? "pill-toggle active" : ""}
                      style={{ height: 18, padding: "0 6px", fontSize: 9.5 }}
                      onClick={() => setVarIntensity(lvl)}
                      data-testid={`intensity-pill-${lvl}`}
                    >
                      {lvl}
                    </button>
                  ))}
                </div>

                <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                  {activeArrangementPlan.changes.map((c, idx) => (
                    <span key={idx} className="tag-badge">
                      {c}
                    </span>
                  ))}
                </div>

                <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
                  <button
                    className="btn-primary"
                    style={{ flex: 1, height: 26, justifyContent: "center", fontSize: 11 }}
                    disabled={runningVariation}
                    onClick={() => void handleExecuteArrangement(activeArrangementPlan)}
                    data-testid="btn-execute-arrangement"
                  >
                    <Sparkles size={11} />
                    {["extend_section", "strip_to_tracks", "audio_reverse", "audio_fade"].includes(
                      activeArrangementPlan.operation
                    )
                      ? t("producer.applyStructuralEdit")
                      : t("producer.runVariation")}
                  </button>
                  <button
                    style={{ height: 26, padding: "0 7px", fontSize: 10 }}
                    onClick={() => setActiveArrangementPlan(null)}
                  >
                    <X size={11} />
                  </button>
                </div>
              </div>
            )}

            {/* Active Composition Plan Card (Inspectable before Generate!) */}
            {activePlan && (
              <div
                className="producer-card"
                style={{ borderColor: "#506d80", background: "rgba(100, 142, 168, 0.08)" }}
                data-testid="composition-plan-card"
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="producer-label" style={{ color: "#9bc2d9" }}>
                    {t("producer.planTitle")}
                  </span>
                  <span className="tag-badge">{activePlan.mode}</span>
                </div>

                <div style={{ fontWeight: 600, fontSize: 12, color: "var(--text-primary)" }}>
                  {activePlan.musicalIdentity.title}
                </div>
                <div className="mono" style={{ fontSize: 10, color: "var(--text-secondary)" }}>
                  {activePlan.musicalIdentity.tempoBpm} BPM · {activePlan.musicalIdentity.key} ·{" "}
                  {activePlan.musicalIdentity.barCount} bars ({activePlan.musicalIdentity.durationSec}s)
                </div>

                {/* Chords & Motif */}
                <div style={{ fontSize: 10, color: "var(--text-secondary)", lineHeight: 1.4 }}>
                  <strong>Chords:</strong> {(activePlan.harmonyAndGroove.chordProgression ?? []).join(" – ")}
                  <br />
                  <strong>Motif:</strong> {activePlan.signatureMotif.concept}
                </div>

                {/* Planned Sections */}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                  {activePlan.arrangement.map((sec, idx) => (
                    <span key={idx} className="tag-badge" title={sec.transitionNote}>
                      {sec.name} ({sec.bars}b)
                    </span>
                  ))}
                </div>

                {/* Traceable Reference Binding */}
                {activePlan.referenceBinding.referenceIds.length > 0 && (
                  <div
                    style={{
                      fontSize: 9.5,
                      color: "#b7d3c4",
                      background: "rgba(99, 180, 124, 0.09)",
                      padding: "4px 6px",
                      borderRadius: 4,
                    }}
                  >
                    Ref: {activePlan.referenceBinding.referenceNames.join(", ")} →{" "}
                    {Object.keys(activePlan.referenceBinding.appliedFeatures).join(", ")}
                  </div>
                )}

                <button
                  className="btn-primary"
                  style={{ height: 28, justifyContent: "center", fontSize: 11, marginTop: 2 }}
                  disabled={Boolean(isGenerating)}
                  onClick={() => void handleGenerate(activePlan)}
                  data-testid="btn-generate-from-plan"
                >
                  <Sparkles size={12} />
                  {t("producer.generateFromPlan")}
                </button>
              </div>
            )}
          </>
        )}

        {/* TAB 2: GENERATED TAKES, LEVEL-MATCHED PREVIEW & TRANSACTIONAL APPLY */}
        {subTab === "takes" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }} data-testid="producer-takes-list">
            {takes.length === 0 ? (
              <div className="producer-card dashed" style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>
                {t("producer.takesEmpty")}
              </div>
            ) : (
              takes.map((take) => {
                const tech = (take.qualityReport?.technical ?? {}) as Record<string, unknown>;
                const ctxPrev = (tech.contextualPreview ?? null) as Record<string, unknown> | null;
                const lufsVal = tech.integratedLufs ?? take.previewIntegratedLufs;
                const tpVal = tech.truePeakDbtp;
                const isRejected = take.status === "rejected";
                const isPlayingSolo = playingTakeKey === `${take.id}:solo`;
                const isPlayingCtx = playingTakeKey === `${take.id}:in_context`;
                const isPlayingOrig = playingTakeKey === `${take.id}:original_context`;
                const isSingleOrVariation = take.mode === "midi_variation" || take.artifacts.length === 1;
                const effTargetTrackId = take.targetTrackId ?? selectedTrack?.id ?? null;
                return (
                  <div
                    key={take.id}
                    className="producer-card"
                    style={{
                      opacity: isRejected ? 0.55 : 1,
                      borderColor: take.status === "applied" ? "var(--accent-play)" : undefined,
                    }}
                    data-testid={`take-card-${take.id}`}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 4 }}>
                      <strong style={{ fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {take.title}
                      </strong>
                      <span
                        className="tag-badge"
                        style={{
                          color:
                            take.status === "applied"
                              ? "#a9e1ba"
                              : take.qualityReport?.verdict === "warn"
                                ? "#f0cf7b"
                                : "var(--text-secondary)",
                        }}
                      >
                        {take.status === "applied"
                          ? t("producer.takeApplied")
                          : take.status === "rejected"
                            ? t("producer.takeRejected")
                            : take.qualityReport?.verdict ?? "ready"}
                      </span>
                    </div>

                    {/* Honest Provenance & BS.1770-4 Metrics */}
                    <div className="mono" style={{ fontSize: 9.5, color: "var(--text-muted)" }}>
                      {take.provenance.engine} · {take.previewDurationSec.toFixed(1)}s ·{" "}
                      {typeof lufsVal === "number" ? `${lufsVal} LUFS` : "?"} ·{" "}
                      {typeof tpVal === "number" ? `TP ${tpVal} dBTP` : ""}
                    </div>

                    <div style={{ fontSize: 10, color: "var(--text-secondary)" }}>
                      {take.artifacts.map((a) => `${a.name} (${a.notes.length} notes)`).join(" · ")}
                    </div>

                    {/* Planned vs Detected Section Distinction */}
                    {(take.plannedSections.length > 0 || take.detectedSections.length > 0) && (
                      <div className="mono" style={{ fontSize: 9, color: "var(--text-muted)" }}>
                        Planned: {take.plannedSections.length} sec · Detected: {take.detectedSections.length} sec
                      </div>
                    )}

                    {/* Reference Comparison Observation if available */}
                    {take.qualityReport?.referenceComparison?.observations?.[0] && (
                      <div
                        style={{
                          fontSize: 9.5,
                          background: "#14161a",
                          borderLeft: "2px solid var(--accent-playhead)",
                          padding: "3px 6px",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {locale === "ko"
                          ? take.qualityReport.referenceComparison.observations[0].ko
                          : take.qualityReport.referenceComparison.observations[0].en}
                      </div>
                    )}

                    {/* Contextual Audition Row: Solo / In-Context / Original A/B (-16 LUFS matched) */}
                    {take.previewRelativePath && (
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 2 }}>
                        <button
                          className={isPlayingSolo ? "pill-toggle active" : ""}
                          style={{ height: 21, padding: "0 6px", fontSize: 9.5 }}
                          onClick={() => void handleToggleTakePreview(take.id, "solo", take.levelMatchedGainDb)}
                          data-testid={`btn-preview-take-${take.id}`}
                        >
                          {isPlayingSolo ? <Square size={9} fill="currentColor" /> : <Play size={9} fill="currentColor" />}
                          {isPlayingSolo
                            ? t("producer.stopPreview")
                            : ctxPrev
                              ? t("producer.previewSolo")
                              : t("producer.previewLevelMatched")}
                        </button>
                        {ctxPrev && (
                          <>
                            <button
                              className={isPlayingCtx ? "pill-toggle active" : ""}
                              style={{ height: 21, padding: "0 6px", fontSize: 9.5 }}
                              onClick={() =>
                                void handleToggleTakePreview(
                                  take.id,
                                  "in_context",
                                  Number(ctxPrev.inContextLevelMatchedGainDb ?? 0)
                                )
                              }
                              data-testid={`btn-preview-ctx-${take.id}`}
                            >
                              {isPlayingCtx ? <Square size={9} fill="currentColor" /> : <Play size={9} fill="currentColor" />}
                              {t("producer.previewInContext")}
                            </button>
                            <button
                              className={isPlayingOrig ? "pill-toggle active" : ""}
                              style={{ height: 21, padding: "0 6px", fontSize: 9.5 }}
                              onClick={() =>
                                void handleToggleTakePreview(
                                  take.id,
                                  "original_context",
                                  Number(ctxPrev.originalLevelMatchedGainDb ?? 0)
                                )
                              }
                              data-testid={`btn-preview-orig-${take.id}`}
                            >
                              {isPlayingOrig ? <Square size={9} fill="currentColor" /> : <Play size={9} fill="currentColor" />}
                              {t("producer.previewOriginal")}
                            </button>
                          </>
                        )}
                      </div>
                    )}

                    {/* Explicit Transactional Apply Controls (Replace / Take Lane / Add / Extend / Reject) */}
                    {!isRejected && (
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 2 }}>
                        {isSingleOrVariation && effTargetTrackId ? (
                          <>
                            <button
                              className="pill-toggle active"
                              style={{ height: 22, padding: "0 7px", fontSize: 9.5 }}
                              onClick={() => void applyGeneratedTake(take.id, "replace_range", effTargetTrackId)}
                              data-testid={`btn-apply-take-replace-${take.id}`}
                            >
                              <Check size={10} />
                              {t("producer.applyReplaceRange")}
                            </button>
                            <button
                              style={{ height: 22, padding: "0 7px", fontSize: 9.5 }}
                              onClick={() => void applyGeneratedTake(take.id, "alternative_take", effTargetTrackId)}
                              data-testid={`btn-apply-take-lane-${take.id}`}
                            >
                              <Layers size={10} />
                              {t("producer.applyAltTake")}
                            </button>
                            <button
                              style={{ height: 22, padding: "0 6px", fontSize: 9.5 }}
                              onClick={() => void applyGeneratedTake(take.id, "add")}
                              data-testid={`btn-apply-take-new-${take.id}`}
                            >
                              <Plus size={10} />
                              {t("producer.applyNewTracks")}
                            </button>
                            <button
                              style={{ height: 22, padding: "0 6px", fontSize: 9.5 }}
                              onClick={() => void applyGeneratedTake(take.id, "extend", effTargetTrackId)}
                              data-testid={`btn-apply-take-extend-${take.id}`}
                            >
                              {t("producer.applyExtend")}
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              className="pill-toggle active"
                              style={{ height: 22, padding: "0 7px", fontSize: 10 }}
                              onClick={() => void applyGeneratedTake(take.id, "new_tracks")}
                              data-testid={`btn-apply-take-new-${take.id}`}
                            >
                              <Plus size={10} />
                              {t("producer.applyNewTracks")}
                            </button>
                            <button
                              style={{ height: 22, padding: "0 7px", fontSize: 10 }}
                              onClick={() => void applyGeneratedTake(take.id, "new_project")}
                              data-testid={`btn-apply-take-newproj-${take.id}`}
                            >
                              {t("producer.applyNewProject")}
                            </button>
                          </>
                        )}
                        <button
                          style={{ height: 22, padding: "0 6px", fontSize: 10 }}
                          onClick={() => void rejectGeneratedTake(take.id)}
                          data-testid={`btn-reject-take-${take.id}`}
                        >
                          <X size={10} />
                          {t("producer.rejectTake")}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* TAB 3: HONEST PROVIDERS, GENERATION ENGINES & COLLAPSIBLE DEVELOPER DETAILS */}
        {subTab === "engines" && (
          <>
            {/* Providers (Honest 4-State Status: Verified / Authenticated / Ready for Client / Uninstalled) */}
            <div className="producer-card" data-testid="providers-card">
              <div className="producer-label">{t("producer.providersTitle")}</div>
              {(providerSummary?.providers ?? []).map((p) => {
                const isActive = providerSummary?.activeProviderId === p.id;
                const pState = p.providerState ?? p.status ?? (p.available ? "ready_for_client" : "uninstalled");
                const statusBadge =
                  pState === "verified"
                    ? "Verified"
                    : pState === "authenticated"
                      ? "Authenticated"
                      : pState === "ready_for_client"
                        ? "MCP Ready"
                        : pState === "detected"
                          ? "Detected"
                          : "Uninstalled";
                return (
                  <div
                    key={p.id}
                    style={{
                      padding: "5px 6px",
                      borderRadius: 4,
                      border: `1px solid ${isActive ? "var(--accent-play)" : "var(--border-subtle)"}`,
                      background: isActive ? "rgba(99, 180, 124, 0.08)" : "#15171b",
                      display: "flex",
                      flexDirection: "column",
                      gap: 3,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 4 }}>
                      <strong style={{ fontSize: 10.5 }}>{p.name}</strong>
                      <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                        <span
                          className="tag-badge"
                          data-testid={`provider-state-${p.id}`}
                          style={{
                            fontSize: 8.5,
                            color:
                              pState === "verified" || pState === "authenticated"
                                ? "#a9e1ba"
                                : pState === "ready_for_client"
                                  ? "#9bc2d9"
                                  : "var(--text-muted)",
                          }}
                        >
                          {statusBadge}
                        </span>
                        {p.available && (
                          <button
                            className={isActive ? "pill-toggle active" : ""}
                            style={{ height: 18, padding: "0 6px", fontSize: 9, flexShrink: 0, whiteSpace: "nowrap" }}
                            onClick={() => void selectAiProvider(p.id)}
                          >
                            {isActive ? "Active" : "Use"}
                          </button>
                        )}
                      </div>
                    </div>
                    <div style={{ fontSize: 9.5, color: "var(--text-muted)", lineHeight: 1.35 }}>
                      {locale === "ko" ? p.statusNoteKo : p.statusNoteEn}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* 6-State Shared Runtime Registry (YuE2 / ACE-Step / Demucs / Vocal QA / MIDI Composer) */}
            <div className="producer-card" data-testid="engines-card">
              <div className="producer-label">{t("producer.runtimeRegistryTitle")}</div>
              {runtimeRegistry?.engines?.length
                ? runtimeRegistry.engines.map((eng) => (
                    <div
                      key={eng.id}
                      style={{
                        padding: "5px 6px",
                        borderRadius: 4,
                        border: "1px solid var(--border-subtle)",
                        background: "#15171b",
                        display: "flex",
                        flexDirection: "column",
                        gap: 2,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 4 }}>
                        <span style={{ fontSize: 10.5, fontWeight: 600, display: "flex", alignItems: "center", gap: 4 }}>
                          <Cpu size={10} />
                          {eng.name}
                        </span>
                        <span
                          className="tag-badge"
                          style={{
                            color:
                              eng.state === "verified" || eng.state === "ready"
                                ? "#a9e1ba"
                                : eng.state === "binary_found" || eng.state === "model_found"
                                  ? "#f0cf7b"
                                  : "var(--text-muted)",
                            fontSize: 9,
                            flexShrink: 0,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {eng.state}
                        </span>
                      </div>
                      <div style={{ fontSize: 9.5, color: "var(--text-muted)", lineHeight: 1.35 }}>
                        {locale === "ko" ? eng.statusNoteKo : eng.statusNoteEn}
                      </div>
                    </div>
                  ))
                : generationEngines.map((eng) => (
                    <div
                      key={eng.id}
                      style={{
                        padding: "5px 6px",
                        borderRadius: 4,
                        border: "1px solid var(--border-subtle)",
                        background: "#15171b",
                        display: "flex",
                        flexDirection: "column",
                        gap: 2,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 10.5, fontWeight: 600, display: "flex", alignItems: "center", gap: 4 }}>
                          <Cpu size={10} />
                          {eng.name}
                        </span>
                        <span
                          className="tag-badge"
                          style={{ color: eng.available ? "#a9e1ba" : "var(--text-muted)", fontSize: 9 }}
                        >
                          {eng.available ? "Ready" : "Unavailable"}
                        </span>
                      </div>
                      <div style={{ fontSize: 9.5, color: "var(--text-muted)", lineHeight: 1.35 }}>
                        {locale === "ko" ? eng.statusNoteKo : eng.statusNoteEn}
                      </div>
                    </div>
                  ))}
            </div>

            {/* Collapsible Developer Details (Revision, Payload JSON, MCP, Host) */}
            <div className="producer-card">
              <button
                style={{
                  border: "none",
                  background: "transparent",
                  padding: 0,
                  justifyContent: "space-between",
                  width: "100%",
                  color: "var(--text-secondary)",
                  fontSize: 10.5,
                }}
                onClick={() => setShowDevDetails((v) => !v)}
                data-testid="btn-toggle-dev-details"
              >
                <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  {showDevDetails ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  {t("producer.devDetails")}
                </span>
                <span className="mono" data-testid="producer-revision" style={{ fontSize: 9.5, color: "var(--text-muted)" }}>
                  rev {savedRevision}
                </span>
              </button>

              {showDevDetails && (
                <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 4 }}>
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
                  {timeRangeSecLabel && (
                    <div className="producer-kv">
                      <span style={{ color: "var(--text-muted)" }}>{t("producer.timeSpan")}</span>
                      <span className="mono">{timeRangeSecLabel}</span>
                    </div>
                  )}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 2 }}>
                    <span className="producer-label">{t("producer.payloadTitle")}</span>
                    <button style={{ fontSize: 10, padding: "2px 6px" }} onClick={() => setShowPayload((s) => !s)}>
                      <Code2 size={11} />
                      {showPayload ? t("producer.hideJson") : t("producer.inspectJson")}
                    </button>
                  </div>
                  {showPayload && <pre className="payload-pre">{JSON.stringify(commandPayload, null, 2)}</pre>}
                  <div style={{ fontSize: 9.5, color: "var(--text-muted)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <Radio size={10} color={sseConnected ? "var(--accent-play)" : "var(--text-muted)"} />
                      {t("producer.engineWebAudio")}
                    </div>
                    <div>
                      {health?.reaper.available ? t("producer.hostReaperFound") : t("producer.hostStandalone")}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Bottom Conversational Composer & Command Box */}
      <div className="producer-footer">
        {latestFeedback && subTab !== "chat" && (
          <div
            data-testid="producer-feedback"
            style={{
              fontSize: 10,
              lineHeight: 1.35,
              padding: "4px 6px",
              borderRadius: 4,
              background: latestFeedback.ok === false ? "rgba(217, 92, 92, 0.12)" : "rgba(99, 180, 124, 0.12)",
              color: latestFeedback.ok === false ? "#f2b8b8" : "#cdecd7",
            }}
          >
            {latestFeedback.text}
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
              void handleSubmitText();
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
          <span style={{ fontSize: 9.5, color: "var(--text-muted)" }}>
            {providerSummary?.activeProviderId ?? "local-music-director"}
          </span>
          <button
            className="btn-primary"
            style={{ height: 24, padding: "0 10px", fontSize: 11 }}
            disabled={!draftPrompt.trim() || runningCmd}
            onClick={() => void handleSubmitText()}
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
