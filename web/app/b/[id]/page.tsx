import Link from "next/link";
import { notFound } from "next/navigation";
import { AgentCard } from "@/components/agent-card";
import { DealCardForm } from "@/components/deal-card";
import { DriveCard } from "@/components/drive-card";
import { ReviewMark } from "@/components/review-mark";
import { Shell } from "@/components/shell";
import { addNote, archiveBusiness, deleteBusiness, restoreBusiness, setNextStep } from "@/lib/actions";
import { requireUser } from "@/lib/auth";
import { Business, BY_HAND, db, Fact, link, nameOf, routeClass, Tracking, when } from "@/lib/db";

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
  const name = nameOf(b, tracking);
  const { data: review } = await db().from("reviews").select("mark").eq("business_id", id).maybeSingle();
  const mark = tracking?.archived_at ? "Archived" : tracking?.stage === "Passed" ? "Passed" : tracking ? "In pipeline" : review?.mark ?? "Not reviewed";

  return (
    <Shell user={user} active="/find">
      <Link href="/find">Back to Find</Link>
      <div className="bhead">
        <div>
          <h1>{name}</h1>
          {name !== b.name ? <p className="headline">Listed as: {b.name}</p> : null}
          <p className="lede" style={{ marginBottom: 8 }}>{[b.types[0], b.suburb, b.status].filter(Boolean).join(" · ")}</p>
          <span className="actions"><span className={routeClass(b.route)}>{b.route}</span><ReviewMark key={mark} id={b.id} mark={mark} name={name} /></span>
        </div>
        <div className="actions">
          {b.phone ? <a className="btn primary" href={`tel:${b.phone.split(";")[0].replace(/[^+\d]/g, "")}`}>Call {b.phone.split(";")[0]}</a> : null}
          {b.url ? <a className="btn" href={b.url} target="_blank" rel="noreferrer">Original listing</a> : null}
          {b.map_url ? <a className="btn" href={b.map_url} target="_blank" rel="noreferrer">Map</a> : null}
        </div>
      </div>
      {tracking?.archived_at ? (
        <div className="note warn archived" role="status">
          <span>Archived {when(tracking.archived_at)}{tracking.archived_by ? ` by ${tracking.archived_by}` : ""}. It's hidden from Pipeline, Today and Find.</span>
          <form action={restoreBusiness}><input type="hidden" name="id" value={b.id} /><button type="submit" className="btn">Restore</button></form>
        </div>
      ) : null}
      {b.same_as ? <p className="note">This is the same business as <Link href={link(b.same_as)}>another listing</Link>, which is the one shown in Find.</p> : null}
      {b.also_on?.length ? <p className="note">Also listed (or posted again) on {b.also_on.map((c, i) => <span key={c.id}>{i ? ", " : ""}{c.url ? <a href={c.url} target="_blank" rel="noreferrer">{c.site}{c.where ? ` (${c.where})` : ""}</a> : c.site}</span>)}.</p> : null}
      {broker ? <p className="note">This listing stays with the broker. Contact goes through them.</p> : null}
      {b.route === "Needs a pharmacist" ? <p className="note warn">In WA, only pharmacists and certain companies and partnerships they control can own a pharmacy.</p> : null}
      {b.on_sheet || b.site === BY_HAND ? null : <p className="note warn">This business has left the Sheet, so it may be sold or gone.</p>}
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
          <DealCardForm business={b} tracking={tracking} />
          <DriveCard business={b} tracking={tracking} />
          {tracking && !tracking.archived_at ? (
            <section className="card"><h2>Archive or delete</h2>
              <form action={archiveBusiness} className="stack">
                <input type="hidden" name="id" value={b.id} />
                <p className="lsub">For a business that's off the table, passed on or gone. It leaves every list; nothing is deleted, and Restore brings it back.</p>
                {tracking.drive_folder_id ? <label className="lsub dcheck"><input type="checkbox" name="move_folder" value="yes" defaultChecked /> Also move its Drive folder to Passed</label> : null}
                <button type="submit" className="btn">Archive {name.slice(0, 40)}</button>
              </form>
              <details className="dline" style={{ marginTop: 10 }}>
                <summary className="lsub">Delete it now instead</summary>
                <form action={deleteBusiness} className="stack">
                  <input type="hidden" name="id" value={b.id} /><input type="hidden" name="sure" value="yes" /><input type="hidden" name="back" value="/pipeline" />
                  <p className="lsub">{b.site === BY_HAND ? "Removes it, its card, worksheets and notes from the website."
                    : "Removes it from the pipeline with its card and worksheets, and marks it Not for us in Find."}</p>
                  {tracking.drive_folder_id ? <label className="lsub dcheck"><input type="checkbox" name="bin_folder" value="yes" /> Also put its Drive folder in the Drive bin</label> : null}
                  <button type="submit" className="btn danger">Yes, delete {name.slice(0, 40)}</button>
                </form>
              </details>
            </section>
          ) : null}
          {b.kind === "sale" && b.site !== BY_HAND ? <AgentCard business={b} /> : null}
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
