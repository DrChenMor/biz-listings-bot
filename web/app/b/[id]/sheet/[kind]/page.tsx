import Link from "next/link";
import { notFound } from "next/navigation";
import { Shell } from "@/components/shell";
import { WorksheetForm } from "@/components/worksheet-form";
import { requireUser } from "@/lib/auth";
import { Business, dealCard, db, link, Tracking, when } from "@/lib/db";
import { isKind, prefill, SHEETS } from "@/lib/worksheets";

export const dynamic = "force-dynamic";

export default async function Worksheet({ params }: { params: Promise<{ id: string; kind: string }> }) {
  const user = await requireUser();
  const { id: raw, kind } = await params;
  const id = decodeURIComponent(raw);
  if (!isKind(kind)) notFound();
  const { data } = await db().from("businesses").select("*").eq("id", id).maybeSingle();
  if (!data) notFound();
  const b = data as Business;
  const { data: track } = await db().from("tracking").select("*").eq("business_id", id).maybeSingle();
  const { data: sheet } = await db().from("worksheets").select("*").eq("business_id", id).eq("kind", kind).maybeSingle();
  const initial = sheet?.data ?? prefill(kind, b, dealCard(b, track as Tracking | null));

  return (
    <Shell user={user} active="/pipeline">
      <Link href={link(id)} className="noprint">Back to {b.name}</Link>
      <h1>{SHEETS[kind].title}</h1>
      <p className="lede">{b.name} · {SHEETS[kind].when}{sheet ? ` · last saved ${when(sheet.updated_at)} by ${sheet.updated_by}` : ""}</p>
      <WorksheetForm id={id} kind={kind} initial={initial} saved={Boolean(sheet)} />
    </Shell>
  );
}
