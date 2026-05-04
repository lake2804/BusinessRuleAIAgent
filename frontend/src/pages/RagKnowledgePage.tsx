import { Archive, Database, Download, Eye, FolderPlus, Loader2, RefreshCw, Search, UploadCloud, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, Domain, FileContent, IngestionJob, RagFile } from "../api/client";
import { PreviewOverlay } from "../components/PreviewOverlay";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { UploadDropzone } from "../components/UploadDropzone";
import { fileExtension, formatBytes, formatDate } from "../utils/format";

const KNOWLEDGE_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".xlsm", ".txt", ".md", ".csv", ".json"];

export function RagKnowledgePage({
  routeDomainId,
  navigate
}: {
  routeDomainId: string;
  navigate: (path: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [files, setFiles] = useState<RagFile[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [stats, setStats] = useState({ domain_count: 0, document_count: 0, active_count: 0, archived_count: 0, registered_chunks: 0, vector_chunks: 0 });
  const [search, setSearch] = useState("");
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [selectedContent, setSelectedContent] = useState<FileContent | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [rulesetName, setRulesetName] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [message, setMessage] = useState("");
  const [progress, setProgress] = useState({ label: "Idle", percent: 0 });
  const [newDomain, setNewDomain] = useState({ name: "", domainId: "", description: "" });

  const selectedDomain = useMemo(() => domains.find((domain) => domain.domain_id === routeDomainId), [domains, routeDomainId]);
  const selectedFile = selectedIndex === null ? null : files[selectedIndex] || null;

  async function loadOverview() {
    const [domainData, jobData, statData] = await Promise.all([api.domains(), api.jobs(), api.stats()]);
    setDomains(domainData.domains);
    setJobs(jobData.jobs);
    setStats(statData.stats);
  }

  async function loadFiles(domainId = routeDomainId) {
    if (!domainId) {
      setFiles([]);
      return;
    }
    setFiles((await api.ragFiles(domainId, search)).files);
  }

  async function refresh() {
    await loadOverview();
    await loadFiles();
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error.message));
  }, [routeDomainId]);

  useEffect(() => {
    loadFiles().catch((error) => setMessage(error.message));
  }, [routeDomainId, search]);

  useEffect(() => {
    if (!selectedFile) {
      setSelectedContent(null);
      return;
    }
    setBusy(true);
    api.ragFile(selectedFile.document_id)
      .then((data) => setSelectedContent(data.content))
      .catch((error) => setMessage(error.message))
      .finally(() => setBusy(false));
  }, [selectedFile]);

  function addFiles(nextFiles: File[]) {
    const accepted = nextFiles.filter((file) => KNOWLEDGE_EXTENSIONS.includes(fileExtension(file.name)));
    const rejected = nextFiles.length - accepted.length;
    setUploadFiles((current) => {
      const map = new Map<string, File>();
      [...current, ...accepted].forEach((file) => map.set(`${file.name}:${file.size}:${file.lastModified}`, file));
      return Array.from(map.values());
    });
    setMessage(rejected ? `${rejected} unsupported file(s) skipped.` : "");
  }

  async function createDomain(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const data = await api.createDomain(newDomain);
      setNewDomain({ name: "", domainId: "", description: "" });
      setMessage(`Created domain ${data.domain.name}`);
      await loadOverview();
      navigate(`/rag/${encodeURIComponent(data.domain.domain_id)}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to create domain");
    } finally {
      setBusy(false);
    }
  }

  async function ingest(event: FormEvent) {
    event.preventDefault();
    if (!routeDomainId || !rulesetName.trim() || !uploadFiles.length) {
      setMessage("Enter a ruleset name and choose files.");
      return;
    }
    const form = new FormData();
    form.append("domainId", routeDomainId);
    form.append("rulesetName", rulesetName);
    form.append("version", version || "1.0.0");
    uploadFiles.forEach((file) => form.append("files", file));
    setBusy(true);
    setMessage("");
    setProgress({ label: "Uploading files", percent: 10 });
    const timer = window.setInterval(async () => {
      const data = await api.jobs().catch(() => null);
      if (!data) return;
      setJobs(data.jobs);
      const activeJob = data.jobs.find((job) => job.domain_id === routeDomainId && uploadFiles.some((file) => file.name === job.source_file));
      if (activeJob) setProgress({ label: activeJob.message || activeJob.status, percent: activeJob.status === "succeeded" ? 95 : 45 });
    }, 1200);
    try {
      const result = await api.uploadKnowledge(form);
      setMessage(`${result.succeeded} succeeded, ${result.failed} failed`);
      setProgress({ label: "Ingestion complete", percent: 100 });
      setUploadFiles([]);
      await refresh();
    } catch (error) {
      setProgress({ label: "Failed", percent: 100 });
      setMessage(error instanceof Error ? error.message : "Ingestion failed");
    } finally {
      window.clearInterval(timer);
      setBusy(false);
    }
  }

  function move(delta: number) {
    setSelectedIndex((current) => Math.min(Math.max((current || 0) + delta, 0), files.length - 1));
  }

  if (!routeDomainId) {
    return (
      <section className="p-5 lg:p-8">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">RAG Domains</h1>
            <p className="mt-1 text-sm text-slate-500">Create a domain or open an existing one to manage its knowledge files.</p>
          </div>
          <button onClick={loadOverview} className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:border-slate-500">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </header>
        <div className="mt-6 grid gap-4 md:grid-cols-4">
          <StatCard label="Domains" value={stats.domain_count} icon={<Database className="h-4 w-4 text-slate-400" />} />
          <StatCard label="Documents" value={stats.document_count} />
          <StatCard label="Active files" value={stats.active_count} />
          <StatCard label="Vector chunks" value={stats.vector_chunks} />
        </div>
        {message && <div className="mt-5 rounded-md border border-slate-200 bg-white px-4 py-3 text-sm">{message}</div>}
        <div className="mt-6 grid gap-5 xl:grid-cols-[420px_minmax(0,1fr)]">
          <form onSubmit={createDomain} className="rounded-lg border border-slate-200 bg-white p-5">
            <div className="flex items-center gap-2 text-sm font-semibold"><FolderPlus className="h-4 w-4" />Create domain</div>
            <input value={newDomain.name} onChange={(event) => setNewDomain({ ...newDomain, name: event.target.value })} placeholder="Domain name" className="mt-4 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input value={newDomain.domainId} onChange={(event) => setNewDomain({ ...newDomain, domainId: event.target.value })} placeholder="domain_id (optional)" className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <textarea value={newDomain.description} onChange={(event) => setNewDomain({ ...newDomain, description: event.target.value })} placeholder="Description" rows={4} className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <button disabled={busy} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white disabled:opacity-60">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FolderPlus className="h-4 w-4" />}
              Create and open
            </button>
          </form>
          <div className="rounded-lg border border-slate-200 bg-white">
            <div className="border-b border-slate-200 px-4 py-3 text-sm font-semibold">Existing domains</div>
            <div className="grid divide-y divide-slate-200">
              {domains.map((domain) => (
                <button key={domain.domain_id} onClick={() => navigate(`/rag/${encodeURIComponent(domain.domain_id)}`)} className="flex items-center justify-between gap-4 px-4 py-4 text-left hover:bg-slate-50">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold">{domain.name}</div>
                    <div className="mt-1 truncate font-mono text-xs text-slate-500">{domain.domain_id}</div>
                    <div className="mt-1 text-xs text-slate-500">{domain.description || "No description"}</div>
                  </div>
                  <div className="text-right text-xs text-slate-500">
                    <div>{domain.document_count || 0} files</div>
                    <div>{domain.chunk_count || 0} chunks</div>
                  </div>
                </button>
              ))}
              {!domains.length && <div className="px-4 py-12 text-center text-sm text-slate-500">No domains created yet.</div>}
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="p-5 lg:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <button onClick={() => navigate("/rag")} className="mb-2 text-sm font-medium text-slate-500 hover:text-slate-950">Back to domains</button>
          <h1 className="text-2xl font-semibold">{selectedDomain?.name || routeDomainId}</h1>
          <p className="mt-1 text-sm text-slate-500">{selectedDomain?.description || "Domain detail workspace"}</p>
        </div>
        <button onClick={refresh} className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:border-slate-500">
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </header>
      {message && <div className="mt-5 rounded-md border border-slate-200 bg-white px-4 py-3 text-sm">{message}</div>}
      <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
            <div>
              <div className="text-sm font-semibold">Knowledge files</div>
              <div className="text-xs text-slate-500">{files.length} stored files in this domain</div>
            </div>
            <label className="flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm">
              <Search className="h-4 w-4 text-slate-400" />
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search files" className="w-52 outline-none" />
            </label>
          </div>
          <div className="grid divide-y divide-slate-200">
            {files.map((file, index) => (
              <div key={file.document_id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-slate-50">
                <button onClick={() => setSelectedIndex(index)} className="flex min-w-0 items-center gap-3 text-left">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-100 text-slate-600"><Eye className="h-4 w-4" /></div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{file.source_file}</div>
                    <div className="text-xs text-slate-500">{file.ruleset_id} - v{file.version} - {file.chunk_count} chunks</div>
                  </div>
                </button>
                <div className="flex items-center gap-2">
                  <StatusBadge status={file.status} />
                  <a href={`${api.ragBaseUrl}/api/rag/files/${file.document_id}/download`} className="rounded-md p-2 text-slate-500 hover:bg-slate-100" title="Download"><Download className="h-4 w-4" /></a>
                  <button onClick={() => api.updateRagFileStatus(file.document_id, file.status === "active" ? "archived" : "active").then(refresh)} className="rounded-md p-2 text-slate-500 hover:bg-slate-100" title="Toggle active"><Archive className="h-4 w-4" /></button>
                </div>
              </div>
            ))}
            {!files.length && <div className="px-4 py-12 text-center text-sm text-slate-500">No files in this domain yet.</div>}
          </div>
        </div>
        <div className="space-y-5">
          <form onSubmit={ingest} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="text-sm font-semibold">Upload knowledge</div>
            <input ref={inputRef} type="file" multiple accept={KNOWLEDGE_EXTENSIONS.join(",")} onChange={(event) => addFiles(Array.from(event.target.files || []))} className="sr-only" />
            <label className="mt-4 block text-sm font-medium">Ruleset name<input value={rulesetName} onChange={(event) => setRulesetName(event.target.value)} className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" /></label>
            <label className="mt-3 block text-sm font-medium">Version<input value={version} onChange={(event) => setVersion(event.target.value)} className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" /></label>
            <div className="mt-4"><UploadDropzone active={busy} description="PDF, DOCX, Excel, TXT, MD, CSV, and JSON." onBrowse={() => inputRef.current?.click()} onDrop={addFiles} /></div>
            <div className="mt-3 space-y-2">
              {uploadFiles.map((file, index) => (
                <div key={`${file.name}-${file.size}`} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-sm">
                  <span className="truncate">{file.name} <span className="text-slate-500">({formatBytes(file.size)})</span></span>
                  <button type="button" onClick={() => setUploadFiles((items) => items.filter((_, itemIndex) => itemIndex !== index))} title="Remove"><X className="h-4 w-4" /></button>
                </div>
              ))}
            </div>
            {progress.percent > 0 && (
              <div className="mt-4">
                <div className="flex justify-between text-xs text-slate-500"><span>{progress.label}</span><span>{progress.percent}%</span></div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200"><div className="h-full bg-slate-950" style={{ width: `${progress.percent}%` }} /></div>
              </div>
            )}
            <button disabled={busy} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white disabled:opacity-60">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
              Upload and ingest
            </button>
          </form>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="text-sm font-semibold">Recent jobs</div>
            <div className="mt-3 space-y-3">
              {jobs.filter((job) => job.domain_id === routeDomainId).slice(0, 6).map((job) => (
                <div key={job.job_id} className="text-sm">
                  <div className="flex justify-between gap-3"><span className="truncate font-medium">{job.source_file}</span><StatusBadge status={job.status} /></div>
                  <div className="mt-1 text-xs text-slate-500">{job.message || formatDate(job.updated_at)}</div>
                </div>
              ))}
              {!jobs.filter((job) => job.domain_id === routeDomainId).length && <div className="text-sm text-slate-500">No jobs for this domain yet.</div>}
            </div>
          </div>
        </div>
      </div>
      {selectedFile && (
        <PreviewOverlay
          title={selectedFile.source_file}
          subtitle={`${selectedIndex! + 1} of ${files.length} - ${selectedFile.ruleset_id} - v${selectedFile.version}`}
          content={selectedContent}
          previewUrl={`${api.ragBaseUrl}/api/rag/files/${selectedFile.document_id}/preview`}
          downloadUrl={`${api.ragBaseUrl}/api/rag/files/${selectedFile.document_id}/download`}
          canGoPrevious={selectedIndex! > 0}
          canGoNext={selectedIndex! < files.length - 1}
          onPrevious={() => move(-1)}
          onNext={() => move(1)}
          onClose={() => setSelectedIndex(null)}
          sidePanel={
            <div>
              <div className="font-semibold">Details</div>
              <dl className="mt-4 space-y-3 text-neutral-300">
                <div><dt className="text-xs text-neutral-500">Status</dt><dd><StatusBadge status={selectedFile.status} /></dd></div>
                <div><dt className="text-xs text-neutral-500">Chunks</dt><dd>{selectedFile.chunk_count}</dd></div>
                <div><dt className="text-xs text-neutral-500">Uploaded</dt><dd>{formatDate(selectedFile.uploaded_at)}</dd></div>
                <div><dt className="text-xs text-neutral-500">Preview</dt><dd>{busy ? "Loading..." : selectedContent?.mode}</dd></div>
              </dl>
            </div>
          }
        />
      )}
    </section>
  );
}
