"use server";

import { redirect } from "next/navigation";
import { endSession, passwordIsRight, requireUser, startSession } from "./auth";
import { db, link, STAGES } from "./db";

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

export async function setStage(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const stage = String(form.get("stage"));
  if (![...STAGES, "Passed"].includes(stage)) throw new Error("Unknown stage");
  await saveTracking(id, { stage, owner: who });
  await note(id, who, `Moved to ${stage}`);
  redirect(String(form.get("back") || link(id)));
}

export async function moveOn(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const next = STAGES[STAGES.indexOf(String(form.get("stage"))) + 1];
  if (next) {
    await saveTracking(id, { stage: next });
    await note(id, who, `Moved to ${next}`);
  }
  redirect("/pipeline");
}

export async function queueEnquiry(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const enquiries = db().from("enquiries");
  const { error } = await enquiries.upsert({ business_id: id, asked_by: who }, { onConflict: "business_id", ignoreDuplicates: true });
  if (error) throw new Error(error.message);
  // Only a test run can be queued again: anything else may already have reached the broker.
  await db().from("enquiries").update({ status: "Queued", detail: null, asked_by: who }).eq("business_id", id).eq("status", "Test only");
  await saveTracking(id, { stage: "Approaching", owner: who });
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
