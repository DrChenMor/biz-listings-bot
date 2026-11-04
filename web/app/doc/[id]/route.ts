import { NextResponse } from "next/server";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";

/** Files stay private: a signed-in person gets a link that lasts one minute. */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  await requireUser();
  const id = Number((await params).id);
  if (!Number.isInteger(id)) return new NextResponse("Not found", { status: 404 });
  const { data } = await db().from("agent_documents").select("path").eq("id", id).maybeSingle();
  if (!data) return new NextResponse("Not found", { status: 404 });
  const { data: signed, error } = await db().storage.from("deal-docs").createSignedUrl(data.path, 60);
  if (error) throw new Error(error.message);
  return NextResponse.redirect(signed.signedUrl);
}
