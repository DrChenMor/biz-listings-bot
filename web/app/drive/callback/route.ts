import { timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { requireUser } from "@/lib/auth";
import { finishSignIn } from "@/lib/google";

/** Google sends the person back here after they approve. */
export async function GET(request: Request) {
  const who = await requireUser();
  const url = new URL(request.url);
  const jar = await cookies();
  const expected = jar.get("drive-state")?.value ?? "";
  const state = url.searchParams.get("state") ?? "";
  jar.delete("drive-state");
  const back = (result: string) => NextResponse.redirect(new URL(`/sources?drive=${result}`, request.url));
  if (!expected || expected.length !== state.length || !timingSafeEqual(Buffer.from(expected), Buffer.from(state))) return back("expired");
  const code = url.searchParams.get("code");
  if (!code) return back("cancelled");
  try {
    const email = await finishSignIn(code, new URL("/drive/callback", request.url).toString(), who);
    return back(`connected&as=${encodeURIComponent(email)}`);
  } catch {
    return back("failed");
  }
}
