/**
 * The website's log: sign-ins, problems and server errors, for the Log page. Writing to it never breaks what the
 * person was doing: if the log can't be written, the page carries on.
 */
import { db } from "./db";

export type LogKind = "sign-in" | "problem" | "error" | "email" | "action";

export async function logEvent(kind: LogKind, what: string, detail?: string | null, who?: string | null, path?: string | null): Promise<void> {
  try {
    await db().from("app_log").insert({
      kind, what: what.slice(0, 300), detail: detail ? String(detail).slice(0, 2000) : null, who: who ?? null, path: path ?? null,
    });
  } catch {
    // The log is for finding problems; it must never become one.
  }
}
