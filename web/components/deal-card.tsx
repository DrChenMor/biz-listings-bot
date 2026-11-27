import Link from "next/link";
import { saveDealCard } from "@/lib/actions";
import { Business, db, link, PASSED, STAGES, Tracking, when } from "@/lib/db";
import { SHEETS } from "@/lib/worksheets";
import { OverviewInputs } from "./overview";

/**
 * In the pipeline: the stage and the dates (the overview has its own box). Not yet in the pipeline: the overview and a
 * stage, to add it. Then the business's three worksheets.
 */
export async function DealCardForm({ business, tracking }: { business: Business; tracking: Tracking | null }) {
  const { data: sheets } = await db().from("worksheets").select("kind, updated_at").eq("business_id", business.id);
  const saved = Object.fromEntries((sheets ?? []).map((s) => [s.kind, s.updated_at]));

  return (
    <>
      <section className="card"><h2>{tracking ? "Stage and dates" : "Add to pipeline"}</h2>
        <form action={saveDealCard} className="fieldgrid">
          <input type="hidden" name="id" value={business.id} />
          <label className="field">Stage
            <select name="stage" defaultValue={tracking?.stage ?? "Shortlist"}>{[...STAGES, PASSED].map((s) => <option key={s}>{s}</option>)}</select>
          </label>
          <label className="field">Approached on<input className="input" type="date" name="approached_on" defaultValue={tracking?.approached_on ?? ""} /></label>
          <label className="field">Last follow-up<input className="input" type="date" name="followed_up_on" defaultValue={tracking?.followed_up_on ?? ""} /></label>
          {tracking ? null : <div className="field wide"><OverviewInputs business={business} tracking={tracking} /></div>}
          <button type="submit" className="btn primary">{tracking ? "Save" : "Add to pipeline"}</button>
        </form>
        {tracking ? <p className="lsub">Tom&apos;s emails to the contacts update these dates by themselves each morning.</p> : null}
      </section>
      <section className="card"><h2>Worksheets</h2>
        {Object.values(SHEETS).map((sheet) => (
          <Link className="item" key={sheet.kind} href={`${link(business.id)}/sheet/${sheet.kind}`}>
            <span className="ltitle">{sheet.title}</span>
            <span className="lsub">{saved[sheet.kind] ? `Saved ${when(saved[sheet.kind])}` : `Not started · ${sheet.when}`}</span>
          </Link>
        ))}
      </section>
    </>
  );
}
