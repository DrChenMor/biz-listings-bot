/**
 * Businesses that need a follow-up: approached, and no email or follow-up for a week or more. The dates come from
 * Tom's own emails (the email copier) and the "Followed up today" button, so the list keeps itself up to date.
 */
import { db, link, nameOf, today } from "./db";
import { followUpLink } from "./mail";

export const FOLLOW_UP_AFTER_DAYS = 7;

export type Due = { id: string; name: string; days: number; last: string; page: string; follow: string | null };

const daysBetween = (from: string, to: string) => Math.round((Date.parse(to) - Date.parse(from)) / 864e5);

export async function followUpsDue(): Promise<Due[]> {
  const [{ data: tracked }, { data: contacts }, { data: threads }] = await Promise.all([
    db().from("tracking").select("business_id, display_name, approached_on, followed_up_on, archived_at, businesses(name, status)")
      .eq("stage", "Approached").is("archived_at", null),
    db().from("contacts").select("business_id, email, name"),
    db().from("mail").select("business_id, thread_id, sent_at").not("thread_id", "is", null).order("sent_at", { ascending: false }).limit(1000),
  ]);
  const now = today();
  return ((tracked ?? []) as unknown as {
    business_id: string; display_name: string | null; approached_on: string | null; followed_up_on: string | null;
    businesses: { name: string; status: string | null } | null;
  }[])
    .filter((t) => t.businesses && t.businesses.status !== "Removed")
    .map((t) => {
      const last = [t.approached_on, t.followed_up_on].filter(Boolean).sort().pop() ?? null;
      const name = nameOf(t.businesses!, t);
      return {
        id: t.business_id, name, last: last ?? "", days: last ? daysBetween(last, now) : 999, page: link(t.business_id),
        follow: followUpLink(name, (contacts ?? []).filter((c) => c.business_id === t.business_id),
          (threads ?? []).find((m) => m.business_id === t.business_id)?.thread_id ?? null),
      };
    })
    .filter((d) => d.days >= FOLLOW_UP_AFTER_DAYS)
    .sort((a, b) => b.days - a.days);
}
