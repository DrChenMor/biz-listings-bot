import Link from "next/link";
import { Shell } from "@/components/shell";
import { addBusiness, followedUp, moveOn, setStage } from "@/lib/actions";
import { requireUser } from "@/lib/auth";
import { Business, dealCard, db, link, money, NEXT_STAGE, PASSED, STAGES, Tracking, when } from "@/lib/db";

export const dynamic = "force-dynamic";

type Row = Tracking & { businesses: Business };

const anchor = (stage: string) => `stage-${stage.toLowerCase().replace(/[^a-z]+/g, "-")}`;

function Figure({ label, value }: { label: string; value: number | null }) {
  return <div><dt>{label}</dt><dd className="fig">{value ? money(value) : "—"}</dd></div>;
}

function DealCard({ row }: { row: Row }) {
  const b = row.businesses;
  const card = dealCard(b, row);
  const next = NEXT_STAGE[row.stage];
  return (
    <article className="dcard">
      <Link href={link(b.id)} className="dname">{b.name}</Link>
      <span className="lsub">{[card.location, card.product].filter(Boolean).join(" · ")}</span>
      <dl className="dfacts">
        <Figure label="Asking" value={card.asking} />
        <Figure label="Turnover" value={card.turnover} />
        <Figure label="Expenses" value={card.expenses} />
        <Figure label="Profit" value={card.profit} />
      </dl>
      {card.sellingReason ? <p className="dline"><b>Selling:</b> {card.sellingReason}</p> : null}
      {card.underManagement ? <p className="dline"><b>Under management:</b> {card.underManagement}</p> : null}
      <p className="dline lsub">
        {row.approached_on ? `Approached ${when(row.approached_on)}` : "Not approached yet"}
        {row.followed_up_on ? ` · followed up ${when(row.followed_up_on)}` : ""}
      </p>
      {row.next_step ? <p className="dline"><b>Next:</b> {row.next_step}{row.next_due ? ` (by ${when(row.next_due)})` : ""}</p> : null}
      <div className="dbuttons">
        {next ? (
          <form action={moveOn}><input type="hidden" name="id" value={b.id} /><input type="hidden" name="stage" value={row.stage} />
            <button type="submit" className="pmove">Move to {next}</button></form>
        ) : null}
        {row.stage === "Approached" ? (
          <form action={followedUp}><input type="hidden" name="id" value={b.id} /><input type="hidden" name="back" value="/pipeline" />
            <button type="submit" className="pmove">Followed up today</button></form>
        ) : null}
        {row.stage === "Due diligence" ? (
          <form action={setStage}><input type="hidden" name="id" value={b.id} /><input type="hidden" name="stage" value="Deal re-work" />
            <input type="hidden" name="back" value="/pipeline" /><button type="submit" className="pmove">Needs re-work</button></form>
        ) : null}
      </div>
    </article>
  );
}

export default async function Pipeline() {
  const user = await requireUser();
  const { data, error } = await db().from("tracking").select("*, businesses(*)").order("updated_at", { ascending: false });
  if (error) throw new Error(error.message);
  const rows = (data ?? []) as unknown as Row[];
  const passed = rows.filter((r) => r.stage === PASSED);

  return (
    <Shell user={user} active="/pipeline">
      <h1>Pipeline</h1>
      <p className="lede">Every business you're working on, and the stage it's at.</p>
      <nav className="stagestrip" aria-label="Stages">
        {STAGES.map((stage) => {
          const count = rows.filter((r) => r.stage === stage).length;
          return <a key={stage} href={`#${anchor(stage)}`} className={count ? "chip on" : "chip"}>{stage} {count}</a>;
        })}
      </nav>
      {STAGES.map((stage) => {
        const here = rows.filter((r) => r.stage === stage);
        return here.length ? (
          <section key={stage} id={anchor(stage)} className="stagesec">
            <h2>{stage} <span className="lsub">({here.length})</span></h2>
            <div className="dcards">{here.map((row) => <DealCard key={row.business_id} row={row} />)}</div>
          </section>
        ) : null;
      })}
      {rows.length === passed.length ? <p className="note">Nothing in the pipeline yet. Open a business in Find and give it a stage.</p> : null}
      <details className="more stagesec">
        <summary>Add a business that isn't listed</summary>
        <form action={addBusiness} className="fieldgrid">
          <label className="field">Business name<input className="input" name="name" required /></label>
          <label className="field">Location<input className="input" name="location" /></label>
          <label className="field">Link (optional)<input className="input" name="url" type="url" /></label>
          <label className="field">Stage<select name="stage" defaultValue="Approached">{STAGES.map((s) => <option key={s}>{s}</option>)}</select></label>
          <button type="submit" className="btn primary">Add</button>
        </form>
      </details>
      {passed.length ? (
        <details className="more stagesec">
          <summary>Passed ({passed.length})</summary>
          {passed.map((row) => <Link key={row.business_id} className="item" href={link(row.business_id)}><span className="ltitle">{row.businesses.name}</span></Link>)}
        </details>
      ) : null}
    </Shell>
  );
}
