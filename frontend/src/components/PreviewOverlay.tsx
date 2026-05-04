import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";
import type { ReactNode } from "react";
import type { FileContent } from "../api/client";
import { FilePreview } from "./FilePreview";

export function PreviewOverlay({
  title,
  subtitle,
  content,
  previewUrl,
  downloadUrl,
  canGoPrevious,
  canGoNext,
  onPrevious,
  onNext,
  onClose,
  sidePanel
}: {
  title: string;
  subtitle?: string;
  content: FileContent | null;
  previewUrl?: string;
  downloadUrl: string;
  canGoPrevious?: boolean;
  canGoNext?: boolean;
  onPrevious?: () => void;
  onNext?: () => void;
  onClose: () => void;
  sidePanel?: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-black/80 text-white" onMouseDown={onClose}>
      <div className="flex h-screen flex-col" onMouseDown={(event) => event.stopPropagation()}>
        <header className="flex min-h-16 items-center justify-between gap-3 border-b border-white/10 bg-neutral-900/95 px-5">
          <div className="flex min-w-0 items-center gap-3">
            <button onClick={onClose} className="rounded-full p-2 hover:bg-white/10" title="Close preview">
              <X className="h-5 w-5" />
            </button>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{title}</div>
              {subtitle && <div className="truncate text-xs text-neutral-400">{subtitle}</div>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {onPrevious && (
              <button disabled={!canGoPrevious} onClick={onPrevious} className="rounded-full p-2 hover:bg-white/10 disabled:opacity-30" title="Previous file">
                <ChevronLeft className="h-5 w-5" />
              </button>
            )}
            {onNext && (
              <button disabled={!canGoNext} onClick={onNext} className="rounded-full p-2 hover:bg-white/10 disabled:opacity-30" title="Next file">
                <ChevronRight className="h-5 w-5" />
              </button>
            )}
            <a href={downloadUrl} className="rounded-full p-2 hover:bg-white/10" title="Download">
              <Download className="h-5 w-5" />
            </a>
          </div>
        </header>
        <div className="grid min-h-0 flex-1 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="relative min-h-0 overflow-auto bg-neutral-900">
            <FilePreview content={content} drive previewUrl={previewUrl} />
          </div>
          {sidePanel && (
            <aside className="hidden overflow-auto border-l border-white/10 bg-neutral-950 p-4 text-sm xl:block">
              {sidePanel}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
