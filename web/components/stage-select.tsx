"use client";

import type { ReactNode } from "react";

/** A stage menu that moves the business as soon as a stage is picked. The hidden fields say which business and where to return. */
export function StageSelect({ stages, current, label, children }: { stages: string[]; current: string; label: string; children: ReactNode }) {
  return (
    <>
      {children}
      <select name="stage" aria-label={label} defaultValue={current} className="dstagepick"
        onChange={(e) => e.currentTarget.form?.requestSubmit()}>
        {stages.map((s) => <option key={s}>{s}</option>)}
      </select>
    </>
  );
}
