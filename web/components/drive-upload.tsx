"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { beginUpload } from "@/lib/actions";

type Item = { name: string; done: number; status: "sending" | "done" | "failed"; problem?: string };

/** Send one file straight to Google, reporting how far it has got. */
function send(address: string, file: File, onProgress: (share: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", address);
    request.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    request.onload = () => (request.status < 300 ? resolve() : reject(new Error(String(request.status))));
    request.onerror = () => reject(new Error("network"));
    request.send(file);
  });
}

/** Drop files here, or choose them, to add them to the business's Drive folder. */
export function DriveUpload({ id }: { id: string }) {
  const router = useRouter();
  const picker = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [over, setOver] = useState(false);

  const update = (index: number, change: Partial<Item>) => setItems((all) => all.map((item, i) => (i === index ? { ...item, ...change } : item)));

  async function upload(files: File[]) {
    if (!files.length) return;
    const start = items.length;
    setItems((all) => [...all, ...files.map((f) => ({ name: f.name, done: 0, status: "sending" as const }))]);
    await Promise.all(files.map(async (file, i) => {
      try {
        const { address, problem } = await beginUpload(id, file.name, file.type, file.size);
        if (!address) { update(start + i, { status: "failed", problem }); return; }
        await send(address, file, (share) => update(start + i, { done: share }));
        update(start + i, { done: 1, status: "done" });
      } catch {
        update(start + i, { status: "failed" });
      }
    }));
    router.refresh();
  }

  return (
    <div>
      <div className={over ? "dropzone over" : "dropzone"} role="button" tabIndex={0}
        onClick={() => picker.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && picker.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); upload(Array.from(e.dataTransfer.files)); }}>
        <b>Drop files here</b> or click to choose. They go straight into this business&apos;s Drive folder.
      </div>
      <input ref={picker} type="file" multiple hidden aria-label="Choose files to add to the Drive folder"
        onChange={(e) => { upload(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
      {items.map((item, i) => (
        <p className="lsub" key={i} role="status">
          {item.name}: {item.status === "done" ? "added" : item.status === "failed" ? (item.problem ?? "didn't upload, try again") : `${Math.round(item.done * 100)}%`}
        </p>
      ))}
    </div>
  );
}
