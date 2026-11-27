/**
 * Tom's morning email: a short, readable page of what's new since yesterday and what to do today. A few items per
 * section, only the sections that have something, and one line about what the desk got done, read from the log.
 * No AI: the encouraging line is picked from what actually happened, worded a little differently each day.
 */
import { db, money, nameOf, today } from "./db";
import { followUpsDue } from "./followups";
import { fits, WatchRule, Watchable } from "./watch";

const MAX = 5;

type Item = { title: string; detail: string; href: string; action?: { label: string; href: string } };
type Section = { title: string; note?: string; items: Item[]; more?: { label: string; href: string } };

export type Digest = { subject: string; html: string; text: string; send: boolean };

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const dayOfYear = () => Math.floor((Date.now() - Date.UTC(new Date().getUTCFullYear(), 0, 0)) / 864e5);
const pick = <T,>(options: T[]) => options[dayOfYear() % options.length];

/** One line about yesterday, from the log: what moved, who was followed up, what was filed. */
export function encouragement(stats: { moved: string[]; emailed: number; filed: number; named: number; due: number }): string {
  const parts: string[] = [];
  if (stats.emailed) parts.push(pick([`you followed up ${plural(stats.emailed, "seller")}`, `${plural(stats.emailed, "follow-up email")} went out`]));
  if (stats.moved.length) parts.push(`${plural(stats.moved.length, "business", "businesses")} moved forward${stats.moved.length <= 2 ? ` (${stats.moved.join(", ")})` : ""}`);
  if (stats.filed) parts.push(`${plural(stats.filed, "document")} filed`);
  if (stats.named) parts.push(`${plural(stats.named, "business", "businesses")} got ${stats.named === 1 ? "its" : "their"} real name`);
  if (parts.length) {
    const said = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
    return pick([
      `Yesterday ${said}. That's how deals keep moving.`,
      `Nice work yesterday: ${said}.`,
      `Good momentum: yesterday ${said}.`,
    ]);
  }
  return stats.due
    ? pick([
      `A quiet day yesterday. A couple of the follow-ups below would keep things warm.`,
      `Nothing moved yesterday, and that's fine. Today, ${plural(Math.min(stats.due, 2), "quick follow-up")} would keep sellers warm.`,
    ])
    : `All caught up. Here's what's new.`;
}

export async function buildDigest(site: string): Promise<Digest> {
  const since = new Date(Date.now() - 24 * 3600e3).toISOString();
  const page = (id: string) => `${site}/b/${encodeURIComponent(id)}`;
  const [due, mailRes, ruleRes, newRes, dropRes, endedRes, actRes, outRes] = await Promise.all([
    followUpsDue(),
    db().from("mail").select("business_id, sender, subject, body, sent_at, businesses(name)").eq("incoming", true).gte("saved_at", since).order("sent_at", { ascending: false }).limit(20),
    db().from("watch_rules").select("id, name, filters"),
    db().from("find_list").select("id, kind, status, perth, route, types, site, suburb, price, price_text, turnover, profit, phone, search_text, display_name, name, archived_at")
      .gte("first_seen", since).eq("on_sheet", true).is("same_as", null).neq("status", "Removed").limit(400),
    db().from("find_list").select("id, name, display_name, price, previous_price, kind, status, perth, route, types, site, suburb, turnover, profit, phone, search_text, mark")
      .gte("price_dropped_at", since).limit(200),
    db().from("tracking").select("business_id, display_name, stage, archived_at, businesses!inner(name, ended_at)").is("archived_at", null).gte("businesses.ended_at", since),
    db().from("activity").select("who, text, business_id, businesses(name)").gte("at", since).limit(500),
    db().from("mail").select("business_id").eq("incoming", false).gte("sent_at", since),
  ]);
  const rules = (ruleRes.data ?? []) as WatchRule[];
  const sections: Section[] = [];

  if (due.length) {
    sections.push({
      title: "Follow up today", note: "Approached, and no contact for a week or more.",
      items: due.slice(0, MAX).map((d) => ({
        title: d.name, detail: d.last ? `${d.days} days since the last contact` : "No approach date yet", href: `${site}${d.page}`,
        action: d.follow ? { label: "Follow up", href: d.follow } : undefined,
      })),
      more: due.length > MAX ? { label: `${due.length - MAX} more on Today`, href: site } : undefined,
    });
  }

  const mail = (mailRes.data ?? []) as unknown as { business_id: string; sender: string; subject: string | null; body: string | null; businesses: { name: string } | null }[];
  if (mail.length) {
    sections.push({
      title: "New from sellers and brokers",
      items: mail.slice(0, MAX).map((m) => ({
        title: `${(m.sender ?? "").replace(/<[^>]*>/g, "").replace(/"/g, "").trim()} · ${m.businesses?.name ?? m.business_id}`,
        detail: `${m.subject ? `${m.subject}: ` : ""}${(m.body ?? "").replace(/\s+/g, " ").slice(0, 140)}${(m.body ?? "").length > 140 ? "…" : ""}`,
        href: page(m.business_id),
      })),
    });
  }

  const fresh = ((newRes.data ?? []) as unknown as (Watchable & { id: string; name: string; price_text: string | null; archived_at: string | null })[])
    .filter((b) => !b.archived_at).map((b) => ({ b, fitting: rules.filter((r) => fits(b, r.filters)).map((r) => r.name) }))
    .filter((x) => x.fitting.length);
  if (fresh.length) {
    sections.push({
      title: "New listings that fit what you look for",
      items: fresh.slice(0, MAX).map(({ b, fitting }) => ({
        title: nameOf(b, b), detail: [b.price_text, b.suburb, `★ ${fitting.join(", ")}`].filter(Boolean).join(" · "), href: page(b.id),
      })),
      more: fresh.length > MAX ? { label: `${fresh.length - MAX} more in Find`, href: `${site}/find?fresh=1` } : undefined,
    });
  }

  const drops = ((dropRes.data ?? []) as unknown as (Watchable & { id: string; name: string; previous_price: number; mark: string })[])
    .filter((b) => b.mark === "In pipeline" || b.mark === "Interested" || rules.some((r) => fits(b, r.filters)));
  if (drops.length) {
    sections.push({
      title: "Price drops",
      note: "A lower asking price often means a seller ready to talk.",
      items: drops.slice(0, MAX).map((b) => ({
        title: nameOf(b, b), detail: `Now ${money(b.price)}, down from ${money(b.previous_price)}`, href: page(b.id),
      })),
    });
  }

  const ended = (endedRes.data ?? []) as unknown as { business_id: string; display_name: string | null; stage: string; businesses: { name: string } }[];
  if (ended.length) {
    sections.push({
      title: "Listings that ended",
      note: "Taken off the sites: sold, withdrawn, or the seller may still talk.",
      items: ended.slice(0, MAX).map((t) => ({ title: nameOf(t.businesses, t), detail: `At ${t.stage} in the pipeline`, href: page(t.business_id) })),
    });
  }

  const acts = (actRes.data ?? []) as unknown as { who: string; text: string; business_id: string; businesses: { name: string } | null }[];
  const people = acts.filter((a) => a.who === "Tom" || a.who === "Chen");
  const forward = new Set(["Approached", "NDA signed", "Documents in", "First meet", "Deal analysis", "Pitch / offer", "Term sheet", "Due diligence", "Deal closed", "Completion"]);
  const moved = [...new Set(people.filter((a) => a.text.startsWith("Moved to ") && forward.has(a.text.slice(9))).map((a) => a.businesses?.name?.split(/[|–-]/)[0].trim().slice(0, 40) ?? ""))].filter(Boolean);
  const line = encouragement({
    moved, emailed: new Set((outRes.data ?? []).map((m) => m.business_id)).size,
    filed: people.filter((a) => a.text.startsWith("Added ") && a.text.includes("Drive folder")).length,
    named: people.filter((a) => a.text.startsWith("Renamed to ")).length, due: due.length,
  });

  const counts = [due.length && plural(due.length, "follow-up"), mail.length && plural(mail.length, "new email"), fresh.length && plural(fresh.length, "new match", "new matches")].filter(Boolean);
  const subject = counts.length ? `Deal desk: ${counts.join(", ")}` : "Deal desk: your morning update";
  return { subject, html: html(line, sections, site), text: text(line, sections, site), send: sections.length > 0 };
}

function html(line: string, sections: Section[], site: string): string {
  const date = new Date().toLocaleDateString("en-AU", { timeZone: "Australia/Perth", weekday: "long", day: "numeric", month: "long" });
  const block = (s: Section) => `
    <tr><td style="padding:22px 28px 4px">
      <div style="font:700 17px/1.3 Arial,Helvetica,sans-serif;color:#1b1530">${esc(s.title)}</div>
      ${s.note ? `<div style="font:13px/1.4 Arial,Helvetica,sans-serif;color:#6b6780;margin-top:2px">${esc(s.note)}</div>` : ""}
    </td></tr>
    ${s.items.map((i) => `
    <tr><td style="padding:8px 28px">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #ece8f8;border-radius:12px">
        <tr><td style="padding:12px 14px">
          <a href="${esc(i.href)}" style="font:600 15px/1.35 Arial,Helvetica,sans-serif;color:#1b1530;text-decoration:none">${esc(i.title)}</a>
          <div style="font:13px/1.45 Arial,Helvetica,sans-serif;color:#57536a;margin-top:3px">${esc(i.detail)}</div>
          ${i.action ? `<div style="margin-top:9px"><a href="${esc(i.action.href)}" style="display:inline-block;background:#6c47ff;color:#ffffff;font:600 13px Arial,Helvetica,sans-serif;text-decoration:none;padding:8px 14px;border-radius:8px">${esc(i.action.label)}</a></div>` : ""}
        </td></tr>
      </table>
    </td></tr>`).join("")}
    ${s.more ? `<tr><td style="padding:2px 28px 0"><a href="${esc(s.more.href)}" style="font:13px Arial,Helvetica,sans-serif;color:#6c47ff">${esc(s.more.label)}</a></td></tr>` : ""}`;
  return `<!doctype html><html><body style="margin:0;padding:0;background:#f7f5ff">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f5ff"><tr><td align="center" style="padding:24px 12px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:18px;overflow:hidden">
      <tr><td style="background:#15102a;padding:22px 28px">
        <div style="font:700 20px Arial,Helvetica,sans-serif;color:#ffffff">Good morning, Tom</div>
        <div style="font:13px Arial,Helvetica,sans-serif;color:#b9b2d6;margin-top:3px">${esc(date)} · Deal desk</div>
      </td></tr>
      <tr><td style="padding:20px 28px 0">
        <div style="font:15px/1.5 Arial,Helvetica,sans-serif;color:#1b1530;background:#f1edff;border-radius:12px;padding:12px 14px">${esc(line)}</div>
      </td></tr>
      ${sections.map(block).join("")}
      <tr><td style="padding:26px 28px 28px">
        <a href="${esc(site)}/pipeline" style="display:inline-block;border:1px solid #d9cffd;color:#6c47ff;font:600 14px Arial,Helvetica,sans-serif;text-decoration:none;padding:10px 16px;border-radius:10px">Open the Pipeline</a>
        <div style="font:12px/1.5 Arial,Helvetica,sans-serif;color:#9a95ad;margin-top:16px">Sent by the Deal desk email copier, from your own Google account, only to you.</div>
      </td></tr>
    </table>
  </td></tr></table></body></html>`;
}

function text(line: string, sections: Section[], site: string): string {
  return [`Good morning, Tom`, "", line, "",
    ...sections.flatMap((s) => [s.title.toUpperCase(), ...s.items.map((i) => `- ${i.title}: ${i.detail}\n  ${i.action ? i.action.href : i.href}`), ""]),
    `Open the Pipeline: ${site}/pipeline`].join("\n");
}

/** Today's Perth date, for the log. */
export const digestDay = () => today();
