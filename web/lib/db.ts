import { createClient } from "@supabase/supabase-js";

export const STAGES = ["New", "Researching", "Approaching", "Talking", "NDA and numbers", "Offer"];
export const LAST_STAGE = "Offer";

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

export type Tracking = { business_id: string; stage: string; next_step: string | null; next_due: string | null; owner: string | null };

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
