import Link from "next/link";
import { notFound } from "next/navigation";
import { AgentCard } from "@/components/agent-card";
import { Shell } from "@/components/shell";
import { addNote, setNextStep, setStage } from "@/lib/actions";
import { requireUser } from "@/lib/auth";
import { Business, db, Fact, routeClass, STAGES, Tracking, when } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function BusinessPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await requireUser();
  const id = decodeURIComponent((await params).id);
  const { data } = await db().from("businesses").select("*").eq("id", id).maybeSingle();
  if (!data) notFound();
  const b = data as Business;
  const { data: track } = await db().from("tracking").select("*").eq("business_id", id).maybeSingle();
  const tracking = track as Tracking | null;
  const { data: log } = await db().from("activity").select("*").eq("business_id", id).order("at", { ascending: false }).limit(30);
  const broker = b.route === "Via broker";

  return (
    <Shell user={user} active="/find">
      <Link href="/find">Back to Find</Link>
      <div className="bhead">
        <div>
          <h1>{b.name}</h1>
          <p className="lede" style={{ marginBottom: 8 }}>{[b.types[0], b.suburb, b.status].filter(Boolean).join(" · ")}</p>
          <span className={routeClass(b.route)}>{b.route}</span>
        </div>
        <div className="actions">
          {b.phone ? <a className="btn primary" href={`tel:${b.phone.split(";")[0].replace(/[^+\d]/g, "")}`}>Call {b.phone.split(";")[0]}</a> : null}
          {b.url ? <a className="btn" href={b.url} target="_blank" rel="noreferrer">Original listing</a> : null}
          {b.map_url ? <a className="btn" href={b.map_url} target="_blank" rel="noreferrer">Map</a> : null}
        </div>
      </div>
      {broker ? <p className="note">This listing stays with the broker. Contact goes through them.</p> : null}
      {b.route === "Needs a pharmacist" ? <p className="note warn">In WA, only pharmacists and certain companies and partnerships they control can own a pharmacy.</p> : null}
      {b.on_sheet ? null : <p className="note warn">This business has left the Sheet, so it may be sold or gone.</p>}
      <div className="twocol">
        <div className="stack">
          <section className="card"><h2>What we know</h2>
            {b.facts.map((f: Fact) => (
              <div className="fact" key={f.label}>
                <span className="flab">{f.label}</span><span className="fval">{f.value}</span>
                <span className="fsrc">{f.source}{f.date ? `, ${f.date}` : ""}</span>
              </div>
            ))}
          </section>
          {b.description ? <section className="card"><h2>In their words</h2><div className="writing">{b.description.replace(/\*\*/g, "")}</div></section> : null}
        </div>
        <div className="stack">
          {b.kind === "sale" ? <AgentCard business={b} /> : null}
          <section className="card"><h2>Stage</h2>
            <form action={setStage} className="actions">
              <input type="hidden" name="id" value={b.id} />
              <select name="stage" aria-label="Stage" defaultValue={tracking?.stage ?? "New"}>{[...STAGES, "Passed"].map((s) => <option key={s}>{s}</option>)}</select>
              <button type="submit" className="btn">{tracking ? "Save" : "Add to pipeline"}</button>
            </form>
          </section>
          <section className="card"><h2>Next step</h2>
            <form action={setNextStep} className="stack">
              <input type="hidden" name="id" value={b.id} />
              <label className="field">What's next<input className="input" name="step" defaultValue={tracking?.next_step ?? ""} /></label>
              <label className="field">When<input className="input" type="date" name="due" defaultValue={tracking?.next_due ?? ""} /></label>
              <button type="submit" className="btn">Save next step</button>
            </form>
          </section>
          <section className="card"><h2>History</h2>
            <form action={addNote} className="actions">
              <input type="hidden" name="id" value={b.id} />
              <input className="input" name="text" aria-label="Add a note" placeholder="Add a note, like a call you made" style={{ flex: "1 1 180px" }} />
              <button type="submit" className="btn">Add</button>
            </form>
            {log?.map((l: any) => <div className="log" key={l.id}><span className="ldate">{when(l.at)} · {l.who}</span>{l.text}</div>)}
          </section>
        </div>
      </div>
    </Shell>
  );
}
