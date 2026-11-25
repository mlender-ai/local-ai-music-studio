import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ChevronLeft,
  FileAudio,
  FolderOpen,
  Globe,
  Link2,
  Music,
  Play,
  Plus,
  RefreshCw,
  Search,
  Sliders,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { makeClientId } from "../commands/executor";
import { useDaw } from "../commands/store";
import { useI18n } from "../i18n";
import { dawApi } from "../project/api";
import type { FxCatalogEntry, InstrumentCatalogEntry } from "../project/types";

type BrowserCategory = "projects" | "references" | "audio" | "samples" | "instruments" | "effects";

interface ProjectBrowserProps {
  width: number;
  onCollapse: () => void;
  onOpenNewModal: () => void;
  onOpenReferenceTab: () => void;
  onOpenRefUrlModal: () => void;
  onOpenDeviceRack?: () => void;
}

function engineBadgeLabel(engine: string): { label: string; color: string } {
  if (engine === "pro_soundfont" || engine === "fluidsynth_sf3") return { label: "SF3", color: "#6db88a" };
  if (engine === "pro_synth") return { label: "SYNTH", color: "#d9b468" };
  if (engine === "pro_drum_rack" || engine === "drum_rack") return { label: "RACK", color: "#c9856b" };
  if (engine === "pro_sampler" || engine === "sampler") return { label: "SAMP", color: "#7ba7c9" };
  return { label: "PREV", color: "#9ba3b4" };
}

export function ProjectBrowser({
  width,
  onCollapse,
  onOpenNewModal,
  onOpenReferenceTab,
  onOpenRefUrlModal,
  onOpenDeviceRack,
}: ProjectBrowserProps) {
  const { locale, t } = useI18n();
  const {
    project,
    selectedTrack,
    setSelection,
    recentProjects,
    libraryItems,
    assetStates,
    activeReference,
    setActiveReferenceId,
    openProjectById,
    importFile,
    importReferenceFile,
    deleteReference,
    importLibraryAsset,
    addAssetToTimeline,
    retryAssetLoad,
    relinkAssetFile,
    dispatch,
    showToast,
  } = useDaw();

  const [category, setCategory] = useState<BrowserCategory>("audio");
  const [query, setQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const refFileInputRef = useRef<HTMLInputElement | null>(null);
  const relinkInputRef = useRef<HTMLInputElement | null>(null);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const [relinkTargetId, setRelinkTargetId] = useState<string | null>(null);
  const [instruments, setInstruments] = useState<InstrumentCatalogEntry[]>([]);
  const [fxCatalog, setFxCatalog] = useState<FxCatalogEntry[]>([]);
  const [previewingId, setPreviewingId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void dawApi
      .getInstrumentCatalog()
      .then((res) => {
        if (alive) setInstruments(res.instruments ?? []);
      })
      .catch(() => undefined);
    void dawApi
      .getFxCatalog()
      .then((res) => {
        if (alive) setFxCatalog(res.effects ?? []);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      previewAudioRef.current?.pause();
    };
  }, []);

  const q = query.trim().toLowerCase();

  const projectAssets = (project?.assets ?? []).filter((a) => {
    if (q && !a.name.toLowerCase().includes(q)) return false;
    if (category === "references") return a.kind === "reference";
    if (category === "audio") return true;
    return true;
  });

  const filteredLibrary = libraryItems.filter((item) => {
    if (q && !item.name.toLowerCase().includes(q) && !item.category.toLowerCase().includes(q)) {
      return false;
    }
    if (category === "references") return item.category === "studio-recordings";
    if (category === "samples") return item.category === "samples" || item.category === "midi";
    return true;
  });

  const filteredProjects = recentProjects.filter((p) => !q || p.name.toLowerCase().includes(q));

  const filteredInstruments = instruments.filter((inst) => {
    if (!q) return true;
    return (
      inst.name.toLowerCase().includes(q) ||
      (inst.nameKo ?? "").toLowerCase().includes(q) ||
      inst.category.toLowerCase().includes(q) ||
      inst.id.toLowerCase().includes(q)
    );
  });

  const filteredFx = fxCatalog.filter((fx) => {
    if (!q) return true;
    return (
      fx.name.toLowerCase().includes(q) ||
      (fx.nameKo ?? "").toLowerCase().includes(q) ||
      fx.category.toLowerCase().includes(q) ||
      fx.type.toLowerCase().includes(q)
    );
  });

  const handleFilePicked = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const kindHint = category === "references" ? "reference" : undefined;
    for (const file of Array.from(files)) {
      await importFile(file, kindHint, true);
    }
    e.target.value = "";
  };

  const handlePreviewInstrument = async (inst: InstrumentCatalogEntry) => {
    if (previewingId === inst.id) return;
    setPreviewingId(inst.id);
    try {
      const defaultPreset = inst.presetList?.[0]?.id ?? null;
      const blob = await dawApi.previewInstrumentBlob({
        instrumentRef: inst.id,
        presetId: defaultPreset,
      });
      const url = URL.createObjectURL(blob);
      previewAudioRef.current?.pause();
      const audio = new Audio(url);
      previewAudioRef.current = audio;
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setPreviewingId((cur) => (cur === inst.id ? null : cur));
      };
      await audio.play();
    } catch (err) {
      showToast((err as Error).message, "error");
      setPreviewingId(null);
    }
  };

  const handleAssignInstrument = (inst: InstrumentCatalogEntry) => {
    if (!project) return;
    const defaultPreset = inst.presetList?.[0]?.id ?? null;
    let targetTrackId = selectedTrack?.type === "midi" ? selectedTrack.id : null;

    if (!targetTrackId) {
      const existingMidi = project.tracks.find((tr) => tr.type === "midi");
      if (existingMidi && !selectedTrack) {
        targetTrackId = existingMidi.id;
      } else {
        targetTrackId = makeClientId("trk");
        dispatch({
          type: "track.add",
          payload: {
            id: targetTrackId,
            name: locale === "ko" ? inst.nameKo || inst.name : inst.name,
            type: "midi",
          },
        });
      }
    }

    dispatch({
      type: "track.setInstrument",
      payload: {
        trackId: targetTrackId,
        instrumentRef: inst.id,
        preset: defaultPreset,
      },
    });
    setSelection((prev) => ({ ...prev, selectedTrackId: targetTrackId }));
    onOpenDeviceRack?.();
    showToast(`${locale === "ko" ? inst.nameKo || inst.name : inst.name} 적용됨`);
  };

  const handleAddFx = (fx: FxCatalogEntry) => {
    if (!project) return;
    const targetTrack = selectedTrack ?? project.tracks[0];
    if (!targetTrack) {
      showToast(t("browser.selectTrackHint"), "error");
      return;
    }
    dispatch({
      type: "fx.add",
      payload: {
        trackId: targetTrack.id,
        slot: {
          id: makeClientId("fx"),
          type: fx.type,
          name: locale === "ko" ? fx.nameKo || fx.name : fx.name,
          nameKo: fx.nameKo,
          enabled: true,
          bypass: false,
          wetDry: 1.0,
          parameters: { ...(fx.defaultParams ?? {}) },
        },
      },
    });
    setSelection((prev) => ({ ...prev, selectedTrackId: targetTrack.id }));
    onOpenDeviceRack?.();
    showToast(`${targetTrack.name} ← ${locale === "ko" ? fx.nameKo || fx.name : fx.name}`);
  };

  return (
    <aside className="sidebar-left" style={{ width }} data-testid="project-browser">
      <div className="panel-header">
        <span>{t("browser.title")}</span>
        <div style={{ display: "flex", gap: 4 }}>
          <button
            className="icon-btn"
            title={t("browser.importTooltip")}
            onClick={() => fileInputRef.current?.click()}
            data-testid="btn-import-asset"
          >
            <Upload size={13} />
          </button>
          <button className="icon-btn" title={t("browser.collapseTooltip")} onClick={onCollapse}>
            <ChevronLeft size={14} />
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".wav,.mp3,.flac,.ogg,.aiff,.aif,.m4a,.mid,.midi"
        style={{ display: "none" }}
        onChange={(e) => void handleFilePicked(e)}
      />
      <input
        ref={refFileInputRef}
        type="file"
        accept=".wav,.mp3,.flac,.ogg,.aiff,.aif,.m4a,.mp4,.mov,.m4v,.webm"
        style={{ display: "none" }}
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (f) {
            const created = await importReferenceFile(f);
            if (created) onOpenReferenceTab();
          }
          e.target.value = "";
        }}
      />
      <input
        ref={relinkInputRef}
        type="file"
        accept=".wav,.mp3,.flac,.ogg,.aiff,.aif,.m4a,.mid,.midi"
        style={{ display: "none" }}
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (f && relinkTargetId) {
            await relinkAssetFile(relinkTargetId, f);
          }
          setRelinkTargetId(null);
          e.target.value = "";
        }}
      />

      <div className="browser-search">
        <div style={{ position: "relative" }}>
          <Search
            size={12}
            color="var(--text-muted)"
            style={{ position: "absolute", left: 8, top: 7, pointerEvents: "none" }}
          />
          <input
            type="text"
            placeholder={t("browser.searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ paddingLeft: 26 }}
          />
        </div>
      </div>

      <nav className="browser-nav" aria-label="Browser categories">
        <button
          className={`browser-nav-item ${category === "projects" ? "active" : ""}`}
          onClick={() => setCategory("projects")}
          data-testid="nav-projects"
        >
          <span>{t("browser.projects")}</span>
          <span className="tag-badge">{recentProjects.length}</span>
        </button>
        <button
          className={`browser-nav-item ${category === "references" ? "active" : ""}`}
          onClick={() => setCategory("references")}
          data-testid="nav-references"
        >
          <span>{t("browser.references")}</span>
          <span className="tag-badge">{project?.references?.length ?? 0}</span>
        </button>
        <button
          className={`browser-nav-item ${category === "audio" ? "active" : ""}`}
          onClick={() => setCategory("audio")}
          data-testid="nav-audio-files"
        >
          <span>{t("browser.audioFiles")}</span>
          <span className="tag-badge">{project?.assets.length ?? 0}</span>
        </button>
        <button
          className={`browser-nav-item ${category === "samples" ? "active" : ""}`}
          onClick={() => setCategory("samples")}
        >
          <span>{t("browser.samplesMidi")}</span>
          <span className="tag-badge">{libraryItems.length}</span>
        </button>
        <button
          className={`browser-nav-item ${category === "instruments" ? "active" : ""}`}
          onClick={() => setCategory("instruments")}
          data-testid="nav-instruments"
        >
          <span>{t("browser.instruments")}</span>
          <span className="tag-badge">{instruments.length || "—"}</span>
        </button>
        <button
          className={`browser-nav-item ${category === "effects" ? "active" : ""}`}
          onClick={() => setCategory("effects")}
          data-testid="nav-effects"
        >
          <span>{t("browser.effects")}</span>
          <span className="tag-badge">{fxCatalog.length || "—"}</span>
        </button>
      </nav>

      {/* Projects View */}
      {category === "projects" && (
        <>
          <div className="browser-section-title">
            <span>{t("browser.recentProjects")}</span>
            <button className="icon-btn" title={t("transport.newTooltip")} onClick={onOpenNewModal}>
              <Plus size={12} />
            </button>
          </div>
          <div className="browser-list">
            {filteredProjects.map((p) => (
              <div
                key={p.id}
                className={`browser-item ${project?.id === p.id ? "active" : ""}`}
                onClick={() => void openProjectById(p.id)}
                title={`${p.bpm} BPM · ${t("browser.tracksShort", { count: p.trackCount })}`}
              >
                <FolderOpen size={13} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="browser-item-name" style={{ fontWeight: project?.id === p.id ? 600 : 400 }}>
                    {p.name}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }} className="mono">
                    {p.bpm} BPM · {t("browser.tracksShort", { count: p.trackCount })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Phase 05 Real Instrument Library (FluidSynth SF3 · Pro Synth · Drum Rack · Sampler) */}
      {category === "instruments" && (
        <>
          <div className="browser-section-title">
            <span>{t("browser.instrumentsTitle")}</span>
            <span className="mono">{filteredInstruments.length}</span>
          </div>
          <div className="browser-list" data-testid="instrument-browser-list">
            {filteredInstruments.map((inst) => {
              const badge = engineBadgeLabel(inst.engineType);
              const isAssigned = selectedTrack?.instrumentRef === inst.id;
              return (
                <div
                  key={inst.id}
                  className={`browser-item ${isAssigned ? "active" : ""}`}
                  onDoubleClick={() => handleAssignInstrument(inst)}
                  title={`${inst.name} (${inst.engineType}) · ${inst.license ?? ""}`}
                  data-testid={`browser-inst-${inst.id}`}
                >
                  <Sparkles size={11} color={badge.color} style={{ flexShrink: 0 }} />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="browser-item-name" style={{ fontWeight: isAssigned ? 600 : 400 }}>
                      {locale === "ko" ? inst.nameKo || inst.name : inst.name}
                    </div>
                    <div style={{ fontSize: 9, color: "var(--text-muted)", display: "flex", gap: 4 }}>
                      <span style={{ color: badge.color, fontWeight: 700 }}>{badge.label}</span>
                      <span>{inst.presetList?.length ?? 0} presets</span>
                    </div>
                  </div>
                  <button
                    className="icon-btn"
                    title={t("browser.previewBtn")}
                    data-testid={`btn-preview-inst-${inst.id}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      void handlePreviewInstrument(inst);
                    }}
                  >
                    <Play size={10} color={previewingId === inst.id ? "var(--accent-playhead)" : undefined} />
                  </button>
                  <button
                    className="icon-btn"
                    title={t("browser.assignTrack")}
                    data-testid={`btn-assign-inst-${inst.id}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleAssignInstrument(inst);
                    }}
                  >
                    <Plus size={11} />
                  </button>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Phase 05 Real FX Library (Pedalboard C++ DSP · Convolution IR · External Sidechain · Tube Amp) */}
      {category === "effects" && (
        <>
          <div className="browser-section-title">
            <span>{t("browser.effectsTitle")}</span>
            <span className="mono">{filteredFx.length}</span>
          </div>
          <div style={{ padding: "2px 10px 4px", fontSize: 9.5, color: "var(--text-muted)" }}>
            {selectedTrack ? t("browser.targetTrack", { name: selectedTrack.name }) : t("browser.selectTrackHint")}
          </div>
          <div className="browser-list" data-testid="fx-browser-list">
            {filteredFx.map((fx) => (
              <div
                key={fx.type}
                className="browser-item"
                onDoubleClick={() => handleAddFx(fx)}
                title={`${fx.name} · ${fx.engine}`}
                data-testid={`browser-fx-${fx.type}`}
              >
                <Sliders size={11} color="#85c49b" style={{ flexShrink: 0 }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="browser-item-name">
                    {locale === "ko" ? fx.nameKo || fx.name : fx.name}
                  </div>
                  <div style={{ fontSize: 9, color: "var(--text-muted)" }}>{fx.category}</div>
                </div>
                <button
                  className="icon-btn"
                  title={t("browser.addFxToTrack")}
                  data-testid={`btn-add-fx-${fx.type}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleAddFx(fx);
                  }}
                >
                  <Plus size={11} />
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Dedicated References View (separate from Export tracks!) */}
      {category === "references" && (
        <>
          <div className="browser-section-title">
            <span>{t("browser.references")}</span>
            <div style={{ display: "flex", gap: 4 }}>
              <button
                style={{ fontSize: 10, padding: "2px 6px" }}
                onClick={() => refFileInputRef.current?.click()}
                data-testid="btn-import-ref-file"
              >
                {t("browser.importRefFile")}
              </button>
              <button
                style={{ fontSize: 10, padding: "2px 6px" }}
                onClick={onOpenRefUrlModal}
                data-testid="btn-add-ref-url"
              >
                {t("browser.addRefUrl")}
              </button>
            </div>
          </div>
          <div style={{ padding: "2px 10px 4px", fontSize: 10, color: "var(--text-muted)" }}>
            {t("browser.refExcludedNote")}
          </div>
          <div className="browser-list">
            {(project?.references ?? []).length === 0 ? (
              <div style={{ padding: "8px 6px", color: "var(--text-muted)", fontSize: 11 }}>
                {t("browser.refEmpty")}
              </div>
            ) : (
              (project?.references ?? [])
                .filter((r) => !q || r.name.toLowerCase().includes(q))
                .map((ref) => {
                  const isSel = activeReference?.id === ref.id;
                  return (
                    <div
                      key={ref.id}
                      className={`browser-item ${isSel ? "active" : ""}`}
                      onClick={() => {
                        setActiveReferenceId(ref.id);
                        onOpenReferenceTab();
                      }}
                      data-testid={`ref-item-${ref.id}`}
                    >
                      {ref.kind === "url" ? (
                        <Globe size={12} color="var(--text-muted)" />
                      ) : (
                        <Activity size={12} color="#b89458" />
                      )}
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div className="browser-item-name" style={{ fontWeight: isSel ? 600 : 400 }}>
                          {ref.name}
                        </div>
                        <div style={{ fontSize: 9, color: "var(--text-muted)" }}>
                          {ref.analysisStatus === "completed"
                            ? `${ref.analysis?.rhythm.estimatedBpm ?? "?"} BPM · ${ref.analysis?.harmony.estimatedKey ?? ""}`
                            : ref.audioAvailable
                              ? t("browser.refAnalyze")
                              : t("browser.refUrlOnly")}
                        </div>
                      </div>
                      <button
                        className="icon-btn"
                        title={t("browser.refDelete")}
                        onClick={(e) => {
                          e.stopPropagation();
                          void deleteReference(ref.id);
                        }}
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                  );
                })
            )}
          </div>
        </>
      )}

      {/* Project Assets + Studio Library */}
      {(category === "audio" || category === "samples") && (
        <>
          <div className="browser-section-title">
            <span>{t("browser.projectAssets")}</span>
            <button
              style={{ fontSize: 10, padding: "2px 6px" }}
              onClick={() => fileInputRef.current?.click()}
            >
              + {t("browser.import")}
            </button>
          </div>
          <div className="browser-list" style={{ maxHeight: "42%" }}>
            {projectAssets.length === 0 ? (
              <div style={{ padding: "8px 6px", color: "var(--text-muted)", fontSize: 11 }}>
                {t("browser.emptyAssets")}
              </div>
            ) : (
              projectAssets.map((asset) => {
                const st = assetStates[asset.id];
                const isErr = st?.status === "error";
                return (
                  <div
                    key={asset.id}
                    className="browser-item"
                    style={isErr ? { borderColor: "var(--accent-danger)" } : undefined}
                    onDoubleClick={() => addAssetToTimeline(asset)}
                    title={
                      isErr
                        ? t("browser.audioError", { error: st.error || "decode error" })
                        : `${asset.provenance}\n${t("browser.addToTimeline")}`
                    }
                  >
                    {isErr ? (
                      <AlertTriangle size={12} color="var(--accent-danger)" />
                    ) : asset.kind === "midi" ? (
                      <Music size={12} color="#648ea8" />
                    ) : (
                      <FileAudio size={12} color="#6a997c" />
                    )}
                    <span className="browser-item-name">{asset.name}</span>
                    {isErr ? (
                      <>
                        <button
                          className="icon-btn"
                          title={t("browser.retryLoad")}
                          onClick={(e) => {
                            e.stopPropagation();
                            void retryAssetLoad(asset.id);
                          }}
                        >
                          <RefreshCw size={11} />
                        </button>
                        <button
                          className="icon-btn"
                          title={t("browser.relinkFile")}
                          onClick={(e) => {
                            e.stopPropagation();
                            setRelinkTargetId(asset.id);
                            relinkInputRef.current?.click();
                          }}
                        >
                          <Link2 size={11} />
                        </button>
                      </>
                    ) : (
                      <button
                        className="icon-btn"
                        title={t("browser.addToTimeline")}
                        onClick={(e) => {
                          e.stopPropagation();
                          addAssetToTimeline(asset);
                        }}
                      >
                        <Plus size={12} />
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>

          <div className="browser-section-title" style={{ borderTop: "1px solid var(--border-subtle)" }}>
            <span>{t("browser.studioLibrary")}</span>
            <span className="mono">{filteredLibrary.length}</span>
          </div>
          <div className="browser-list">
            {filteredLibrary.map((item) => (
              <div
                key={item.id}
                className="browser-item"
                onDoubleClick={() => void importLibraryAsset(item, true)}
                title={`${item.category} · ${(item.sizeBytes / 1024).toFixed(0)} KB · ${t("browser.importAndAdd")}`}
              >
                {item.kind === "midi" ? (
                  <Music size={12} color="#648ea8" />
                ) : (
                  <FileAudio size={12} color="#b89458" />
                )}
                <span className="browser-item-name">{item.name}</span>
                <button
                  className="icon-btn"
                  title={t("browser.importAndAdd")}
                  onClick={(e) => {
                    e.stopPropagation();
                    void importLibraryAsset(item, true);
                  }}
                >
                  <Plus size={12} />
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}
