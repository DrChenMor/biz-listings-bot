/**
 * "What we look for": filters saved from Find. A listing that fits one gets a star in Find, and new ones that fit go
 * into Tom's morning email. The test mirrors Find's own filters, so a rule shows what Find showed when it was saved.
 */
export type WatchRule = { id: number; name: string; filters: Record<string, string> };

export type Watchable = {
  kind: string; status: string | null; perth: boolean; route: string; types: string[]; site: string; suburb: string | null;
  price: number | null; turnover: number | null; profit: number | null; phone: string | null; search_text: string | null;
  display_name?: string | null;
};

/** The Find filters a rule keeps: everything except paging, sorting and the view-only switches. */
export const RULE_KEYS = ["show", "area", "route", "type", "site", "suburb", "q", "min", "max", "turnover", "profit", "priced", "earning", "phone", "active"];

export function ruleFilters(search: Record<string, string | undefined>): Record<string, string> {
  return Object.fromEntries(RULE_KEYS.filter((k) => search[k]).map((k) => [k, String(search[k])]));
}

const list = (value?: string) => (value ? value.split("|").filter(Boolean) : []);

export function fits(b: Watchable, f: Record<string, string>): boolean {
  if (b.status === "Removed") return false;
  const show = f.show ?? "sale";
  if (show !== "all" && b.kind !== show) return false;
  if ((f.area ?? "perth") === "perth" && !b.perth) return false;
  const routes = list(f.route), types = list(f.type);
  if (routes.length && !routes.includes(b.route)) return false;
  if (types.length && !types.some((t) => b.types.includes(t))) return false;
  if (f.site && b.site !== f.site) return false;
  if (f.suburb && !(b.suburb ?? "").toLowerCase().includes(f.suburb.toLowerCase())) return false;
  if (f.q) {
    const term = f.q.toLowerCase();
    if (!(b.search_text ?? "").includes(term) && !(b.display_name ?? "").toLowerCase().includes(term)) return false;
  }
  if (f.min && !((b.price ?? 0) >= Number(f.min))) return false;
  if (f.max && !(b.price && b.price <= Number(f.max))) return false;
  if (f.turnover && !((b.turnover ?? 0) >= Number(f.turnover))) return false;
  if (f.profit && !((b.profit ?? 0) >= Number(f.profit))) return false;
  if (f.priced && !b.price) return false;
  if (f.earning && !b.profit) return false;
  if (f.phone && !b.phone) return false;
  if (f.active && b.status === "Under offer") return false;
  return true;
}

/** The names of the rules a listing fits. */
export function rulesFitting(b: Watchable, rules: WatchRule[]): string[] {
  return rules.filter((r) => fits(b, r.filters)).map((r) => r.name);
}

/** Words for a rule's filters, for the list of rules: "Health and medical · Perth · up to $500k". */
export function describe(f: Record<string, string>): string {
  const money = (v: string) => (Number(v) >= 1e6 ? `$${Number(v) / 1e6}M` : `$${Number(v) / 1e3}k`);
  return [
    ...list(f.type), ...list(f.route), f.area === "all" ? "anywhere" : "Perth", f.site, f.suburb && `in ${f.suburb}`, f.q && `"${f.q}"`,
    f.min && `from ${money(f.min)}`, f.max && `up to ${money(f.max)}`, f.turnover && `turnover ${money(f.turnover)}+`,
    f.profit && `profit ${money(f.profit)}+`, f.priced && "has a price", f.earning && "shows profit", f.phone && "has a phone",
    f.active && "not under offer", f.show === "practice" ? "health practices" : f.show === "all" ? "everything" : null,
  ].filter(Boolean).join(" · ");
}
