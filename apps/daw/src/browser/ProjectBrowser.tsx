import React, { useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ChevronLeft,
  FileAudio,
  FolderOpen,
  Globe,
  Link2,
  Music,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { useDaw } from "../commands/store";
import { useI18n } from "../i18n";

type BrowserCategory = "projects" | "references" | "audio" | "samples" | "instruments" | "effects";

interface ProjectBrowserProps {
  width: number;
  onCollapse: () => void;
  onOpenNewModal: () => void;
  onOpenReferenceTab: () => void;
  onOpenRefUrlModal: () => void;
}

export function ProjectBrowser({
  width,
  onCollapse,
  onOpenNewModal,
  onOpenReferenceTab,
  onOpenRefUrlModal,
}: ProjectBrowserProps) {
  const { t } = useI18n();
  const {
    project,
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
  } = useDaw();

  const [category, setCategory] = useState<BrowserCategory>("audio");
  const [query, setQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const refFileInputRef = useRef<HTMLInputElement | null>(null);
  const relinkInputRef = useRef<HTMLInputElement | null>(null);
  const [relinkTargetId, setRelinkTargetId] = useState<string | null>(null);

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

  const handleFilePicked = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const kindHint = category === "references" ? "reference" : undefined;
    for (const file of Array.from(files)) {
      await importFile(file, kindHint, true);
    }
    e.target.value = "";
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
        >
          <span>{t("browser.instruments")}</span>
          <span className="tag-badge">P05</span>
        </button>
        <button
          className={`browser-nav-item ${category === "effects" ? "active" : ""}`}
          onClick={() => setCategory("effects")}
        >
          <span>{t("browser.effects")}</span>
          <span className="tag-badge">P05</span>
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

      {/* Instruments / Effects honest Phase 05 notice */}
      {(category === "instruments" || category === "effects") && (
        <div style={{ padding: 12, color: "var(--text-muted)", fontSize: 11, lineHeight: 1.5 }}>
          <div style={{ color: "var(--text-secondary)", fontWeight: 600, marginBottom: 6 }}>
            {category === "instruments" ? t("browser.instrumentsTitle") : t("browser.effectsTitle")}
          </div>
          {category === "instruments" ? t("browser.instrumentsDesc") : t("browser.effectsDesc")}
        </div>
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
