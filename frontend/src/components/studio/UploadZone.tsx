"use client";

import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { buttonClass } from "../ui";
import { useStudio } from "./StudioProvider";

/** Drop target and file picker for WhatsApp exports. The whole zone takes a drop; the button opens the picker. */
export function UploadZone({ compact = false }: { compact?: boolean }) {
  const { addFiles } = useStudio();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const depth = useRef(0);

  return (
    <section
      aria-labelledby="upload-title"
      onDragEnter={(e) => {
        e.preventDefault();
        depth.current += 1;
        setOver(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => {
        depth.current -= 1;
        if (depth.current <= 0) setOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        addFiles(Array.from(e.dataTransfer.files));
      }}
      className={`rounded-3xl border-2 border-dashed transition-colors duration-200 ${
        over ? "border-lime bg-night-3" : "border-line-strong"
      } ${compact ? "p-5 sm:p-6" : "p-6 sm:p-10"}`}
    >
      <div className={`flex gap-6 ${compact ? "flex-col sm:flex-row sm:items-center" : "flex-col lg:flex-row lg:items-end"}`}>
        <div className="min-w-0 flex-1">
          <h2 id="upload-title" className={`display text-cream ${compact ? "text-[28px]" : "text-[40px] sm:text-[48px]"}`}>
            {over ? "Drop it here" : "Add a chat"}
          </h2>
          <p className="text-cream-2 mt-2 max-w-[62ch] text-[15px]">
            In WhatsApp, open the chat, tap More, then Export chat, and choose Include media. Drop the .zip here, or the
            .txt if you exported without media. Uploading a newer export of the same chat only adds what is new.
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-2">
          <button type="button" onClick={() => input.current?.click()} className={buttonClass("primary", "md")}>
            <Upload aria-hidden className="size-4" />
            Upload a chat
          </button>
          <p className="text-cream-3 text-sm">.zip or .txt, up to 300 MB</p>
        </div>
      </div>
      <input
        ref={input}
        type="file"
        accept=".zip,.txt,application/zip,text/plain"
        multiple
        hidden
        onChange={(e) => {
          addFiles(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
    </section>
  );
}
