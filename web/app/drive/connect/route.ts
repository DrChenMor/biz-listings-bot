import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { requireUser } from "@/lib/auth";
import { connectReady, signInLink } from "@/lib/google";

/** Sends the signed-in person to Google to connect Tom's Drive. */
export async function GET(request: Request) {
  await requireUser();
  if (!connectReady()) return NextResponse.redirect(new URL("/sources?drive=not-set-up", request.url));
  const state = randomBytes(24).toString("base64url");
  (await cookies()).set("drive-state", state, { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/drive", maxAge: 600 });
  return NextResponse.redirect(signInLink(new URL("/drive/callback", request.url).toString(), state));
}
