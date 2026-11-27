import { saveDealCard } from "@/lib/actions";
import { Business, Card, dealCard, money, nameOf, Tracking } from "@/lib/db";

const plain = (value: number | null) => (value ? String(Math.round(value)) : "");

/** The rows Tom wants on every business, known or not, in his order. */
export const OVERVIEW_ROWS = [
  { key: "location", label: "Location" },
  { key: "product", label: "Product / service" },
  { key: "selling_reason", label: "Selling reason" },
  { key: "turnover", label: "Annual turnover" },
  { key: "expenses", label: "Annual expenses" },
  { key: "profit", label: "EBITDA / profit" },
  { key: "asking_price", label: "Asking price" },
  { key: "under_management", label: "Under management" },
] as const;

/** What each row shows: the typed value, or else what the listing said, or nothing yet. */
export function overviewValues(card: Card, amount: (value: number) => string = money): Record<(typeof OVERVIEW_ROWS)[number]["key"], string> {
  const shown = (value: number | null) => (value ? amount(value) : "");
  return {
    location: card.location, product: card.product, selling_reason: card.sellingReason,
    turnover: shown(card.turnover), expenses: shown(card.expenses), profit: shown(card.profit), asking_price: shown(card.asking),
    under_management: card.underManagement,
  };
}

/** The form's inputs: one row each, always there, filled with what's known. */
export function OverviewInputs({ business, tracking, withName = true }: { business: Business; tracking: Tracking | null; withName?: boolean }) {
  const card = dealCard(business, tracking);
  return (
    <div className="orows">
      {withName ? <label className="orow"><span>Name</span><input className="input" name="display_name" defaultValue={nameOf(business, tracking)} /></label> : null}
      <label className="orow"><span>Location</span><input className="input" name="location" defaultValue={card.location} placeholder="Not known yet" /></label>
      <label className="orow"><span>Product / service</span><input className="input" name="product" defaultValue={card.product} placeholder="Not known yet" /></label>
      <label className="orow"><span>Selling reason</span><textarea className="input" name="selling_reason" rows={2} defaultValue={card.sellingReason} placeholder="Not known yet" /></label>
      <label className="orow"><span>Annual turnover</span><input className="input" name="turnover" inputMode="decimal" defaultValue={plain(card.turnover)} placeholder="Not known yet" /></label>
      <label className="orow"><span>Annual expenses</span><input className="input" name="expenses" inputMode="decimal" defaultValue={plain(card.expenses)} placeholder="Not known yet" /></label>
      <label className="orow"><span>EBITDA / profit</span><input className="input" name="profit" inputMode="decimal" defaultValue={plain(card.profit)} placeholder="Not known yet" /></label>
      <label className="orow"><span>Asking price</span><input className="input" name="asking_price" inputMode="decimal" defaultValue={plain(card.asking)} placeholder="Not known yet" /></label>
      <label className="orow"><span>Under management</span>
        <select name="under_management" defaultValue={card.underManagement}>
          <option value="">Not known yet</option><option>Yes</option><option>Partly</option><option>No</option>
        </select>
      </label>
    </div>
  );
}

/** The business's overview on its page: every row, always, ready to fill in or change. */
export function OverviewCard({ business, tracking }: { business: Business; tracking: Tracking }) {
  return (
    <section className="card"><h2>Overview</h2>
      <p className="lsub">Fill in or change anything as you learn it. Amounts can be typed like 250000, 250k or 1.2m.</p>
      <form action={saveDealCard} className="stack">
        <input type="hidden" name="id" value={business.id} />
        <OverviewInputs business={business} tracking={tracking} />
        <button type="submit" className="btn primary">Save</button>
      </form>
    </section>
  );
}
