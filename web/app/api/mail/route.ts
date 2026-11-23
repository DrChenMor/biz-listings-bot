import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { IncomingMail, keyIsRight, saveMail } from "@/lib/mail";

export const dynamic = "force-dynamic";

const denied = () => NextResponse.json({ error: "Wrong key" }, { status: 401 });

/** The addresses the email copier should look for: every contact of a business in the pipeline. */
export async function GET(request: Request) {
  if (!keyIsRight(request.headers.get("x-deal-desk-key"))) return denied();
  const { data, error } = await db().from("contacts").select("email");
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ contacts: [...new Set((data ?? []).map((c) => c.email))], lookbackDays: 120, unmatchedDays: 14 });
}

/** A batch of emails from Tom's inbox. Answers where each new one should be copied. */
export async function POST(request: Request) {
  if (!keyIsRight(request.headers.get("x-deal-desk-key"))) return denied();
  const body = (await request.json().catch(() => null)) as { messages?: IncomingMail[] } | null;
  const messages = (body?.messages ?? []).slice(0, 100).map((m) => ({
    ...m, subject: String(m.subject ?? "").slice(0, 500), body: String(m.body ?? "").slice(0, 50_000),
    attachments: (m.attachments ?? []).map((a) => String(a).slice(0, 200)).slice(0, 30),
  }));
  try {
    return NextResponse.json({ results: await saveMail(messages) });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : "Couldn't save" }, { status: 500 });
  }
}
