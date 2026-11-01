"use client";

import type { ReactNode } from "react";

/** A plain GET form that applies each dropdown as soon as it changes, so filters live in the page's address. */
export function Filters({ children }: { children: ReactNode }) {
  return (
    <form action="/find" method="get" className="filters" onChange={(e) => {
      if ((e.target as HTMLElement).tagName === "SELECT") e.currentTarget.requestSubmit();
    }}>
      {children}
    </form>
  );
}
