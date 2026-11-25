import type {
  AnalysisJobStatus,
  ArrangementEditPlan,
  Asset,
  ChangeProposal,
  CompositionPlan,
  GenerationEngineInfo,
  GenerationJobStatus,
  HealthInfo,
  LibraryItem,
  MidiNote,
  ProducerInstructResponse,
  Project,
  ProjectSummary,
  ProviderSummary,
  ReferenceComparisonResult,
  ReferenceItem,
  RuntimeRegistryInfo,
  SelectionContext,
  Take,
  WaveformData,
} from "./types";

export class RevisionConflictError extends Error {
  serverRevision: number;
  serverProject: Project;

  constructor(message: string, serverRevision: number, serverProject: Project) {
    super(message);
    this.name = "RevisionConflictError";
    this.serverRevision = serverRevision;
    this.serverProject = serverProject;
  }
}

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    let payload: Record<string, unknown> | null = null;
    try {
      payload = (await res.json()) as Record<string, unknown>;
      if (typeof payload?.error === "string") msg = payload.error;
      else if (payload?.detail) msg = String(payload.detail);
    } catch {
      // ignore non-json error body
    }
    if (res.status === 409 && payload?.code === "REVISION_CONFLICT" && payload.serverProject) {
      throw new RevisionConflictError(
        msg,
        Number(payload.serverRevision ?? 0),
        payload.serverProject as Project
      );
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

  saveProject(project: Project, expectedRevision?: number): Promise<Project> {
    const q = expectedRevision !== undefined ? `?expectedRevision=${expectedRevision}` : "";
    return apiFetch(`/api/projects/${encodeURIComponent(project.id)}${q}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(project),
    });
  },

  autosaveProject(
    project: Project,
    expectedRevision?: number
  ): Promise<{ saved: boolean; revision: number; updatedAt: string }> {
    const q = expectedRevision !== undefined ? `?expectedRevision=${expectedRevision}` : "";
    return apiFetch(`/api/projects/${encodeURIComponent(project.id)}/autosave${q}`, {
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
  ): Promise<{
    asset: Asset;
    projectRevision?: number;
    midi?: { notes: MidiNote[]; bpm: number | null; durationBeats: number };
  }> {
    const form = new FormData();
    form.append("file", file);
    if (kind) form.append("kind", kind);
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/assets/import`, {
      method: "POST",
      body: form,
    });
  },

  async relinkAsset(
    projectId: string,
    assetId: string,
    file: File
  ): Promise<{ asset: Asset; projectRevision: number }> {
    const form = new FormData();
    form.append("file", file);
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/relink`,
      {
        method: "POST",
        body: form,
      }
    );
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
  ): Promise<{
    asset: Asset;
    projectRevision?: number;
    midi?: { notes: MidiNote[]; bpm: number | null; durationBeats: number };
  }> {
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

  async importReferenceFile(
    projectId: string,
    file: File,
    attachToRefId?: string
  ): Promise<{ reference: ReferenceItem; projectRevision: number }> {
    const form = new FormData();
    form.append("file", file);
    if (attachToRefId) form.append("attachToRefId", attachToRefId);
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/references/import`, {
      method: "POST",
      body: form,
    });
  },

  addReferenceUrl(
    projectId: string,
    url: string
  ): Promise<{ reference: ReferenceItem; projectRevision: number }> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/references/url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
  },

  deleteReference(projectId: string, refId: string): Promise<{ deleted: string; projectRevision: number }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/references/${encodeURIComponent(refId)}`,
      { method: "DELETE" }
    );
  },

  referenceAudioUrl(projectId: string, refId: string): string {
    return `/api/projects/${encodeURIComponent(projectId)}/references/${encodeURIComponent(refId)}/audio`;
  },

  startReferenceAnalysis(
    projectId: string,
    refId: string,
    sync = false
  ): Promise<{ job?: AnalysisJobStatus; reference?: ReferenceItem; projectRevision?: number }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/references/${encodeURIComponent(refId)}/analyze?sync=${sync}`,
      { method: "POST" }
    );
  },

  getAnalysisJob(jobId: string): Promise<AnalysisJobStatus> {
    return apiFetch(`/api/analysis/jobs/${encodeURIComponent(jobId)}`);
  },

  cancelAnalysisJob(jobId: string): Promise<AnalysisJobStatus> {
    return apiFetch(`/api/analysis/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
  },

  updateReferenceBlueprint(
    projectId: string,
    refId: string,
    body: { selectedInfluences?: string[]; sectionRenames?: Record<string, string> }
  ): Promise<{ reference: ReferenceItem; projectRevision: number }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/references/${encodeURIComponent(refId)}/blueprint`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
  },

  compareReference(
    projectId: string,
    refId: string,
    targetKind: "project_mix" | "asset",
    targetId?: string
  ): Promise<ReferenceComparisonResult> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/references/${encodeURIComponent(refId)}/compare`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targetKind, targetId }),
      }
    );
  },

  syncSessionState(body: {
    sessionId: string;
    projectId: string | null;
    revision: number | null;
    selection: SelectionContext;
    activeReferenceId: string | null;
    locale: string;
    claimActive?: boolean;
  }): Promise<Record<string, unknown>> {
    return apiFetch("/api/session/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  listProposals(projectId: string, status = "pending"): Promise<{ proposals: ChangeProposal[] }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/proposals?status=${encodeURIComponent(status)}`
    );
  },

  applyProposal(
    projectId: string,
    proposalId: string
  ): Promise<{ proposal: ChangeProposal; project: Project }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/proposals/${encodeURIComponent(proposalId)}/apply`,
      { method: "POST" }
    );
  },

  rejectProposal(projectId: string, proposalId: string): Promise<{ proposal: ChangeProposal }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/proposals/${encodeURIComponent(proposalId)}/reject`,
      { method: "POST" }
    );
  },

  sendProducerInstruction(
    projectId: string,
    body: {
      instruction: string;
      selection: SelectionContext;
      activeReferenceId: string | null;
      baseRevision: number;
    }
  ): Promise<ProducerInstructResponse> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/producer/instruct`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  // --- Phase 03: Providers, Composition Plans, Generation Jobs & Takes ---

  getProviders(): Promise<ProviderSummary> {
    return apiFetch("/api/providers");
  },

  selectProvider(providerId: string, model?: string): Promise<ProviderSummary> {
    return apiFetch("/api/providers/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ providerId, model }),
    });
  },

  getGenerationEngines(): Promise<{ engines: GenerationEngineInfo[] }> {
    return apiFetch("/api/generation/engines");
  },

  getRuntimeRegistry(): Promise<RuntimeRegistryInfo> {
    return apiFetch("/api/runtime");
  },

  createCompositionPlan(
    projectId: string,
    body: {
      instruction: string;
      mode?: string;
      targetInstrument?: string;
      referenceIds?: string[];
      selectedInfluences?: string[];
      selection?: SelectionContext;
      providerId?: string;
      enginePreference?: string;
    }
  ): Promise<{ plan: CompositionPlan; projectRevision: number }> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/composition/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  startGenerationJob(
    projectId: string,
    body: {
      planId?: string;
      instruction?: string;
      mode?: string;
      targetInstrument?: string;
      referenceIds?: string[];
      selectedInfluences?: string[];
      selection?: SelectionContext;
      engine?: string;
      seed?: number;
      sync?: boolean;
    }
  ): Promise<{
    job?: GenerationJobStatus;
    take?: Take;
    engineUnavailable?: boolean;
    requestedEngine?: string;
    errorKo?: string;
    errorEn?: string;
  }> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/generation/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  getGenerationJob(jobId: string): Promise<GenerationJobStatus> {
    return apiFetch(`/api/generation/jobs/${encodeURIComponent(jobId)}`);
  },

  cancelGenerationJob(jobId: string): Promise<GenerationJobStatus> {
    return apiFetch(`/api/generation/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
  },

  retryGenerationJob(jobId: string): Promise<{ job: GenerationJobStatus }> {
    return apiFetch(`/api/generation/jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST" });
  },

  listTakes(projectId: string): Promise<{ takes: Take[] }> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/takes`);
  },

  takeAudioUrl(
    projectId: string,
    takeId: string,
    variant: "solo" | "in_context" | "original_context" = "solo"
  ): string {
    const q = variant !== "solo" ? `?variant=${encodeURIComponent(variant)}` : "";
    return `/api/projects/${encodeURIComponent(projectId)}/takes/${encodeURIComponent(takeId)}/audio${q}`;
  },

  applyTake(
    projectId: string,
    takeId: string,
    body: {
      applyMode:
        | "add"
        | "new_tracks"
        | "replace_range"
        | "selected_range"
        | "alternative_take"
        | "extend"
        | "new_project"
        | "keep_take";
      targetTrackId?: string | null;
      startBeats?: number;
      addSectionMarkers?: boolean;
      replaceSections?: boolean;
      expectedRevision?: number;
      forceReapply?: boolean;
    }
  ): Promise<{
    applied: boolean;
    applyMode?: string;
    take: Take;
    project: Project;
    revision?: number;
    createdNewProject?: boolean;
  }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/takes/${encodeURIComponent(takeId)}/apply`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
  },

  rejectTake(projectId: string, takeId: string): Promise<{ take: Take; projectRevision: number }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/takes/${encodeURIComponent(takeId)}/reject`,
      { method: "POST" }
    );
  },

  // --- Phase 04: Selective Arrangement, Variations, Take Lanes, Audio Reverse & Music Memory ---

  createArrangementPlan(
    projectId: string,
    body: {
      instruction: string;
      selection?: SelectionContext;
      intensity?: "subtle" | "moderate" | "creative";
      targetTrackId?: string | null;
      startBeats?: number;
      endBeats?: number;
      providerId?: string;
    }
  ): Promise<{ plan: ArrangementEditPlan; projectRevision: number }> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/arrangement/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  executeArrangementPlan(
    projectId: string,
    body: {
      plan?: ArrangementEditPlan;
      instruction?: string;
      selection?: SelectionContext;
      intensity?: "subtle" | "moderate" | "creative";
      targetTrackId?: string | null;
      startBeats?: number;
      endBeats?: number;
      seed?: number;
    }
  ): Promise<{
    applied?: boolean;
    operation?: string;
    messageKo?: string;
    plan?: ArrangementEditPlan;
    take?: Take;
    contextualPreview?: Record<string, unknown>;
    project?: Project;
    revision?: number;
  }> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/arrangement/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  promoteTakeLane(
    projectId: string,
    trackId: string,
    laneId: string,
    body?: { startBeats?: number; endBeats?: number }
  ): Promise<{ promoted: boolean; laneId: string; insertedClipIds: string[]; project: Project; revision: number }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/tracks/${encodeURIComponent(trackId)}/take-lanes/${encodeURIComponent(laneId)}/promote`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      }
    );
  },

  restoreOriginalTakeLane(
    projectId: string,
    trackId: string,
    laneId?: string
  ): Promise<{ promoted: boolean; project: Project; revision: number }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/tracks/${encodeURIComponent(trackId)}/take-lanes/restore-original`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ laneId }),
      }
    );
  },

  renameTakeLane(
    projectId: string,
    trackId: string,
    laneId: string,
    name: string
  ): Promise<{ renamed: boolean; project: Project; revision: number }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/tracks/${encodeURIComponent(trackId)}/take-lanes/${encodeURIComponent(laneId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }
    );
  },

  reverseAudioClip(
    projectId: string,
    clipId: string,
    expectedRevision?: number
  ): Promise<{ reversed: boolean; newAsset: Asset; project: Project; revision: number }> {
    return apiFetch(
      `/api/projects/${encodeURIComponent(projectId)}/clips/${encodeURIComponent(clipId)}/reverse`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expectedRevision }),
      }
    );
  },

  getMusicMemory(projectId: string): Promise<{ projectId: string; musicMemory: Record<string, unknown> }> {
    return apiFetch(`/api/projects/${encodeURIComponent(projectId)}/memory`);
  },
};
