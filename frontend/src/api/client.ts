export type Domain = {
  domain_id: string;
  name: string;
  description: string;
  created_at?: string;
  document_count?: number;
  chunk_count?: number;
};

export type RagFile = {
  document_id: string;
  domain_id: string;
  source_file: string;
  ruleset_id: string;
  version: string;
  status: string;
  chunk_count: number;
  uploaded_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
};

export type FileContent = {
  fileName: string;
  extension: string;
  sizeBytes: number;
  mode: "text" | "image" | "pdf" | "office" | "binary" | "missing";
  text?: string;
  html?: string;
  imageDataUrl?: string;
  message?: string;
};

export type IngestionJob = {
  job_id: string;
  domain_id: string;
  source_file: string;
  status: string;
  message: string;
  chunk_count: number;
  created_at: string;
  updated_at: string;
};

export type ReviewUpload = {
  upload_id: string;
  source_file: string;
  content_type: string;
  size_bytes: number;
  stored_path: string;
  uploaded_at: string;
};

export type ReviewRunResult = {
  query: string;
  answer: string;
  evidence_count: number;
  citations: string[];
  confidence?: { score?: number; band?: string; reasons?: string[] };
  structured_output?: Record<string, unknown> | null;
  structured_error?: string | null;
  export_files?: Record<string, { file_name: string; mime: string; content: string; encoding?: string }>;
};

const RAG_API = import.meta.env.VITE_RAG_API_URL || "http://localhost:8601";
const REVIEW_API = import.meta.env.VITE_REVIEW_API_URL || "http://localhost:8602";
const API_KEY_PREFIX = "business-rule-ai.api-key.";

async function request<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed with ${response.status}`);
  }
  return data as T;
}

export const api = {
  ragBaseUrl: RAG_API,
  reviewBaseUrl: REVIEW_API,
  domains: () => request<{ domains: Domain[] }>(RAG_API, "/api/domains"),
  createDomain: (payload: { name: string; domainId?: string; description?: string }) =>
    request<{ domain: Domain }>(RAG_API, "/api/domains", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  ragFiles: (domainId: string, search = "") =>
    request<{ files: RagFile[] }>(RAG_API, `/api/rag/files?${new URLSearchParams({ domainId, search })}`),
  ragFile: (documentId: string, includeChunks = false) =>
    request<{ file: RagFile; content: FileContent; chunks?: unknown[]; chunksError?: string }>(
      RAG_API,
      `/api/rag/files/${documentId}${includeChunks ? "?includeChunks=1" : ""}`
    ),
  updateRagFileStatus: (documentId: string, status: "active" | "archived") =>
    request<{ file: RagFile; updated_chunks: number }>(RAG_API, `/api/rag/files/${documentId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status })
    }),
  uploadKnowledge: (form: FormData) =>
    request<{ results: Array<Record<string, unknown>>; succeeded: number; failed: number }>(RAG_API, "/api/rag/files", {
      method: "POST",
      body: form
    }),
  jobs: (limit = 40) => request<{ jobs: IngestionJob[] }>(RAG_API, `/api/rag/jobs?limit=${limit}`),
  stats: () =>
    request<{
      stats: {
        domain_count: number;
        document_count: number;
        active_count: number;
        archived_count: number;
        registered_chunks: number;
        vector_chunks: number;
      };
    }>(RAG_API, "/api/rag/stats"),
  settings: () =>
    request<{
      config: { provider: string; model: string; api_key_env_var: string; api_key_from_env: boolean };
      providers: string[];
      models: Record<string, string[]>;
      defaults: Record<string, string>;
      env_configured: Record<string, boolean>;
    }>(RAG_API, "/api/settings"),
  saveSettings: (payload: { provider: string; model: string; apiKey?: string; checkHealth?: boolean }) =>
    request<{ config: { provider: string; model: string }; health?: { ok: boolean; message: string } }>(
      RAG_API,
      "/api/settings",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }
    ),
  saveSessionApiKey: (provider: string, apiKey: string) => {
    if (!apiKey || typeof window === "undefined") return;
    window.sessionStorage.setItem(`${API_KEY_PREFIX}${provider}`, apiKey);
  },
  getSessionApiKey: (provider: string) => {
    if (typeof window === "undefined") return "";
    return window.sessionStorage.getItem(`${API_KEY_PREFIX}${provider}`) || "";
  },
  clearSessionApiKey: (provider: string) => {
    if (typeof window === "undefined") return;
    window.sessionStorage.removeItem(`${API_KEY_PREFIX}${provider}`);
  },
  reviewUploads: () => request<{ uploads: ReviewUpload[] }>(REVIEW_API, "/api/review/uploads"),
  uploadReviewFiles: (form: FormData) =>
    request<{ uploads: ReviewUpload[] }>(REVIEW_API, "/api/review/uploads", { method: "POST", body: form }),
  reviewUpload: (uploadId: string) =>
    request<{ upload: ReviewUpload; content: FileContent }>(REVIEW_API, `/api/review/uploads/${uploadId}`),
  runReview: (payload: { domainId: string; query: string; uploadIds: string[]; apiKey?: string }) =>
    request<{ result: ReviewRunResult }>(REVIEW_API, "/api/review/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
};
