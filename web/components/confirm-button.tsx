"use client";

import type { ReactNode } from "react";

/** A submit button that asks first. Cancelling stops the form from being sent. */
export function ConfirmButton({ question, className, children }: { question: string; className?: string; children: ReactNode }) {
  return (
    <button type="submit" className={className} onClick={(e) => { if (!window.confirm(question)) e.preventDefault(); }}>
      {children}
    </button>
  );
}
