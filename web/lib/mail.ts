/**
 * The email copier's server side. The Apps Script in Tom's Google account reads his deals inbox and sends each email
 * here; this decides which pipeline business it belongs to, keeps one copy per business, and hands back the text the
 * script adds to that business's Communication doc. No AI: matching is by the contacts Tom adds to each business.
 */
import { createHash, timingSafeEqual } from "node:crypto";
import { db, nameOf } from "./db";

export type IncomingMail = {
  id: string; threadId?: string; date: string; from: string; to?: string; cc?: string; subject?: string; body?: string;
  attachments?: string[];
};

export type Target = { business_id: string; name: string; folder_id: string | null; text: string };

/** The key the script sends, checked without leaking its length or content through timing. */
export function keyIsRight(given: string | null): boolean {
  const expected = process.env.MAIL_SYNC_SECRET;
  if (!expected || !given) return false;
  const hash = (text: string) => createHash("sha256").update(text).digest();
  return timingSafeEqual(hash(given), hash(expected));
}

/** Every address in a header like `Shalee <shalee@x.com>, tom@y.com`, lower-cased. */
export function addresses(header = ""): string[] {
  return [...new Set((header.match(/[\w.+'-]+@[\w-]+(\.[\w-]+)+/g) ?? []).map((a) => a.toLowerCase()))];
}

/** The display name in `Shalee Smith <shalee@x.com>`, or the address. */
export function displayName(header = ""): string {
  const named = header.match(/^\s*"?([^"<]+?)"?\s*</);
  return named ? named[1].trim() : addresses(header)[0] ?? header.trim();
}

// Where an earlier message starts underneath a reply: Gmail, Outlook and Apple Mail each write it differently.
const QUOTE_STARTS = [
  /^On .{6,200}(wrote|writes):\s*$/,
  /^On .{6,120}$/, // Gmail sometimes breaks "On ..., X <x@y> wrote:" over two lines; checked with the next line below
  /^-{2,}\s*Original Message\s*-{2,}/i,
  /^_{5,}\s*$/,
  /^From:\s.+/i,
  /^Sent from my (iPhone|iPad|Android|mobile)/i,
  /^Get Outlook for /i,
];

/**
 * The new part of an email: everything above the quoted earlier messages, with trailing blank lines removed.
 * Leaves the text untouched if cutting would leave nothing.
 */
export function newPart(body = ""): string {
  const lines = body.replace(/\r\n/g, "\n").split("\n");
  let cut = lines.length;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith(">")) { cut = i; break; }
    const next = (lines[i + 1] ?? "").trim();
    if (QUOTE_STARTS[0].test(line) || (QUOTE_STARTS[1].test(line) && /wrote:\s*$/.test(next))) { cut = i; break; }
    if (QUOTE_STARTS.slice(2).some((pattern) => pattern.test(line))) {
      // "From:" only counts as a quote when an Outlook header block follows it.
      if (/^From:/i.test(line) && !/^(Sent|Date|To):/i.test(next)) continue;
      cut = i;
      break;
    }
  }
  const kept = lines.slice(0, cut).join("\n").replace(/\n{3,}/g, "\n\n").trim();
  return kept || body.trim();
}

/** Perth date as Tom writes it in the Communication doc: 17/11/2026. */
export function perthDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-AU", { timeZone: "Australia/Perth", day: "2-digit", month: "2-digit", year: "numeric" });
}

/** The text the script adds to the bottom of the Communication doc for one email. */
export function docText(mail: IncomingMail, incoming: boolean): string {
  const who = incoming ? `From ${displayName(mail.from)} (${addresses(mail.from)[0] ?? ""})` : `Tom to ${displayName(mail.to)}`;
  const files = mail.attachments?.length ? `\nAttached: ${mail.attachments.join(", ")} (saved in this folder)` : "";
  return `${perthDate(mail.date)}\n${who}${mail.subject ? `: ${mail.subject}` : ""}\n\n${newPart(mail.body)}${files}`;
}

type ContactRow = { business_id: string; email: string };
type Business = { id: string; name: string; display_name: string | null; folder_id: string | null };

/** Which businesses an email belongs to. A broker can deal with two of our businesses: then the subject or text decides. */
export function matchBusinesses(mail: IncomingMail, contacts: ContactRow[], businesses: Map<string, Business>): string[] {
  const people = new Set([...addresses(mail.from), ...addresses(mail.to), ...addresses(mail.cc)]);
  const ids = [...new Set(contacts.filter((c) => people.has(c.email)).map((c) => c.business_id))].filter((id) => businesses.has(id));
  if (ids.length < 2) return ids;
  const text = `${mail.subject ?? ""}\n${mail.body ?? ""}`.toLowerCase();
  const named = ids.filter((id) => {
    const b = businesses.get(id)!;
    const words = nameOf(b, b).toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 3);
    const number = nameOf(b, b).match(/\b\d{5}\b/)?.[0];
    return (number && text.includes(number)) || (words.length > 0 && words.filter((w) => text.includes(w)).length >= Math.min(2, words.length));
  });
  return named.length ? named : ids;
}

/** Perth calendar day of an email, as the database stores dates: 2026-11-17. */
function perthDay(iso: string): string {
  return new Date(iso).toLocaleDateString("en-CA", { timeZone: "Australia/Perth" });
}

/**
 * Tom's own email to a contact keeps the card's dates true without anyone typing them: the earliest one is when the
 * business was approached (unless an earlier date is already there), and any later one is the latest follow-up.
 */
export async function datesFromTomsEmail(businessId: string, sentAt: string): Promise<void> {
  const day = perthDay(sentAt);
  const { data } = await db().from("tracking").select("approached_on, followed_up_on").eq("business_id", businessId).maybeSingle();
  if (!data) return;
  const change: Record<string, string> = {};
  if (!data.approached_on || day < data.approached_on) change.approached_on = day;
  else if (day > data.approached_on && (!data.followed_up_on || day > data.followed_up_on)) change.followed_up_on = day;
  if (Object.keys(change).length) await db().from("tracking").update(change).eq("business_id", businessId);
}

const IGNORED_SENDER = /(no-?reply|do-?not-?reply|notifications?|mailer-daemon|postmaster|newsletter|alerts?)@/i;

/**
 * Save a batch of emails. Returns, for each email that's new for a business, where the script should copy it.
 * Emails that match no business go to the Not matched list, unless their sender was dismissed before.
 */
export async function saveMail(batch: IncomingMail[]): Promise<{ id: string; targets: Target[]; unmatched: boolean }[]> {
  const [{ data: contacts }, { data: tracked }] = await Promise.all([
    db().from("contacts").select("business_id, email"),
    db().from("tracking").select("business_id, display_name, drive_folder_id, archived_at, businesses(name)"),
  ]);
  const businesses = new Map<string, Business>(((tracked ?? []) as unknown as {
    business_id: string; display_name: string | null; drive_folder_id: string | null; archived_at: string | null; businesses: { name: string };
  }[]).filter((t) => !t.archived_at).map((t) => [t.business_id, {
    id: t.business_id, name: t.businesses.name, display_name: t.display_name, folder_id: t.drive_folder_id,
  }]));
  const ids = batch.map((m) => m.id);
  const [{ data: known }, { data: dismissed }] = await Promise.all([
    db().from("mail").select("gmail_id, business_id").in("gmail_id", ids),
    db().from("unmatched_mail").select("sender").eq("dismissed", true),
  ]);
  const already = new Set((known ?? []).map((k) => `${k.gmail_id}|${k.business_id}`));
  const ignored = new Set((dismissed ?? []).map((d) => (d.sender ?? "").toLowerCase()));
  const results = [];
  for (const mail of batch) {
    if (!mail.id || !mail.date || !mail.from) continue;
    const sender = addresses(mail.from)[0] ?? "";
    const matched = matchBusinesses(mail, contacts ?? [], businesses);
    if (!matched.length) {
      const skip = !sender || IGNORED_SENDER.test(sender) || ignored.has(sender);
      if (!skip) {
        await db().from("unmatched_mail").upsert({
          gmail_id: mail.id, thread_id: mail.threadId ?? null, sent_at: mail.date, sender, sender_name: displayName(mail.from),
          subject: (mail.subject ?? "").slice(0, 300), snippet: newPart(mail.body).slice(0, 300),
        }, { onConflict: "gmail_id", ignoreDuplicates: true });
      }
      results.push({ id: mail.id, targets: [], unmatched: !skip });
      continue;
    }
    // Incoming when a contact wrote it; otherwise Tom wrote to one of them.
    const incoming = (contacts ?? []).some((c) => matched.includes(c.business_id) && c.email === sender);
    const targets: Target[] = [];
    for (const id of matched.filter((m) => !already.has(`${mail.id}|${m}`))) {
      const b = businesses.get(id)!;
      const { error } = await db().from("mail").insert({
        gmail_id: mail.id, business_id: id, thread_id: mail.threadId ?? null, sent_at: mail.date, sender: mail.from,
        recipients: [mail.to, mail.cc].filter(Boolean).join(", "), subject: mail.subject ?? null, body: newPart(mail.body),
        incoming, attachments: mail.attachments ?? [],
      });
      if (error && error.code !== "23505") throw new Error(error.message);
      if (error) continue;
      if (!incoming) await datesFromTomsEmail(id, mail.date);
      await db().from("activity").insert({
        business_id: id, who: "Email copier",
        text: `${incoming ? `Email from ${displayName(mail.from)}` : `Tom emailed ${displayName(mail.to)}`}${mail.subject ? `: ${mail.subject}` : ""}`.slice(0, 300),
      });
      targets.push({ business_id: id, name: nameOf(b, b), folder_id: b.folder_id, text: docText(mail, incoming) });
    }
    await db().from("unmatched_mail").delete().eq("gmail_id", mail.id);
    results.push({ id: mail.id, targets, unmatched: false });
  }
  return results;
}

const DEALS_INBOX = "contacttomharari@gmail.com";

/**
 * A link that opens Tom's deals Gmail ready to follow up: the last email thread with the business's contacts if there
 * is one (so the reply keeps the history), or else a new email to them with a short draft. Tom reviews and presses
 * Send himself; the website never sends email.
 */
export function followUpLink(businessName: string, contacts: { email: string; name: string | null }[], lastThread: string | null): string | null {
  if (lastThread) return `https://mail.google.com/mail/?authuser=${encodeURIComponent(DEALS_INBOX)}#all/${encodeURIComponent(lastThread)}`;
  if (!contacts.length) return null;
  const first = (contacts[0].name ?? "").split(/\s+/)[0];
  const params = new URLSearchParams({
    authuser: DEALS_INBOX, view: "cm", fs: "1", to: contacts.map((c) => c.email).join(","),
    su: `Following up: ${businessName}`,
    body: `Hi ${first || "there"},\n\nI'm following up on ${businessName}. Is it still available, and could we take the next step?\n\nKind regards,\nTom`,
  });
  return `https://mail.google.com/mail/?${params}`;
}
