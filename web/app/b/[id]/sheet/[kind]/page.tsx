import Link from "next/link";
import { notFound } from "next/navigation";
import { Shell } from "@/components/shell";
import { WorksheetForm } from "@/components/worksheet-form";
import { requireUser } from "@/lib/auth";
import { Business, dealCard, db, link, nameOf, Tracking, when } from "@/lib/db";
import { isKind, prefill, SHEETS } from "@/lib/worksheets";

export const dynamic = "force-dynamic";

const DRIVE_NOTES: Record<string, [string, string]> = {
  saved: ["note", "Saved to the business's Drive folder."],
  "no-folder": ["note warn", "Link this business to its Drive folder first, on the business's page."],
  empty: ["note warn", "Fill in the worksheet first. It saves as you type."],
  "not-connected": ["note warn", "Google Drive isn't connected yet. Connect it on the Sources page."],
  failed: ["note warn", "Google Drive didn't save it. Try again in a minute."],
};

export default async function Worksheet({ params, searchParams }: {
  params: Promise<{ id: string; kind: string }>; searchParams: Promise<Record<string, string | undefined>>;
}) {
  const user = await requireUser();
  const { id: raw, kind } = await params;
  const { drive, doc } = await searchParams;
  const id = decodeURIComponent(raw);
  if (!isKind(kind)) notFound();
  const { data } = await db().from("businesses").select("*").eq("id", id).maybeSingle();
  if (!data) notFound();
  const b = data as Business;
  const { data: track } = await db().from("tracking").select("*").eq("business_id", id).maybeSingle();
  const { data: sheet } = await db().from("worksheets").select("*").eq("business_id", id).eq("kind", kind).maybeSingle();
  const initial = sheet?.data ?? prefill(kind, { ...b, name: nameOf(b, track as Tracking | null) }, dealCard(b, track as Tracking | null));
  const shown = DRIVE_NOTES[drive ?? ""];
  const docLink = doc && /^https:\/\/docs\.google\.com\//.test(doc) ? doc : null;

  return (
    <Shell user={user} active="/pipeline">
      <Link href={link(id)} className="noprint">Back to {nameOf(b, track as Tracking | null)}</Link>
      <h1>{SHEETS[kind].title}</h1>
      <p className="lede">{nameOf(b, track as Tracking | null)} · {SHEETS[kind].when}{sheet ? ` · last saved ${when(sheet.updated_at)} by ${sheet.updated_by}` : ""}</p>
      {shown ? <p className={`${shown[0]} noprint`} role="status">{shown[1]} {docLink ? <a href={docLink} target="_blank" rel="noreferrer">Open the Doc</a> : null}</p> : null}
      <WorksheetForm id={id} kind={kind} initial={initial} saved={Boolean(sheet)} inDrive={Boolean(sheet?.drive_file_id)} />
    </Shell>
  );
}
