import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { keyIsRight } from "@/lib/mail";

export const dynamic = "force-dynamic";

/** The email copier reports each run, so Today and Sources show when it last ran and how it went. */
export async function POST(request: Request) {
  if (!keyIsRight(request.headers.get("x-deal-desk-key"))) return NextResponse.json({ error: "Wrong key" }, { status: 401 });
  const body = (await request.json().catch(() => ({}))) as { copied?: number; unmatched?: number; skipped?: number; error?: string };
  const started = new Date().toLocaleString("sv-SE", { timeZone: "Australia/Perth" }).slice(0, 16);
  const skipped = Number(body.skipped) ? `, ${Number(body.skipped)} skipped` : "";
  const result = body.error ? `error: ${String(body.error).slice(0, 200)}`
    : `ok, ${Number(body.copied) || 0} copied, ${Number(body.unmatched) || 0} not matched${skipped}`;
  const { error } = await db().from("site_runs").upsert({ site: "email copier", started, result }, { onConflict: "site" });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
