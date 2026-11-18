/** The three Deal Mastery worksheets, filled in online for each business. Answers are stored as flat text keys. */
import type { Business, Card } from "./db";

export type Field =
  | { key: string; label: string; type: "text" | "long" | "money" }
  | { key: string; label: string; type: "choice"; options: string[] }
  | { key: string; label: string; type: "row"; money: boolean }
  | { key: string; label: string; type: "plan"; rows: number };

export type Section = { title: string; fields: Field[]; heads?: string[] };
export type Sheet = { kind: Kind; title: string; when: string; sections: Section[] };
export type Kind = "review" | "analysis" | "bundle";

const text = (key: string, label: string): Field => ({ key, label, type: "text" });
const long = (key: string, label: string): Field => ({ key, label, type: "long" });
const cash = (key: string, label: string): Field => ({ key, label, type: "money" });
const row = (key: string, label: string, money = true): Field => ({ key, label, type: "row", money });
const ROW_HEADS = ["", "Y/N", "Value", "Notes"];
const PLAN_HEADS = ["Strategy", "Used Y/N", "Cash impact", "Notes"];

export const SHEETS: Record<Kind, Sheet> = {
  review: {
    kind: "review", title: "Deal Review", when: "Before and after the first meeting",
    sections: [
      { title: "Business", fields: [text("business", "Business name")] },
      { title: "Pre meet", fields: [long("product", "Product / service overview"), text("industry", "Industry info"), text("timing", "Timing"),
        text("multiple", "Multiple"), text("connections", "Connections in industry"), long("impact", "Impact to Empire")] },
      { title: "First meet criticals", fields: [long("motivation", "Motivation to sell"), long("personal_story", "Their personal story"),
        long("business_story", "The business story"), text("years", "Years in business"),
        { key: "owner_is", label: "Owner is a", type: "choice", options: ["1", "2", "3"] }, text("team", "Number of team"),
        { key: "going_concern", label: "Going concern", type: "choice", options: ["Y", "N"] }, long("great", "What's great about the business"),
        long("challenging", "What's challenging about the business"), cash("monthly_turnover", "Avg monthly turnover"),
        cash("monthly_expenses", "Avg monthly expenses"), text("time_frame", "Time frames to sell"), long("leverage", "Any other leverage points")] },
      { title: "Deal notes", fields: [long("notes", "Deal notes")] },
    ],
  },
  analysis: {
    kind: "analysis", title: "Deal Analysis", when: "Once the documents are in",
    sections: [
      { title: "Target business", fields: [text("business", "Target business")] },
      { title: "Business overview", heads: ROW_HEADS, fields: [row("cash", "Cash on hand"), row("ar_in", "A/R (what's coming in)"),
        row("invested", "Invested money (term/crypto)"), row("security", "Security (stocks/bonds)"), row("stock", "Stock (parts of products)"),
        row("inventory", "Inventory (ready to sell)"), row("fixtures", "Fixtures & fittings"), row("equipment", "Equipment"),
        row("vehicles", "Vehicles"), row("real_estate", "Real estate")] },
      { title: "Deal overview", heads: ROW_HEADS, fields: [row("ask", "Ask price/value"), row("ebitda", "EBITDA/profit"),
        row("ask_multiple", "Ask multiple"), row("turnover_annual", "Turnover annual"), row("turnover_monthly", "Turnover monthly avg"),
        row("recurring", "Recurring monthly avg (if any)"), row("customers", "Customer database total (buyers)"), row("pipeline", "Customer pipeline"),
        row("prospects", "Prospect database total (non-buyers)"), row("ar_out", "A/R (outstanding to pay)"), row("ip", "IP owned"),
        row("social", "Social media presence/following", false), row("capacity", "Capacity – more output potential", false),
        row("management", "Under management", false), row("reasons", "Reasons for selling", false)] },
      { title: "Deal notes", fields: [long("notes", "Deal notes"), { key: "next_step", label: "Take to next step", type: "choice", options: ["No", "Yes"] }] },
    ],
  },
  bundle: {
    kind: "bundle", title: "Deal Bundle", when: "Planning the offer",
    sections: [
      { title: "Target business", fields: [text("business", "Target business"), cash("ask", "Ask price"), cash("ebitda", "EBITDA"),
        cash("goal", "Goal purchase price")] },
      { title: "Pre-closing strategy", heads: PLAN_HEADS, fields: [{ key: "pre", label: "Pre-closing strategy", type: "plan", rows: 12 }] },
      { title: "Gap funding strategy", heads: PLAN_HEADS, fields: [{ key: "gap", label: "Gap funding strategy", type: "plan", rows: 4 }] },
      { title: "Post closing strategy", heads: PLAN_HEADS, fields: [{ key: "post", label: "Post closing strategy", type: "plan", rows: 5 }] },
      { title: "Deal notes", fields: [long("notes", "Deal notes")] },
      { title: "Empire impact", fields: [cash("net_value", "Net value added"), cash("annual_cash", "Annual positive cash added"),
        { key: "funded", label: "Fully funded", type: "choice", options: ["Y", "N"] }] },
    ],
  },
};

export function isKind(kind: string): kind is Kind {
  return kind in SHEETS;
}

const plain = (value: number | null) => (value ? String(Math.round(value)) : "");

/** A new worksheet starts with what's already known about the business. */
export function prefill(kind: Kind, b: Business, card: Card): Record<string, string> {
  const monthly = card.turnover ? card.turnover / 12 : null;
  if (kind === "review") {
    return { business: b.name, product: card.product, motivation: card.sellingReason, monthly_turnover: plain(monthly),
      monthly_expenses: plain(card.expenses ? card.expenses / 12 : null) };
  }
  if (kind === "analysis") {
    return { business: b.name, "ask.value": plain(card.asking), "ebitda.value": plain(card.profit), "turnover_annual.value": plain(card.turnover),
      "turnover_monthly.value": plain(monthly), "reasons.notes": card.sellingReason, "management.notes": card.underManagement };
  }
  return { business: b.name, ask: plain(card.asking), ebitda: plain(card.profit) };
}

export function number(value: string | undefined): number {
  const n = Number(String(value ?? "").replace(/[$,\s]/g, ""));
  return Number.isFinite(n) ? n : 0;
}

const escape = (text: string) => text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string);
const money = (text: string | undefined) => (text ? `$${number(text).toLocaleString("en-AU")}` : "");

/** A filled-in worksheet as a simple HTML page, which Google Drive turns into a Doc. */
export function worksheetHtml(kind: Kind, business: string, data: Record<string, string>): string {
  const value = (key: string) => escape(data[key] ?? "");
  const cell = (text: string, head = false) => `<${head ? "th" : "td"} style="border:1px solid #999;padding:4px 6px;text-align:left">${text}</${head ? "th" : "td"}>`;
  const table = (heads: string[], rows: string[][]) => `<table style="border-collapse:collapse;width:100%">
    <tr>${heads.map((h) => cell(h, true)).join("")}</tr>${rows.map((r) => `<tr>${r.map((c) => cell(c)).join("")}</tr>`).join("")}</table>`;
  const parts = [`<h1>${escape(SHEETS[kind].title)}: ${escape(business)}</h1>`];
  for (const section of SHEETS[kind].sections) {
    parts.push(`<h2>${escape(section.title)}</h2>`);
    const rows = section.fields.filter((f) => f.type === "row");
    if (rows.length) parts.push(table(["", "Y/N", "Value", "Notes"], rows.map((f) => [escape(f.label), value(`${f.key}.yn`), f.type === "row" && f.money ? escape(money(data[`${f.key}.value`])) : "", value(`${f.key}.notes`)])));
    for (const field of section.fields) {
      if (field.type === "plan") {
        const used = Array.from({ length: field.rows }, (_, i) => `${field.key}.${i}`).filter((k) => data[`${k}.name`] || data[`${k}.cash`]);
        parts.push(table(["Strategy", "Used Y/N", "Cash impact", "Notes"], [...used.map((k) => [value(`${k}.name`), value(`${k}.used`), escape(money(data[`${k}.cash`])), value(`${k}.notes`)]),
          ["<b>Total</b>", "", `<b>$${planTotal(data, field.key, field.rows).toLocaleString("en-AU")}</b>`, ""]]));
      } else if (field.type !== "row") {
        const shown = field.type === "money" ? escape(money(data[field.key])) : value(field.key).replace(/\n/g, "<br>");
        parts.push(`<p><b>${escape(field.label)}:</b> ${shown}</p>`);
      }
    }
  }
  return `<html><head><meta charset="utf-8"></head><body>${parts.join("\n")}</body></html>`;
}

/** The total of a strategy table, counting every row not marked N. */
export function planTotal(data: Record<string, string>, key: string, rows: number): number {
  let total = 0;
  for (let i = 0; i < rows; i++) {
    if ((data[`${key}.${i}.used`] ?? "").toUpperCase() !== "N") total += number(data[`${key}.${i}.cash`]);
  }
  return total;
}
