import Link from "next/link";
import { Shell } from "@/components/shell";
import { requireUser } from "@/lib/auth";
import { db, Enquiry, link, statusClass, when } from "@/lib/db";

export const dynamic = "force-dynamic";

type Row = Enquiry & { businesses: { name: string; suburb: string | null } | null };

const GROUPS: { title: string; empty: string; has: (status: string) => boolean }[] = [
  { title: "Needs you", empty: "Nothing is waiting on you.", has: (s) => s === "Needs you" || s === "Stopped" },
  { title: "Under way", empty: "Open a business and press Send first enquiry to start one.", has: (s) => !["Needs you", "Stopped", "Evaluated", "Closed"].includes(s) },
  { title: "Finished", empty: "Nothing has finished yet.", has: (s) => s === "Evaluated" || s === "Closed" },
];

export default async function Agent() {
  const user = await requireUser();
  const { data, error } = await db().from("enquiries").select("*, businesses(name, suburb)").order("updated_at", { ascending: false }).limit(300);
  if (error) throw new Error(error.message);
  const rows = (data ?? []) as unknown as Row[];

  return (
    <Shell user={user} active="/agent">
      <h1>Agent</h1>
      <p className="lede">The first approach to each broker: enquiry, reply, NDA, documents, evaluation.</p>
      <div className="stack">
        {GROUPS.map((group) => {
          const items = rows.filter((row) => group.has(row.status));
          return (
            <section key={group.title}>
              <h2>{group.title}{items.length ? ` (${items.length})` : ""}</h2>
              {items.length ? (
                <div className="list">
                  {items.map((row) => (
                    <Link className="row" key={row.id} href={link(row.business_id)}>
                      <span className="c1"><span className="ltitle">{row.businesses?.name}</span><span className="lsub">{row.businesses?.suburb}</span></span>
                      <span className="c2"><span className={statusClass(row.status)}>{row.status}</span></span>
                      <span className="c3 lsub">{row.detail}</span>
                      <span className="c5 lsub">{when(row.updated_at)}</span>
                    </Link>
                  ))}
                </div>
              ) : <p className="lsub">{group.empty}</p>}
            </section>
          );
        })}
      </div>
    </Shell>
  );
}
