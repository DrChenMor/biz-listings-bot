import { createClient } from "@supabase/supabase-js";

/** The deal flow, in order. Passed sits outside it. */
export const STAGES = ["Shortlist", "Approached", "NDA signed", "Documents in", "First meet", "Deal analysis", "Pitch / offer",
  "Term sheet", "Due diligence", "Deal re-work", "Deal closed", "Completion"];
export const PASSED = "Passed";

/** Where Move on takes a business. Due diligence that goes well closes the deal; a re-worked deal is pitched again. */
export const NEXT_STAGE: Record<string, string> = Object.fromEntries(STAGES.slice(0, -1).map((stage, i) => [stage, STAGES[i + 1]]));
NEXT_STAGE["Due diligence"] = "Deal closed";
NEXT_STAGE["Deal re-work"] = "Pitch / offer";

/** Businesses added straight into the pipeline, not found by a bot. */
export const BY_HAND = "Added by hand";

/** Server only: this key can read everything, so it never reaches the browser. */
export function db() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL and SUPABASE_SERVICE_KEY are not set");
  return createClient(url, key, { auth: { persistSession: false } });
}

export type Fact = { label: string; value: string; source: string; date: string };

export type Business = {
  id: string; kind: "sale" | "practice"; site: string; status: string | null; name: string; summary: string | null;
  types: string[]; category: string | null; suburb: string | null; postcode: string | null; region: string | null; perth: boolean;
  price_text: string | null; price: number | null; turnover: number | null; profit: number | null; route: string; tags: string[];
  seller: string | null; phone: string | null; email: string | null; website: string | null; address: string | null;
  url: string | null; map_url: string | null; description: string | null; facts: Fact[]; first_seen: string | null; on_sheet: boolean;
};

export type Tracking = {
  business_id: string; stage: string; next_step: string | null; next_due: string | null; owner: string | null;
  location: string | null; product: string | null; selling_reason: string | null; asking_price: number | null; turnover: number | null;
  expenses: number | null; profit: number | null; under_management: string | null; approached_on: string | null; followed_up_on: string | null;
};

export type Card = {
  location: string; product: string; sellingReason: string; asking: number | null; turnover: number | null;
  expenses: number | null; profit: number | null; underManagement: string;
};

/** What a pipeline card shows: what was typed in, or else what the listing said. */
export function dealCard(b: Business, t: Tracking | null): Card {
  return {
    location: t?.location || b.suburb || "",
    product: t?.product || b.category || b.types[0] || "",
    sellingReason: t?.selling_reason || b.facts.find((f) => f.label === "Reason for sale")?.value || "",
    asking: t?.asking_price ?? b.price,
    turnover: t?.turnover ?? b.turnover,
    expenses: t?.expenses ?? null,
    profit: t?.profit ?? b.profit,
    underManagement: t?.under_management || "",
  };
}

/** Today's date in Perth, as the database stores dates. */
export function today(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Australia/Perth" });
}

export const AGENT_SITES = ["bsale", "business2sell", "AnyBusiness", "businessforsale.com.au", "No Agent Business"];

export type Enquiry = {
  id: number; business_id: string; status: string; detail: string | null; asked_by: string | null; message: string | null;
  requested_at: string; sent_at: string | null; updated_at: string;
};

export type Evaluation = {
  verdict: string; headline: string; asking_price: string; years: { year: string; turnover: string; profit: string }[];
  adjusted_profit: string; price_to_profit: string; lease: string; staff: string; owner_involvement: string;
  strengths: string[]; risks: string[]; missing: string[]; questions: string[];
};

export function statusClass(status: string): string {
  if (status === "Needs you" || status === "Stopped") return "pill r-stop";
  if (status === "Evaluated") return "pill r-call";
  if (["Queued", "Sending", "Test only", "Closed"].includes(status)) return "pill r-broker";
  return "pill r-email";
}

export function routeClass(route: string): string {
  if (route === "Private seller") return "pill r-private";
  if (route === "Call owner") return "pill r-call";
  if (route === "Email owner") return "pill r-email";
  if (route === "Needs a pharmacist" || route === "Excluded") return "pill r-stop";
  return "pill r-broker";
}

export function when(moment: string | null): string {
  if (!moment) return "";
  return new Date(moment).toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric", timeZone: "Australia/Perth" });
}

export function money(value: number | null): string {
  return value ? `$${Number(value).toLocaleString("en-AU", { maximumFractionDigits: 0 })}` : "";
}

export function link(id: string): string {
  return `/b/${encodeURIComponent(id)}`;
}
