import React, { useRef, useState } from "react";
import {
  AlertTriangle,
  ChevronLeft,
  FileAudio,
  FolderOpen,
  Link2,
  Music,
  Plus,
  RefreshCw,
  Search,
  Upload,
} from "lucide-react";
import { useDaw } from "../commands/store";

type BrowserCategory = "projects" | "references" | "audio" | "samples" | "instruments" | "effects";

interface ProjectBrowserProps {
  width: number;
  onCollapse: () => void;
  onOpenNewModal: () => void;
}

export function ProjectBrowser({ width, onCollapse, onOpenNewModal }: ProjectBrowserProps) {
  const {
    project,
    recentProjects,
    libraryItems,
    assetStates,
    openProjectById,
    importFile,
    importLibraryAsset,
    addAssetToTimeline,
    retryAssetLoad,
    relinkAssetFile,
  } = useDaw();

  const [category, setCategory] = useState<BrowserCategory>("audio");
  const [query, setQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
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
        <span>Browser</span>
        <div style={{ display: "flex", gap: 4 }}>
          <button
            className="icon-btn"
            title="Import Audio (.wav/.mp3/.flac) or MIDI (.mid)"
            onClick={() => fileInputRef.current?.click()}
            data-testid="btn-import-asset"
          >
            <Upload size={13} />
          </button>
          <button className="icon-btn" title="Collapse Browser" onClick={onCollapse}>
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
            placeholder="Search sounds..."
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
        >
          <span>Projects</span>
          <span className="tag-badge">{recentProjects.length}</span>
        </button>
        <button
          className={`browser-nav-item ${category === "references" ? "active" : ""}`}
          onClick={() => setCategory("references")}
        >
          <span>References</span>
        </button>
        <button
          className={`browser-nav-item ${category === "audio" ? "active" : ""}`}
          onClick={() => setCategory("audio")}
        >
          <span>Audio Files</span>
          <span className="tag-badge">{project?.assets.length ?? 0}</span>
        </button>
        <button
          className={`browser-nav-item ${category === "samples" ? "active" : ""}`}
          onClick={() => setCategory("samples")}
        >
          <span>Samples & MIDI</span>
          <span className="tag-badge">{libraryItems.length}</span>
        </button>
        <button
          className={`browser-nav-item ${category === "instruments" ? "active" : ""}`}
          onClick={() => setCategory("instruments")}
        >
          <span>Instruments</span>
          <span className="tag-badge">P05</span>
        </button>
        <button
          className={`browser-nav-item ${category === "effects" ? "active" : ""}`}
          onClick={() => setCategory("effects")}
        >
          <span>Effects</span>
          <span className="tag-badge">P05</span>
        </button>
      </nav>

      {/* Projects View */}
      {category === "projects" && (
        <>
          <div className="browser-section-title">
            <span>Recent Projects</span>
            <button className="icon-btn" title="New Project" onClick={onOpenNewModal}>
              <Plus size={12} />
            </button>
          </div>
          <div className="browser-list">
            {filteredProjects.map((p) => (
              <div
                key={p.id}
                className={`browser-item ${project?.id === p.id ? "active" : ""}`}
                onClick={() => void openProjectById(p.id)}
                title={`${p.bpm} BPM · ${p.trackCount} tracks · Click to open`}
              >
                <FolderOpen size={13} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="browser-item-name" style={{ fontWeight: project?.id === p.id ? 600 : 400 }}>
                    {p.name}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }} className="mono">
                    {p.bpm} BPM · {p.trackCount} trk
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
            {category === "instruments" ? "Virtual Instruments" : "Audio Effects & FX Rack"}
          </div>
          {category === "instruments" ? (
            <>
              Phase 01 includes a built-in <strong>Basic Poly Synth</strong> for MIDI clip auditioning and export.
              Full Sampler, Synthesizer, and AU/VST3 hosting arrive in Phase 05.
            </>
          ) : (
            <>
              EQ, Compressor, Delay, Reverb, and AU/VST3 FX Rack integration are scheduled for Phase 05.
            </>
          )}
        </div>
      )}

      {/* Project Assets + Studio Library */}
      {(category === "audio" || category === "samples" || category === "references") && (
        <>
          <div className="browser-section-title">
            <span>Project Assets</span>
            <button
              style={{ fontSize: 10, padding: "2px 6px" }}
              onClick={() => fileInputRef.current?.click()}
            >
              + Import
            </button>
          </div>
          <div className="browser-list" style={{ maxHeight: "42%" }}>
            {projectAssets.length === 0 ? (
              <div style={{ padding: "8px 6px", color: "var(--text-muted)", fontSize: 11 }}>
                No project assets yet. Click <strong>+ Import</strong> to add WAV, MP3, FLAC, or MIDI.
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
                        ? `Audio Error: ${st.error}\nRetry or relink source file.`
                        : `${asset.provenance}\nDouble-click or click + to place on timeline`
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
                          title="Retry loading audio"
                          onClick={(e) => {
                            e.stopPropagation();
                            void retryAssetLoad(asset.id);
                          }}
                        >
                          <RefreshCw size={11} />
                        </button>
                        <button
                          className="icon-btn"
                          title="Relink missing audio file"
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
                        title="Add to Timeline at Playhead"
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
            <span>Studio Library</span>
            <span className="mono">{filteredLibrary.length}</span>
          </div>
          <div className="browser-list">
            {filteredLibrary.map((item) => (
              <div
                key={item.id}
                className="browser-item"
                onDoubleClick={() => void importLibraryAsset(item, true)}
                title={`${item.category} · ${(item.sizeBytes / 1024).toFixed(0)} KB · Click + to import onto timeline`}
              >
                {item.kind === "midi" ? (
                  <Music size={12} color="#648ea8" />
                ) : (
                  <FileAudio size={12} color="#b89458" />
                )}
                <span className="browser-item-name">{item.name}</span>
                <button
                  className="icon-btn"
                  title="Import into Project & Add to Timeline"
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
