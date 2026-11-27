"use server";

import { randomUUID } from "node:crypto";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { endSession, passwordIsRight, requireUser, startSession } from "./auth";
import { BY_HAND, db, link, nameOf, NEXT_STAGE, PASSED, STAGES, today } from "./db";
import { MARKS } from "./marks";
import { acquisitionsId, businessFolders, folderName, passedId } from "./drive";
import { binFile, connection, createFolder, disconnect, DriveDisconnected, moveFile, renameFile, saveDoc, startUpload } from "./google";
import { isKind, SHEETS, worksheetHtml } from "./worksheets";
import { logEvent } from "./log";

export async function signIn(form: FormData): Promise<void> {
  const name = String(form.get("name") || "");
  if (!["Chen", "Tom"].includes(name) || !passwordIsRight(String(form.get("password") || ""))) {
    await logEvent("sign-in", "Wrong password", null, name || null);
    await new Promise((resolve) => setTimeout(resolve, 800));
    redirect("/login?wrong=1");
  }
  await startSession(name);
  await logEvent("sign-in", "Signed in", null, name);
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
  const change: Record<string, unknown> = { stage, owner: who, ...extra };
  // The first move to Approached or later records the day. A blank date box sent with the move must not wipe it.
  if (!data?.approached_on && !extra.approached_on && STAGES.indexOf(stage) >= STAGES.indexOf("Approached")) change.approached_on = today();
  else if (!extra.approached_on && data?.approached_on) delete change.approached_on;
  await saveTracking(id, change);
  await note(id, who, `Moved to ${stage}`);
}

/** Where a form came from, so a button on the Pipeline keeps the view that was open. Only pages on this site. */
function back(form: FormData, otherwise: string): string {
  const to = String(form.get("back") || "");
  return to.startsWith("/") && !to.startsWith("//") ? to : otherwise;
}

/** A name fit for a Drive folder. */
const folderSafe = (name: string) => name.replace(/[\\/]+/g, "-").slice(0, 100).trim();

export async function setStage(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  await moveTo(id, String(form.get("stage")), who);
  redirect(back(form, link(id)));
}

export async function moveOn(form: FormData): Promise<void> {
  const who = await requireUser();
  const next = NEXT_STAGE[String(form.get("stage"))];
  if (next) await moveTo(String(form.get("id")), next, who);
  redirect(back(form, "/pipeline"));
}

export async function followedUp(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  await saveTracking(id, { followed_up_on: today() });
  await note(id, who, "Followed up");
  redirect(back(form, link(id)));
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

const OVERVIEW_LABELS: Record<string, string> = {
  display_name: "name", location: "location", product: "product / service", selling_reason: "selling reason",
  turnover: "annual turnover", expenses: "annual expenses", profit: "EBITDA / profit", asking_price: "asking price",
  under_management: "under management", approached_on: "approached on", followed_up_on: "last follow-up",
};

/**
 * Save the business's overview, stage or dates. Only the fields the form sends are changed, so the Overview, the
 * Stage box and the pipeline card's Edit form can each send their own part.
 */
export async function saveDealCard(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const [{ data }, { data: business }] = await Promise.all([
    db().from("tracking").select("*").eq("business_id", id).maybeSingle(),
    db().from("businesses").select("name").eq("id", id).maybeSingle(),
  ]);
  const card: Record<string, unknown> = {};
  let displayName: string | null = data?.display_name ?? null;
  if (form.has("display_name")) {
    const typed = words(form.get("display_name"));
    displayName = typed && typed !== business?.name ? typed.slice(0, 120) : null;
    card.display_name = displayName;
  }
  for (const key of ["location", "product", "selling_reason", "under_management"]) {
    if (form.has(key)) card[key] = words(form.get(key));
  }
  // An empty date box keeps the date there is: dates are only ever set or changed, never wiped by a blank box.
  for (const key of ["approached_on", "followed_up_on"]) {
    if (words(form.get(key))) card[key] = words(form.get(key));
  }
  for (const key of ["asking_price", "turnover", "expenses", "profit"]) {
    if (form.has(key)) card[key] = amount(form.get(key));
  }
  const changed = Object.keys(card).filter((key) => key !== "display_name" && String(card[key] ?? "") !== String(data?.[key] ?? ""));
  const stage = form.has("stage") ? String(form.get("stage")) : data?.stage ?? "Shortlist";
  if (data?.stage !== stage) await moveTo(id, stage, who, card);
  else await saveTracking(id, { ...card, owner: who });
  if (changed.length) await note(id, who, `Updated ${changed.map((key) => OVERVIEW_LABELS[key] ?? key).join(", ")}`);
  if (form.has("display_name") && (data?.display_name ?? null) !== displayName) {
    const shown = displayName ?? business?.name ?? id;
    await note(id, who, `Renamed to ${shown}`);
    // Keep the Drive folder's name in step, when Tom's Google Drive is connected. The website still saves if Drive says no.
    if (data?.drive_folder_id && displayName && (await connection())) {
      try {
        await renameFile(data.drive_folder_id, folderSafe(displayName));
        await note(id, who, `Renamed the Drive folder to ${folderSafe(displayName)}`);
      } catch {
        await note(id, who, "Couldn't rename the Drive folder. Rename it in Drive by hand.");
      }
    }
  }
  redirect(back(form, link(id)));
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

const folderId = (value: FormDataEntryValue | null) => String(value ?? "").replace(/[^\w-]/g, "") || null;

export async function linkFolder(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const folder = folderId(form.get("folder"));
  // Tom names his folders after the real business, so a linked folder gives the business its name, unless one is set.
  const name = folder ? words(form.get("folder_name")) ?? (await folderName(folder).catch(() => null)) : null;
  const { data: tracked } = await db().from("tracking").select("display_name").eq("business_id", id).maybeSingle();
  const { data: business } = await db().from("businesses").select("name").eq("id", id).maybeSingle();
  const naming = name && !tracked?.display_name && name !== business?.name ? { display_name: name.slice(0, 120) } : {};
  await saveTracking(id, { drive_folder_id: folder, ...naming });
  await note(id, who, folder ? `Linked the Drive folder ${name ?? ""}`.trim() : "Unlinked the Drive folder");
  redirect(back(form, link(id)));
}

/** A Drive folder whose business isn't in the pipeline yet becomes a business added by hand. */
export async function addFromFolder(form: FormData): Promise<void> {
  const who = await requireUser();
  const folder = folderId(form.get("folder"));
  const name = words(form.get("folder_name"));
  if (!folder || !name) redirect("/pipeline");
  const id = `manual:${randomUUID().slice(0, 8)}`;
  const { error } = await db().from("businesses").insert({ id, kind: "sale", site: BY_HAND, status: "Available", name, route: "Direct", search_text: name.toLowerCase() });
  if (error) throw new Error(error.message);
  await moveTo(id, String(form.get("stage") || "Documents in"), who, { drive_folder_id: folder });
  redirect("/pipeline");
}

/** Make the business's folder in Acquisitions, as Tom, and link it. */
export async function createDriveFolder(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const { data: business } = await db().from("businesses").select("name").eq("id", id).maybeSingle();
  const root = await acquisitionsId();
  if (!business || !root) throw new Error("The Acquisitions folder isn't shared with the website.");
  const typed = words(form.get("name"));
  const name = folderSafe(typed ?? business.name) || folderSafe(business.name);
  let folder: string;
  try {
    folder = await createFolder(root, name);
  } catch (e) {
    await logEvent("problem", "Couldn't make a Drive folder", e instanceof Error ? e.message : String(e), who, link(id));
    redirect(`${link(id)}?drive=${e instanceof DriveDisconnected ? "disconnected" : "failed"}`);
  }
  await saveTracking(id, { drive_folder_id: folder, ...(typed && typed !== business.name ? { display_name: typed.slice(0, 120) } : {}) });
  await note(id, who, `Made the Drive folder ${name}`);
  redirect(link(id));
}

/**
 * Where the browser should send a file for the business's folder. Problems come back as words to show, because the
 * website hides a server error's message from the browser.
 */
export async function beginUpload(id: string, name: string, type: string, size: number): Promise<{ address?: string; problem?: string }> {
  const who = await requireUser();
  const { data: tracked } = await db().from("tracking").select("drive_folder_id").eq("business_id", id).maybeSingle();
  if (!tracked?.drive_folder_id) return { problem: "Link this business to its Drive folder first." };
  const host = (await headers()).get("host") ?? "";
  const origin = `${host.startsWith("localhost") ? "http" : "https"}://${host}`;
  try {
    const address = await startUpload(tracked.drive_folder_id, name.replace(/[\\/]+/g, "-").slice(0, 200), type, size, origin);
    await note(id, who, `Added ${name} to the Drive folder`);
    return { address };
  } catch (e) {
    await logEvent("problem", `Couldn't upload ${name}`, e instanceof Error ? e.message : String(e), who, link(id));
    return { problem: e instanceof DriveDisconnected ? e.message : "Google Drive didn't take the file. Try again in a minute." };
  }
}

export async function disconnectDrive(): Promise<void> {
  await requireUser();
  await disconnect();
  redirect("/sources?drive=disconnected");
}

/** Save a worksheet as a Google Doc in the business's Drive folder, updating the Doc saved before if there is one. */
export async function saveWorksheetToDrive(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const kind = String(form.get("kind"));
  if (!isKind(kind)) throw new Error("Unknown worksheet");
  const page = `${link(id)}/sheet/${kind}`;
  const [{ data: business }, { data: tracked }, { data: sheet }] = await Promise.all([
    db().from("businesses").select("name").eq("id", id).maybeSingle(),
    db().from("tracking").select("drive_folder_id, display_name").eq("business_id", id).maybeSingle(),
    db().from("worksheets").select("data, drive_file_id").eq("business_id", id).eq("kind", kind).maybeSingle(),
  ]);
  if (!tracked?.drive_folder_id) redirect(`${page}?drive=no-folder`);
  if (!sheet) redirect(`${page}?drive=empty`);
  if (!(await connection())) redirect(`${page}?drive=not-connected`);
  const shown = business ? nameOf(business, tracked) : id;
  const title = `${SHEETS[kind].title} - ${shown}`;
  let saved: { id: string; link: string };
  try {
    saved = await saveDoc(tracked.drive_folder_id, title, worksheetHtml(kind, shown, sheet.data), sheet.drive_file_id);
  } catch {
    redirect(`${page}?drive=failed`);
  }
  await db().from("worksheets").update({ drive_file_id: saved.id }).eq("business_id", id).eq("kind", kind);
  await note(id, who, `Saved the ${SHEETS[kind].title} to Drive`);
  redirect(`${page}?drive=saved&doc=${encodeURIComponent(saved.link)}`);
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

/**
 * Take a business off every list. Nothing is deleted: Restore brings it back as it was. Its Drive folder can go into
 * Acquisitions/Passed, Tom's place for businesses that are off the table.
 */
export async function archiveBusiness(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const { data: tracked } = await db().from("tracking").select("stage, drive_folder_id").eq("business_id", id).maybeSingle();
  await saveTracking(id, { archived_at: new Date().toISOString(), archived_by: who, ...(tracked ? {} : { stage: PASSED }) });
  await note(id, who, "Archived");
  if (form.get("move_folder") && tracked?.drive_folder_id && (await connection())) {
    try {
      const passed = await passedId();
      if (!passed) throw new Error("No Passed folder");
      await moveFile(tracked.drive_folder_id, passed);
      await note(id, who, "Moved the Drive folder to Acquisitions/Passed");
    } catch {
      await note(id, who, "Couldn't move the Drive folder to Passed. Move it in Drive by hand.");
    }
  }
  redirect(back(form, link(id)));
}

export async function restoreBusiness(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  await saveTracking(id, { archived_at: null, archived_by: null });
  await note(id, who, "Restored from the archive");
  redirect(back(form, link(id)));
}

/**
 * Delete a business from the website right away, after a confirm. One added by hand goes completely. A listing found by
 * the bots would come back on their next run, so it leaves the pipeline, loses its card and worksheets, and is marked
 * Not for us in Find; its history stays. Its Drive folder goes to the Drive bin only when that box is ticked.
 */
export async function deleteBusiness(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  if (form.get("sure") !== "yes") redirect(back(form, "/pipeline"));
  const [{ data: business }, { data: tracked }] = await Promise.all([
    db().from("businesses").select("site").eq("id", id).maybeSingle(),
    db().from("tracking").select("drive_folder_id").eq("business_id", id).maybeSingle(),
  ]);
  if (!business) redirect(back(form, "/pipeline"));
  if (form.get("bin_folder") && tracked?.drive_folder_id && (await connection())) await binFile(tracked.drive_folder_id);
  const byHand = business.site === BY_HAND;
  for (const table of byHand ? ["worksheets", "activity", "reviews", "tracking"] : ["worksheets", "tracking"]) {
    const { error } = await db().from(table).delete().eq("business_id", id);
    if (error) throw new Error(error.message);
  }
  if (byHand) {
    const { error } = await db().from("businesses").delete().eq("id", id);
    if (error) throw new Error(error.message);
  } else {
    await db().from("reviews").upsert({ business_id: id, mark: "Not for us", marked_by: who, marked_at: new Date().toISOString() });
    await note(id, who, "Deleted from the pipeline");
  }
  const to = back(form, "/pipeline");
  redirect(to.startsWith("/b/") ? "/pipeline" : to);
}

/** Put a Drive folder that isn't linked to any business in the Drive bin, after a confirm. Only folders in Acquisitions. */
export async function binFolder(form: FormData): Promise<void> {
  await requireUser();
  const folder = folderId(form.get("folder"));
  if (form.get("sure") !== "yes" || !folder) redirect("/pipeline");
  const { data: linked } = await db().from("tracking").select("business_id").eq("drive_folder_id", folder).maybeSingle();
  const known = (await businessFolders()).some((f) => f.id === folder);
  if (linked || !known) throw new Error("Only a folder in Acquisitions that no business uses can be deleted here.");
  await binFile(folder);
  redirect("/pipeline");
}

/**
 * Mark a listing as looked at, from Find or its page. Adding it to the pipeline happens on its page, with the Deal card.
 * Returns the mark to show. Everyone signed in sees the same marks.
 */
export async function setReview(id: string, mark: string): Promise<string> {
  const who = await requireUser();
  if (!MARKS.includes(mark)) throw new Error("Unknown mark");
  const reviews = db().from("reviews");
  const { error } = mark === "Not reviewed"
    ? await reviews.delete().eq("business_id", id)
    : await reviews.upsert({ business_id: id, mark, marked_by: who, marked_at: new Date().toISOString() });
  if (error) throw new Error(error.message);
  await note(id, who, mark === "Not reviewed" ? "Cleared the review mark" : `Marked ${mark}`);
  return mark;
}

const emailOf = (value: FormDataEntryValue | null) => {
  const text = String(value ?? "").trim().toLowerCase();
  return /^[\w.+'-]+@[\w-]+(\.[\w-]+)+$/.test(text) ? text : null;
};

/** Someone we email about this business: the email copier copies their emails to it. */
export async function addContact(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const email = emailOf(form.get("email"));
  if (email) {
    const role = ["Seller", "Broker", "Other"].includes(String(form.get("role"))) ? String(form.get("role")) : "Other";
    const { error } = await db().from("contacts").upsert(
      { business_id: id, email, name: words(form.get("name")), role, added_by: who }, { onConflict: "business_id,email" });
    if (error) throw new Error(error.message);
    await note(id, who, `Added ${email} to the contacts (${role.toLowerCase()})`);
  }
  redirect(back(form, link(id)));
}

export async function removeContact(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id"));
  const email = emailOf(form.get("email"));
  if (email) {
    await db().from("contacts").delete().eq("business_id", id).eq("email", email);
    await note(id, who, `Removed ${email} from the contacts`);
  }
  redirect(back(form, link(id)));
}

/** An email the copier couldn't place: its sender becomes a contact of the business Tom picks. */
export async function linkUnmatched(form: FormData): Promise<void> {
  const who = await requireUser();
  const id = String(form.get("id") || "");
  const gmailId = String(form.get("gmail_id") || "");
  const { data } = await db().from("unmatched_mail").select("sender, sender_name").eq("gmail_id", gmailId).maybeSingle();
  if (id && data?.sender) {
    await db().from("contacts").upsert({ business_id: id, email: data.sender, name: data.sender_name, role: "Other", added_by: who },
      { onConflict: "business_id,email" });
    await db().from("unmatched_mail").delete().eq("sender", data.sender);
    await note(id, who, `Added ${data.sender} to the contacts; the email copier will copy their emails on its next run`);
  }
  redirect("/pipeline#emails");
}

/** Not about any business: hide it, and the copier skips that sender from now on. */
export async function dismissUnmatched(form: FormData): Promise<void> {
  await requireUser();
  const { data } = await db().from("unmatched_mail").select("sender").eq("gmail_id", String(form.get("gmail_id") || "")).maybeSingle();
  if (data?.sender) await db().from("unmatched_mail").update({ dismissed: true }).eq("sender", data.sender);
  redirect("/pipeline#emails");
}

/** A real name the name finder found in the documents: Accept puts it on the card. */
export async function acceptName(form: FormData): Promise<void> {
  const who = await requireUser();
  const suggestion = Number(form.get("suggestion"));
  const { data } = await db().from("name_suggestions").select("business_id, name, source").eq("id", suggestion).maybeSingle();
  if (data) {
    await saveTracking(data.business_id, { display_name: data.name.slice(0, 120) });
    await db().from("name_suggestions").update({ status: "accepted" }).eq("id", suggestion);
    await note(data.business_id, who, `Renamed to ${data.name} (found by the name finder: ${data.source})`);
  }
  redirect(back(form, data ? link(data.business_id) : "/pipeline"));
}

export async function ignoreName(form: FormData): Promise<void> {
  await requireUser();
  await db().from("name_suggestions").update({ status: "ignored" }).eq("id", Number(form.get("suggestion")));
  redirect(back(form, "/pipeline"));
}

/** Save Find's current filters as something we look for. New listings that fit them are starred and emailed to Tom. */
export async function saveWatchRule(form: FormData): Promise<void> {
  const who = await requireUser();
  const name = words(form.get("name"))?.slice(0, 60);
  let filters: Record<string, string> = {};
  try {
    filters = JSON.parse(String(form.get("filters") || "{}"));
  } catch {
    filters = {};
  }
  if (name) {
    await db().from("watch_rules").insert({ name, filters, created_by: who });
    await logEvent("action", `Started watching "${name}"`, JSON.stringify(filters), who, "/find");
  }
  redirect(`/find?${new URLSearchParams(filters)}`);
}

export async function deleteWatchRule(form: FormData): Promise<void> {
  const who = await requireUser();
  const { data } = await db().from("watch_rules").delete().eq("id", Number(form.get("id"))).select("name").maybeSingle();
  if (data) await logEvent("action", `Stopped watching "${data.name}"`, null, who, "/find");
  redirect("/find");
}
