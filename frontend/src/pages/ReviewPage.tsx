import { ArrowUp, Download, FileImage, Loader2, Paperclip, X } from "lucide-react";
import { ClipboardEvent, DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import { api, Domain, FileContent, ReviewRunResult, ReviewUpload } from "../api/client";
import { PreviewOverlay } from "../components/PreviewOverlay";
import { formatBytes, formatDate } from "../utils/format";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: ReviewRunResult;
  timestamp: Date;
  attachedFiles?: ReviewUpload[];
}

export function ReviewPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [domainId, setDomainId] = useState("");
  const [provider, setProvider] = useState("groq");
  const [attached, setAttached] = useState<ReviewUpload[]>([]);
  const [selected, setSelected] = useState<ReviewUpload | null>(null);
  const [content, setContent] = useState<FileContent | null>(null);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const hasConversation = messages.length > 0 || busy;

  async function refresh() {
    const [domainData, settingsData] = await Promise.all([api.domains(), api.settings()]);
    setDomains(domainData.domains);
    setDomainId((current) => current || domainData.domains[0]?.domain_id || "");
    setProvider(settingsData.config.provider);
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    if (!selected) {
      setContent(null);
      return;
    }
    api.reviewUpload(selected.upload_id)
      .then((data) => setContent(data.content))
      .catch((error) => setMessage(error.message));
  }, [selected]);

  async function uploadFiles(files: File[]) {
    if (!files.length) return;
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    setUploading(true);
    setMessage("");
    try {
      const data = await api.uploadReviewFiles(form);
      setAttached((current) => [...current, ...data.uploads]);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!domainId) {
      setMessage("Select a domain first.");
      return;
    }
    if (!query.trim()) {
      setMessage("Enter a query first.");
      return;
    }
    
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: query,
      timestamp: new Date(),
      attachedFiles: attached.length > 0 ? [...attached] : undefined,
    };
    
    setMessages((prev) => [...prev, userMessage]);
    const currentQuery = query;
    const currentAttached = attached.map((item) => item.upload_id);
    setQuery("");
    setAttached([]);
    setBusy(true);
    setMessage("");
    
    try {
      const data = await api.runReview({
        domainId,
        query: currentQuery,
        uploadIds: currentAttached,
        apiKey: api.getSessionApiKey(provider)
      });
      
      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: String(data.result.structured_output?.human_summary || data.result.answer),
        result: data.result,
        timestamp: new Date(),
      };
      
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Review failed");
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  function handleDrag(event: DragEvent<HTMLFormElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (event.type === "dragenter" || event.type === "dragover") {
      setDragActive(true);
    }
    if (event.type === "dragleave") {
      setDragActive(false);
    }
  }

  function handleDrop(event: DragEvent<HTMLFormElement>) {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);
    uploadFiles(Array.from(event.dataTransfer.files || []));
  }

  function handlePaste(event: ClipboardEvent<HTMLFormElement>) {
    const imageFiles = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item, index) => {
        const file = item.getAsFile();
        if (!file) return null;
        const extension = file.type.split("/")[1] || "png";
        return new File([file], file.name || `pasted-image-${Date.now()}-${index + 1}.${extension}`, {
          type: file.type
        });
      })
      .filter((file): file is File => Boolean(file));
    if (imageFiles.length) {
      event.preventDefault();
      uploadFiles(imageFiles);
    }
  }

  function downloadArtifact(format: string, artifact: { file_name: string; mime: string; content: string; encoding?: string }) {
    const data =
      artifact.encoding === "base64"
        ? Uint8Array.from(window.atob(artifact.content), (char) => char.charCodeAt(0))
        : artifact.content;
    const blob = new Blob([data], { type: artifact.mime });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = artifact.file_name || `corrected.${format}`;
    link.click();
    window.URL.revokeObjectURL(url);
  }

  function renderComposer() {
    return (
      <form
        onSubmit={submit}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onPaste={handlePaste}
        className={`mx-auto w-full max-w-3xl rounded-[28px] border bg-white p-3 shadow-xl transition ${
          dragActive ? "border-slate-950 ring-4 ring-slate-200" : "border-slate-200"
        }`}
      >
        {dragActive && (
          <div className="mb-3 rounded-2xl border border-dashed border-slate-400 bg-slate-50 px-4 py-6 text-center text-sm font-medium text-slate-600">
            Drop files into the chat
          </div>
        )}

        {!!attached.length && (
          <div className="mb-3 flex flex-wrap gap-2 px-1">
            {attached.map((upload) => (
              <button
                type="button"
                key={upload.upload_id}
                onClick={() => setSelected(upload)}
                className="group flex max-w-[270px] items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-left"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-500 text-white"><FileImage className="h-4 w-4" /></div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-slate-900">{upload.source_file}</div>
                  <div className="text-xs uppercase text-slate-500">{formatBytes(upload.size_bytes)}</div>
                </div>
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(event) => {
                    event.stopPropagation();
                    setAttached((items) => items.filter((item) => item.upload_id !== upload.upload_id));
                  }}
                  className="rounded-full p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-900"
                >
                  <X className="h-4 w-4" />
                </span>
              </button>
            ))}
          </div>
        )}

        <textarea
          ref={textareaRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything (Enter to send, Shift+Enter for new line)"
          rows={hasConversation ? 2 : 3}
          className="min-h-16 w-full resize-none bg-transparent px-3 py-2 text-base text-slate-900 outline-none placeholder:text-slate-400"
        />

        <div className="flex items-center justify-between gap-3">
          <div>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md,.csv,.json,.xlsx,.xls,.png,.jpg,.jpeg,.webp,.gif,.bmp,.svg,.avif,.tif,.tiff"
              onChange={(event) => uploadFiles(Array.from(event.target.files || []))}
              className="sr-only"
            />
            <button type="button" onClick={() => inputRef.current?.click()} className="inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
              Add files
            </button>
          </div>
          <button disabled={busy} className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-950 text-white disabled:opacity-60" title="Run review">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <ArrowUp className="h-5 w-5" />}
          </button>
        </div>
      </form>
    );
  }

  return (
    <section className="min-h-screen bg-slate-100 text-slate-950">
      <div className={`mx-auto flex min-h-screen max-w-5xl flex-col px-5 py-8 ${hasConversation ? "pb-64" : ""}`}>
        <header className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Review</h1>
            <p className="mt-1 text-sm text-slate-500">Ask against a business-rule domain and attach files when needed.</p>
          </div>
          <select
            value={domainId}
            onChange={(event) => setDomainId(event.target.value)}
            className="rounded-full border border-slate-300 bg-white px-6 py-2 text-sm text-slate-900 outline-none"
          >
            {domains.map((domain) => (
              <option key={domain.domain_id} value={domain.domain_id}>
                {domain.name}
              </option>
            ))}
          </select>
        </header>

        <div className={`flex flex-1 flex-col py-10 ${hasConversation ? "justify-start" : "justify-center"}`}>
          {messages.length === 0 && (
            <div className="mb-8 text-center text-3xl font-semibold text-slate-900">
              What are you working on?
            </div>
          )}

          <div className="mx-auto w-full max-w-3xl space-y-6">
            {messages.map((msg, index) => (
              <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-2xl px-5 py-4 ${
                  msg.role === "user" 
                    ? "bg-slate-900 text-white" 
                    : "border border-slate-200 bg-white shadow-sm"
                }`}>
                  {msg.role === "user" ? (
                    <div className="space-y-3">
                      {msg.attachedFiles && msg.attachedFiles.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {msg.attachedFiles.map((file) => (
                            <div key={file.upload_id} className="flex items-center gap-2 rounded-lg bg-slate-800 px-3 py-1.5 text-xs">
                              <FileImage className="h-3 w-3" />
                              <span>{file.source_file}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="whitespace-pre-wrap text-sm">{msg.content}</div>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <article className="max-w-none whitespace-pre-wrap text-sm leading-7 text-slate-900">
                        {msg.content}
                      </article>
                      {msg.result && (
                        <>
                          <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                            <span>{msg.result.evidence_count} evidence chunks</span>
                            {msg.result.confidence?.score !== undefined && (
                              <span>Confidence {msg.result.confidence.score}/100 {msg.result.confidence.band || ""}</span>
                            )}
                            {msg.result.structured_error && (
                              <span className="text-amber-700">{msg.result.structured_error}</span>
                            )}
                          </div>
                          {Array.isArray(msg.result.structured_output?.cases) && msg.result.structured_output.cases.length > 0 && (
                            <div className="overflow-x-auto rounded-xl border border-slate-200">
                              <table className="min-w-full text-left text-xs">
                                <thead className="bg-slate-50 text-slate-500">
                                  <tr>
                                    <th className="px-3 py-2 font-medium">Case</th>
                                    <th className="px-3 py-2 font-medium">Decision</th>
                                    <th className="px-3 py-2 font-medium">Issues</th>
                                    <th className="px-3 py-2 font-medium">Owner</th>
                                    <th className="px-3 py-2 font-medium">Evidence</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-200">
                                  {(msg.result.structured_output.cases as Array<Record<string, unknown>>).map((item, idx) => (
                                    <tr key={`${item.case_id || idx}`}>
                                      <td className="px-3 py-2 font-medium text-slate-900">{String(item.case_id || `case_${idx + 1}`)}</td>
                                      <td className="px-3 py-2 text-slate-700">{String(item.final_decision_allowed || "")}</td>
                                      <td className="px-3 py-2 text-slate-700">{Array.isArray(item.issue_types) ? item.issue_types.join(", ") : ""}</td>
                                      <td className="px-3 py-2 text-slate-700">{String(item.required_owner_or_approver || "")}</td>
                                      <td className="px-3 py-2 text-slate-700">{String(item.evidence_strength || "")}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                          {msg.result.export_files && Object.keys(msg.result.export_files).length > 0 && (
                            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                              <div className="text-sm font-semibold text-slate-900">Corrected file exports</div>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {Object.entries(msg.result.export_files).map(([format, artifact]) => (
                                  <button
                                    key={format}
                                    type="button"
                                    onClick={() => downloadArtifact(format, artifact)}
                                    className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:border-slate-500"
                                  >
                                    <Download className="h-4 w-4" />
                                    {format.toUpperCase()}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                          {!!msg.result.citations?.length && (
                            <details className="text-sm text-slate-700">
                              <summary className="cursor-pointer text-slate-500">Citations</summary>
                              <div className="mt-2 space-y-1">
                                {msg.result.citations.map((citation) => <div key={citation}>{citation}</div>)}
                              </div>
                            </details>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Thinking...
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {!hasConversation && renderComposer()}

          {message && <div className="mx-auto mt-4 max-w-3xl rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{message}</div>}
        </div>
      </div>

      {hasConversation && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-slate-100/95 px-5 pb-5 pt-4 backdrop-blur lg:left-[var(--sidebar-width)]">
          {renderComposer()}
          <p className="mx-auto mt-2 max-w-3xl text-center text-xs text-slate-500">
            Business Rule AI can make mistakes. Check cited evidence before operational use.
          </p>
        </div>
      )}

      {selected && (
        <PreviewOverlay
          title={selected.source_file}
          subtitle={`${formatBytes(selected.size_bytes)} - ${formatDate(selected.uploaded_at)}`}
          content={content}
          previewUrl={`${api.reviewBaseUrl}/api/review/uploads/${selected.upload_id}/preview`}
          downloadUrl={`${api.reviewBaseUrl}/api/review/uploads/${selected.upload_id}/download`}
          onClose={() => setSelected(null)}
          sidePanel={
            <div>
              <div className="font-semibold">Details</div>
              <dl className="mt-4 space-y-3 text-neutral-300">
                <div><dt className="text-xs text-neutral-500">Type</dt><dd>{selected.content_type}</dd></div>
                <div><dt className="text-xs text-neutral-500">Size</dt><dd>{formatBytes(selected.size_bytes)}</dd></div>
                <div><dt className="text-xs text-neutral-500">Uploaded</dt><dd>{formatDate(selected.uploaded_at)}</dd></div>
                <div><dt className="text-xs text-neutral-500">Preview</dt><dd>{content?.mode || "Loading"}</dd></div>
              </dl>
            </div>
          }
        />
      )}
    </section>
  );
}
