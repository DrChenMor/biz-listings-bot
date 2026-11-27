import Link from "next/link";
import { Shell } from "@/components/shell";
import { requireUser } from "@/lib/auth";
import { db, link, when } from "@/lib/db";

export const dynamic = "force-dynamic";

type Entry = { at: string; who: string | null; kind: string; what: string; detail: string | null; business?: string | null; name?: string };

const KINDS: Record<string, string> = { error: "Error", problem: "Problem", "sign-in": "Sign-in", email: "Email copier", action: "Did" };

/** Everything that happened on the desk, newest first: what Chen and Tom did, and anything that went wrong. */
export default async function Log({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const user = await requireUser();
  const only = (await searchParams).only;
  const [{ data: events }, { data: actions }] = await Promise.all([
    db().from("app_log").select("at, who, kind, what, detail, path").order("at", { ascending: false }).limit(200),
    only === "problems" ? Promise.resolve({ data: [] }) : db().from("activity").select("at, who, text, business_id, businesses(name)").order("at", { ascending: false }).limit(200),
  ]);
  const entries: Entry[] = [
    ...((events ?? []) as Entry[]).filter((e) => only !== "problems" || e.kind === "error" || e.kind === "problem"),
    ...((actions ?? []) as unknown as { at: string; who: string; text: string; business_id: string; businesses: { name: string } | null }[])
      .map((a) => ({ at: a.at, who: a.who, kind: "action", what: a.text, detail: null, business: a.business_id, name: a.businesses?.name })),
  ].sort((a, b) => (a.at < b.at ? 1 : -1)).slice(0, 250);
  const problems = (events ?? []).filter((e) => e.kind === "error" || e.kind === "problem").length;

  return (
    <Shell user={user} active="/log">
      <h1>Log</h1>
      <p className="lede">What Chen and Tom did on the desk, and anything that went wrong, newest first.</p>
      <nav className="stagestrip" aria-label="Show">
        <Link href="/log" className={only ? "chip" : "chip on"}>Everything</Link>
        <Link href="/log?only=problems" className={only === "problems" ? "chip on" : "chip"}>Problems {problems}</Link>
      </nav>
      <div className="list">
        {entries.map((e, i) => (
          <div className={e.kind === "error" || e.kind === "problem" ? "row logrow bad" : "row logrow"} key={i}>
            <span className="c5 lsub">{when(e.at)} {new Date(e.at).toLocaleTimeString("en-AU", { timeZone: "Australia/Perth", hour: "2-digit", minute: "2-digit" })}</span>
            <span className="c2"><span className="tag">{KINDS[e.kind] ?? e.kind}</span></span>
            <span className="c1">
              <span className="ltitle">{e.who ? `${e.who}: ` : ""}{e.what}</span>
              {e.business ? <Link className="lsub" href={link(e.business)}>{e.name ?? e.business}</Link> : null}
              {e.detail ? <span className="lsub logdetail">{e.detail}</span> : null}
            </span>
          </div>
        ))}
      </div>
      {!entries.length ? <p className="note">Nothing here yet.</p> : null}
    </Shell>
  );
}
