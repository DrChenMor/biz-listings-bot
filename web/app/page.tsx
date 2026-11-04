import Link from "next/link";
import { Shell } from "@/components/shell";
import { requireUser } from "@/lib/auth";
import { db, link, when } from "@/lib/db";

export const dynamic = "force-dynamic";

async function count(filter: (q: any) => any): Promise<number> {
  const { count: total, error } = await filter(db().from("businesses").select("id", { count: "exact", head: true }).eq("on_sheet", true));
  if (error) throw new Error(error.message);
  return total ?? 0;
}

export default async function Today() {
  const user = await requireUser();
  const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const [forSale, practices, privateSellers, newThisWeek] = await Promise.all([
    count((q) => q.eq("kind", "sale").neq("status", "Removed")),
    count((q) => q.eq("kind", "practice")),
    count((q) => q.eq("route", "Private seller").neq("status", "Removed")),
    count((q) => q.eq("kind", "sale").gte("first_seen", weekAgo)),
  ]);
  const { data: steps } = await db().from("tracking").select("business_id, next_step, next_due, owner, businesses(name)")
    .not("next_step", "is", null).order("next_due", { ascending: true, nullsFirst: false }).limit(8);
  const { data: fresh } = await db().from("businesses").select("id, name, suburb, price_text, route").eq("kind", "sale").eq("on_sheet", true)
    .neq("status", "Removed").order("first_seen", { ascending: false, nullsFirst: false }).limit(8);
  const { data: runs } = await db().from("site_runs").select("*").order("site");

  return (
    <Shell user={user} active="/">
      <h1>Today</h1>
      <p className="lede">Real data, copied from the Google Sheet.</p>
      <div className="stats">
        <Link className="stat" href="/find?area=all"><span className="statnum">{forSale.toLocaleString()}</span><span className="statlab">For sale in WA</span></Link>
        <Link className="stat" href="/find?route=Private+seller&area=all"><span className="statnum">{privateSellers.toLocaleString()}</span><span className="statlab">Private sellers</span></Link>
        <Link className="stat" href="/find?area=all&fresh=1"><span className="statnum">{newThisWeek.toLocaleString()}</span><span className="statlab">New this week</span></Link>
        <Link className="stat" href="/find?show=practice&area=all"><span className="statnum">{practices.toLocaleString()}</span><span className="statlab">Health practices</span></Link>
      </div>
      <div className="cards">
        <section className="card"><h2>Do next</h2>
          {steps?.length ? steps.map((s: any) => (
            <Link className="item" key={s.business_id} href={link(s.business_id)}>
              <span className="ltitle">{s.next_step}</span>
              <span className="lsub">{s.businesses?.name}{s.next_due ? ` · due ${when(s.next_due)}` : ""}{s.owner ? ` · ${s.owner}` : ""}</span>
            </Link>
          )) : <p className="lsub">Nothing yet. Open a business in Find and set its next step.</p>}
        </section>
        <section className="card"><h2>Newest for sale</h2>
          {fresh?.map((b: any) => (
            <Link className="item" key={b.id} href={link(b.id)}>
              <span className="ltitle">{b.name}</span>
              <span className="lsub">{[b.suburb, b.price_text, b.route].filter(Boolean).join(" · ")}</span>
            </Link>
          ))}
        </section>
        <section className="card"><h2>Bots</h2>
          {runs?.map((r: any) => (
            <div className="item" key={r.site}>
              <span className="ltitle">{r.site}</span>
              <span className="lsub">{r.started} · {r.result}</span>
            </div>
          ))}
        </section>
      </div>
    </Shell>
  );
}
