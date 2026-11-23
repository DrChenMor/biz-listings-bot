"use client";

import { useState, useTransition } from "react";
import { setReview } from "@/lib/actions";
import { MARKS, markClass, PIPELINE_MARKS } from "@/lib/marks";

/** The coloured review menu on a listing. A business in the pipeline just shows where it is. */
export function ReviewMark({ id, mark, name }: { id: string; mark: string; name: string }) {
  const [shown, setShown] = useState(mark);
  const [busy, start] = useTransition();
  if (PIPELINE_MARKS.includes(shown)) return <span className={markClass(shown)}>{shown}</span>;
  return (
    <select className={markClass(shown)} value={shown} disabled={busy} aria-label={`Review mark for ${name}`}
      onChange={(e) => {
        const next = e.target.value, before = shown;
        setShown(next === "Add to pipeline" ? "In pipeline" : next);
        start(async () => {
          try {
            setShown(await setReview(id, next));
          } catch {
            setShown(before);
          }
        });
      }}>
      {MARKS.map((m) => <option key={m}>{m}</option>)}
      <option>Add to pipeline</option>
    </select>
  );
}
