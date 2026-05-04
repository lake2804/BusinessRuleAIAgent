import { FilePlus2, UploadCloud } from "lucide-react";
import type { DragEvent, ReactNode } from "react";

export function UploadDropzone({
  active,
  children,
  onBrowse,
  onDrop,
  description
}: {
  active: boolean;
  children?: ReactNode;
  onBrowse: () => void;
  onDrop: (files: File[]) => void;
  description: string;
}) {
  function handleDrag(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    onDrop(Array.from(event.dataTransfer.files || []));
  }

  return (
    <div
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      className={`rounded-lg border-2 border-dashed p-8 text-center transition ${
        active ? "border-slate-950 bg-slate-50" : "border-slate-300 bg-white hover:border-slate-500"
      }`}
    >
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-950 text-white">
        <UploadCloud className="h-6 w-6" />
      </div>
      <div className="mt-3 text-sm font-semibold">Drop files here</div>
      <div className="mt-1 text-xs text-slate-500">{description}</div>
      <button
        type="button"
        onClick={onBrowse}
        className="mt-4 inline-flex items-center gap-2 rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white"
      >
        <FilePlus2 className="h-4 w-4" />
        Choose files
      </button>
      {children}
    </div>
  );
}
