import { NextResponse } from "next/server";
import { buildDigest } from "@/lib/digest";
import { logEvent } from "@/lib/log";
import { keyIsRight } from "@/lib/mail";

export const dynamic = "force-dynamic";

/** Tom's morning email, for the email copier to send to him. Answers send: false when there's nothing new. */
export async function GET(request: Request) {
  if (!keyIsRight(request.headers.get("x-deal-desk-key"))) return NextResponse.json({ error: "Wrong key" }, { status: 401 });
  try {
    const digest = await buildDigest(new URL(request.url).origin);
    await logEvent("email", digest.send ? `Morning email made: ${digest.subject}` : "Morning email skipped: nothing new");
    return NextResponse.json(digest);
  } catch (e) {
    await logEvent("error", "The morning email couldn't be made", e instanceof Error ? e.message : String(e));
    return NextResponse.json({ error: "Couldn't make the morning email" }, { status: 500 });
  }
}
