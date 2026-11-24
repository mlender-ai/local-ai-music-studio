import type {
  Asset,
  HealthInfo,
  LibraryItem,
  MidiNote,
  Project,
  ProjectSummary,
  WaveformData,
} from "./types";

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (err?.error) msg = err.error;
      else if (err?.detail) msg = String(err.detail);
    } catch {
      // ignore non-json error body
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

export const dawApi = {
  health(): Promise<HealthInfo> {
    return apiFetch("/api/health");
  },

  listProjects(): Promise<{ projects: ProjectSummary[] }> {
    return apiFetch("/api/projects");
  },

  createProject(params: {
    name: string;
    bpm?: number;
    numerator?: number;
    denominator?: number;
    lengthBeats?: number;
  }): Promise<Project> {
    return apiFetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
  },

  openProject(projectId: string): Promise<Project> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}`);
  },

  saveProject(project: Project): Promise<Project> {
    return apiFetch(`/api/projects/${encodeURIComponent(project.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(project),
    });
  },

  autosaveProject(project: Project): Promise<{ saved: boolean; updatedAt: string }> {
    return apiFetch(`/api/projects/${encodeURIComponent(project.id)}/autosave`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(project),
    });
  },

  saveAsProject(projectId: string, name: string, project: Project): Promise<Project> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/save-as`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, project }),
    });
  },

  renameProject(projectId: string, name: string): Promise<Project> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  },

  deleteProject(projectId: string): Promise<{ deleted: string }> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "DELETE",
    });
  },

  async importAsset(
    projectId: string,
    file: File,
    kind?: "audio" | "midi" | "reference"
  ): Promise<{ asset: Asset; midi?: { notes: MidiNote[]; bpm: number | null; durationBeats: number } }> {
    const form = new FormData();
    form.append("file", file);
    if (kind) form.append("kind", kind);
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/assets/import`, {
      method: "POST",
      body: form,
    });
  },

  assetFileUrl(projectId: string, assetId: string): string {
    return `/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/file`;
  },

  getWaveform(projectId: string, assetId: string, bins = 1024): Promise<WaveformData> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/waveform?bins=${bins}`
    );
  },

  listLibrary(): Promise<{ items: LibraryItem[] }> {
    return apiFetch("/api/library/assets");
  },

  importFromLibrary(
    projectId: string,
    libraryId: string,
    kind?: "audio" | "reference"
  ): Promise<{ asset: Asset; midi?: { notes: MidiNote[]; bpm: number | null; durationBeats: number } }> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/assets/import-library`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ libraryId, kind }),
    });
  },

  async uploadExportWav(
    projectId: string,
    filename: string,
    wavBlob: Blob
  ): Promise<{ filename: string; relativePath: string; bytes: number; sha256: string }> {
    const form = new FormData();
    form.append("file", wavBlob, filename);
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/exports`, {
      method: "POST",
      body: form,
    });
  },
};
