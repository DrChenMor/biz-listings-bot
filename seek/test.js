// Tests for SaveToSheet.gs, run with: node --test seek/
const test = require("node:test");
const assert = require("node:assert/strict");
const script = require("./SaveToSheet.gs");

const header = script.COLUMNS.map((c) => c[1]);
const col = (field) => script.COLUMNS.findIndex((c) => c[0] === field);

function listing(over = {}) {
  return {
    id: "794248",
    url: "https://www.seekbusiness.com.au/business-listing/mount-pleasant-stunning-hair-salon-for-sale/794248",
    title: "Mount Pleasant Stunning Hair Salon for Sale",
    advertiser: "Benchmark Business Sales and Valuations",
    location: "Perth - Greater, Mount Pleasant, WA 6153",
    industry: "Health, Beauty & Fitness > Hair, Beauty & Spa",
    price_text: "$87,000 + SAV",
    price_min: 87000,
    opportunity_type: "Business",
    summary: "Established 23+ years, this turnkey boutique salon delivers $13K weekly sales and ~$160K net profit, with 11 stations.",
    ...over,
  };
}

test("a new listing is added once, with price, turnover and profit read from its text", () => {
  const plan = script.planChanges([header], [listing(), listing()], "2026-10-23 15:00");
  assert.equal(plan.appends.length, 1);
  const row = plan.appends[0];
  assert.equal(row[col("key")], "seek:794248");
  assert.equal(row[col("price_aud")], 87000);
  assert.equal(row[col("price_basis")], "+ stock (SAV)");
  assert.equal(row[col("turnover_aud")], 13000 * 52);
  assert.equal(row[col("profit_aud")], 160000);
  assert.equal(row[col("first_seen")], "2026-10-23 15:00");
  assert.deepEqual(plan.changes[0].slice(4), ["New listing", "", "$87,000 + SAV", listing().url]);
  assert.deepEqual(plan.counts, { saved: 1, added: 1, updated: 0, unchanged: 0, skipped: 0 });
});

test("seeing it again updates the row and logs a price drop and under offer", () => {
  const first = script.planChanges([header], [listing()], "2026-10-23 15:00");
  const values = [header, first.appends[0]];
  const plan = script.planChanges(values, [listing({ title: "UNDER OFFER - Mount Pleasant Hair Salon", price_text: "$79,000 + SAV" })], "2026-10-24 09:00");
  assert.equal(plan.updates.length, 1);
  assert.equal(plan.updates[0].row, 2);
  const changed = plan.changes.map((c) => [c[4], c[5], c[6]]);
  assert.deepEqual(changed, [
    ["Status", "Active", "Under offer"],
    ["Title", "Mount Pleasant Stunning Hair Salon for Sale", "UNDER OFFER - Mount Pleasant Hair Salon"],
    ["Asking price", "$87,000 + SAV", "$79,000 + SAV"],
  ]);
  const row = plan.updates[0].values;
  assert.equal(row[col("first_seen")], "2026-10-23 15:00");
  assert.equal(row[col("last_changed")], "2026-10-24 09:00");
});

test("a results-page capture doesn't wipe the description saved from the listing page", () => {
  const first = script.planChanges([header], [listing({ description: "Contact John on 0422 930 549 or 1300 366 521" })], "t1");
  assert.equal(first.appends[0][col("phones")], "0422 930 549; 1300 366 521");
  const plan = script.planChanges([header, first.appends[0]], [listing()], "t2");
  assert.match(plan.updates[0].values[col("description")], /0422 930 549/);
  assert.equal(plan.counts.unchanged, 1);
});

test("food businesses are skipped", () => {
  const plan = script.planChanges([header], [listing({ id: "1", industry: "Food & Drink > Coffee, Cafes & Restaurants > Cafe" }), listing({ id: "2", industry: "Retail > Convenience, Grocery & Liquor stores" })], "t");
  assert.equal(plan.appends.length, 0);
  assert.equal(plan.counts.skipped, 2);
  const kept = script.planChanges([header], [listing({ industry: "Health, Beauty & Fitness > Hair, Beauty & Spa > Barber" })], "t");
  assert.equal(kept.appends.length, 1);
});

test("price from SEEK's numbers when the page text has none", () => {
  assert.equal(script.priceFromParts({ price_min: 300000, price_max: 450000 }), "$300,000 - $450,000");
  assert.equal(script.priceFromParts({ poa: true }), "P.O.A");
  assert.equal(script.priceFromParts({ price_min: 87000, price_max: 87000, sav: true }), "$87,000 + SAV");
});

test("turnover and profit wording", () => {
  assert.equal(script.turnover("Turnover: $2026 – $329,300; 2025 – $317,900"), 329300);
  assert.equal(script.turnover("Averaging $51,415 a week, open 6 days"), 51415 * 52);
  assert.equal(script.turnover("All sales are cash, so there are no debtors, and $250,000 in orders"), "");
  assert.equal(script.profit("EBITDA of $210,000 last year"), 210000);
  assert.equal(script.profit("A profitable cafe asking $120,000"), "");
});
