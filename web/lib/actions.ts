"use server";

import { randomUUID } from "node:crypto";
import { redirect } from "next/navigation";
import { endSession, passwordIsRight, requireUser, startSession } from "./auth";
import { BY_HAND, db, link, NEXT_STAGE, PASSED, STAGES, today } from "./db";

export async function signIn(form: FormData): Promise<void> {
  const name = String(form.get("name") || "");
  if (!["Chen", "Partner"].includes(name) || !passwordIsRight(String(form.get("password") || ""))) {
    await new Promise((resolve) => setTimeout(resolve, 800));
    redirect("/login?wrong=1");
  }
  await startSession(name);
  redirect("/");
}

export async function signOut(): Promise<void> {
  await endSession();
  redirect("/login");
}

async function note(id: string, who: string, text: string): Promise<void> {
  const { error } = await db().from("activity").insert({ business_id: id, who, text });
  if (error) throw new Error(error.message);
}

async function saveTracking(id: string, change: Record<string, unknown>): Promise<void> {
  const { error } = await db().from("tracking").upsert({ business_id: id, ...change, updated_at: new Date().toISOString() });
  if (error) throw new Error(error.message);
}

/** A stage change, which also records the day a business was first approached. */
async function moveTo(id: string, stage: string, who: string, extra: Record<string, unknown> = {}): Promise<void> {
  if (![...STAGES, PASSED].includes(stage)) throw new Error("Unknown stage");
  const { data } = await db().from("tracking").select("approached_on").eq("business_id", id).maybeSingle();
  const approached = !data?.approached_on && STAGES.indexOf(stage) >= STAGES.indexOf("Approached") ? { approached_on: today() } : {};
  await saveTracking(id, { stage, owner: who, ...approached, ...extra });
  await note(id, who, `Moved to ${stage}`);
}

export async function setStage(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  await moveTo(id, String(form.get("stage")), who);
  redirect(String(form.get("back") || link(id)));
}

export async function moveOn(form: FormData): Promise<void> {
  const who = await requireUser();
  const next = NEXT_STAGE[String(form.get("stage"))];
  if (next) await moveTo(String(form.get("id")), next, who);
  redirect("/pipeline");
}

export async function followedUp(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  await saveTracking(id, { followed_up_on: today() });
  await note(id, who, "Followed up");
  redirect(String(form.get("back") || link(id)));
}

/** "$250k", "1.2m" or "250,000" as a number; blank as nothing. */
function amount(value: FormDataEntryValue | null): number | null {
  const text = String(value ?? "").replace(/[$,\s]/g, "").replace(/k$/i, "e3").replace(/m$/i, "e6");
  const number = text ? Number(text) : NaN;
  return Number.isFinite(number) ? number : null;
}

function words(value: FormDataEntryValue | null): string | null {
  return String(value ?? "").trim() || null;
}

export async function saveDealCard(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const stage = String(form.get("stage"));
  const { data } = await db().from("tracking").select("stage").eq("business_id", id).maybeSingle();
  const card = {
    location: words(form.get("location")), product: words(form.get("product")), selling_reason: words(form.get("selling_reason")),
    asking_price: amount(form.get("asking_price")), turnover: amount(form.get("turnover")), expenses: amount(form.get("expenses")),
    profit: amount(form.get("profit")), under_management: words(form.get("under_management")),
    approached_on: words(form.get("approached_on")), followed_up_on: words(form.get("followed_up_on")),
  };
  if (data?.stage !== stage) await moveTo(id, stage, who, card);
  else await saveTracking(id, { ...card, owner: who });
  redirect(link(id));
}

export async function addBusiness(form: FormData): Promise<void> {
  const who = await requireUser();
  const name = words(form.get("name"));
  if (!name) redirect("/pipeline");
  const id = `manual:${randomUUID().slice(0, 8)}`;
  const location = words(form.get("location"));
  const { error } = await db().from("businesses").insert({
    id, kind: "sale", site: BY_HAND, status: "Available", name, suburb: location, route: "Direct", url: words(form.get("url")),
    search_text: `${name} ${location ?? ""}`.toLowerCase(),
  });
  if (error) throw new Error(error.message);
  await moveTo(id, String(form.get("stage") || "Approached"), who, { location });
  redirect(link(id));
}

export async function saveWorksheet(id: string, kind: string, data: Record<string, string>): Promise<string> {
  const who = await requireUser();
  if (!["review", "analysis", "bundle"].includes(kind)) throw new Error("Unknown worksheet");
  const kept = Object.fromEntries(Object.entries(data).filter(([key, value]) => key.length < 80 && typeof value === "string").map(([k, v]) => [k, v.slice(0, 5000)]));
  const at = new Date().toISOString();
  const { error } = await db().from("worksheets").upsert({ business_id: id, kind, data: kept, updated_by: who, updated_at: at });
  if (error) throw new Error(error.message);
  return at;
}

export async function queueEnquiry(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const enquiries = db().from("enquiries");
  const { error } = await enquiries.upsert({ business_id: id, asked_by: who }, { onConflict: "business_id", ignoreDuplicates: true });
  if (error) throw new Error(error.message);
  // Only a test run can be queued again: anything else may already have reached the broker.
  await db().from("enquiries").update({ status: "Queued", detail: null, asked_by: who }).eq("business_id", id).eq("status", "Test only");
  const { data: tracked } = await db().from("tracking").select("stage").eq("business_id", id).maybeSingle();
  if (!tracked || tracked.stage === "Shortlist") await moveTo(id, "Approached", who);
  await note(id, who, "Asked the agent to send the first enquiry");
  redirect(link(id));
}

export async function cancelEnquiry(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const { error } = await db().from("enquiries").delete().eq("business_id", id).eq("status", "Queued");
  if (error) throw new Error(error.message);
  await note(id, who, "Took the enquiry back off the agent's list");
  redirect(link(id));
}

export async function setNextStep(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const step = String(form.get("step") || "").trim();
  const due = String(form.get("due") || "") || null;
  await saveTracking(id, { next_step: step || null, next_due: due, owner: who });
  if (step) await note(id, who, `Next step: ${step}`);
  redirect(link(id));
}

export async function addNote(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const text = String(form.get("text") || "").trim();
  if (text) await note(id, who, text);
  redirect(link(id));
}
