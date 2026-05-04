import type { FileContent } from "../api/client";
import { formatBytes } from "../utils/format";

export function FilePreview({
  content,
  drive = false,
  previewUrl
}: {
  content: FileContent | null;
  drive?: boolean;
  previewUrl?: string;
}) {
  if (!content) {
    return (
      <div className="flex min-h-[360px] items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white text-sm text-slate-500">
        Select a file to inspect its content.
      </div>
    );
  }

  if (content.mode === "image" && content.imageDataUrl) {
    return (
      <div className={drive ? "flex min-h-[calc(100vh-160px)] items-center justify-center overflow-auto bg-slate-950 p-8" : "rounded-lg border border-slate-200 bg-white p-4"}>
        <img
          src={content.imageDataUrl}
          alt={content.fileName}
          className={drive ? "max-h-[calc(100vh-240px)] max-w-full object-contain shadow-2xl" : "max-h-[620px] w-full object-contain"}
        />
      </div>
    );
  }

  if (content.mode === "text") {
    return (
      <div className={drive ? "min-h-[calc(100vh-160px)] overflow-auto bg-slate-950 px-4 py-8" : ""}>
        <pre
          className={
            drive
              ? "mx-auto min-h-[calc(100vh-260px)] max-w-5xl whitespace-pre-wrap bg-white px-10 py-8 text-sm leading-6 text-slate-900 shadow-2xl"
              : "max-h-[620px] overflow-auto rounded-lg border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-800"
          }
        >
          {content.text}
        </pre>
      </div>
    );
  }

  if (content.mode === "pdf" && previewUrl) {
    return (
      <div className="h-full min-h-[calc(100vh-64px)] bg-neutral-900 p-4">
        <iframe title={content.fileName} src={previewUrl} className="mx-auto h-[calc(100vh-96px)] w-full max-w-6xl border-0 bg-white shadow-2xl" />
      </div>
    );
  }

  if (content.mode === "office" && content.html) {
    return (
      <div className={drive ? "min-h-[calc(100vh-160px)] overflow-auto bg-neutral-900 px-4 py-8" : ""}>
        <article
          className={
            drive
              ? "office-preview mx-auto min-h-[calc(100vh-260px)] max-w-6xl bg-white px-10 py-8 text-sm leading-6 text-slate-900 shadow-2xl"
              : "office-preview max-h-[620px] overflow-auto rounded-lg border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-800"
          }
          dangerouslySetInnerHTML={{ __html: content.html }}
        />
      </div>
    );
  }

  return (
    <div className={drive ? "flex min-h-[calc(100vh-160px)] items-center justify-center bg-slate-950 p-8" : "rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-600"}>
      <div className={drive ? "max-w-lg rounded-md bg-white p-6 text-center text-sm text-slate-600 shadow-2xl" : ""}>
        <div>{content.message || "Preview unavailable."}</div>
        <div className="mt-2 text-xs text-slate-500">{formatBytes(content.sizeBytes)}</div>
      </div>
    </div>
  );
}
