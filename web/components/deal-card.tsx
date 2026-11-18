import Link from "next/link";
import { saveDealCard } from "@/lib/actions";
import { Business, dealCard, db, link, PASSED, STAGES, Tracking, when } from "@/lib/db";
import { SHEETS } from "@/lib/worksheets";

const plain = (value: number | null) => (value ? String(Math.round(value)) : "");

/** The facts every pipeline card shows, the stage, and the business's three worksheets. */
export async function DealCardForm({ business, tracking }: { business: Business; tracking: Tracking | null }) {
  const card = dealCard(business, tracking);
  const { data: sheets } = await db().from("worksheets").select("kind, updated_at").eq("business_id", business.id);
  const saved = Object.fromEntries((sheets ?? []).map((s) => [s.kind, s.updated_at]));

  return (
    <>
      <section className="card"><h2>{tracking ? "Deal card" : "Add to pipeline"}</h2>
        <form action={saveDealCard} className="fieldgrid">
          <input type="hidden" name="id" value={business.id} />
          <label className="field">Stage
            <select name="stage" defaultValue={tracking?.stage ?? "Shortlist"}>{[...STAGES, PASSED].map((s) => <option key={s}>{s}</option>)}</select>
          </label>
          <label className="field">Location<input className="input" name="location" defaultValue={card.location} /></label>
          <label className="field">Product / service<input className="input" name="product" defaultValue={card.product} /></label>
          <label className="field">Asking price<input className="input" name="asking_price" inputMode="decimal" defaultValue={plain(card.asking)} /></label>
          <label className="field">Annual turnover<input className="input" name="turnover" inputMode="decimal" defaultValue={plain(card.turnover)} /></label>
          <label className="field">Annual expenses<input className="input" name="expenses" inputMode="decimal" defaultValue={plain(card.expenses)} /></label>
          <label className="field">EBITDA / profit<input className="input" name="profit" inputMode="decimal" defaultValue={plain(card.profit)} /></label>
          <label className="field">Under management
            <select name="under_management" defaultValue={card.underManagement}>
              <option value="">Not known</option><option>Yes</option><option>Partly</option><option>No</option>
            </select>
          </label>
          <label className="field">Approached on<input className="input" type="date" name="approached_on" defaultValue={tracking?.approached_on ?? ""} /></label>
          <label className="field">Last follow-up<input className="input" type="date" name="followed_up_on" defaultValue={tracking?.followed_up_on ?? ""} /></label>
          <label className="field wide">Reason for selling<textarea className="input" name="selling_reason" rows={2} defaultValue={card.sellingReason} /></label>
          <button type="submit" className="btn primary">{tracking ? "Save" : "Add to pipeline"}</button>
        </form>
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
