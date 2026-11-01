import Link from "next/link";
import { Filters } from "@/components/filters";
import { Shell } from "@/components/shell";
import { requireUser } from "@/lib/auth";
import { Business, db, link, routeClass, when } from "@/lib/db";

export const dynamic = "force-dynamic";

const PAGE = 50;
const ROUTES = ["Private seller", "Via broker", "Franchisor", "Site enquiry", "Not scored yet", "Needs a pharmacist"];
const SALE_TYPES = ["Health and medical", "Beauty and hair", "Fitness and sport", "Childcare and education", "Cleaning and home services",
  "Trades and construction", "Automotive and transport", "Retail and shops", "Professional and finance", "Manufacturing and wholesale",
  "Pets and animals", "Accommodation and tourism", "Online and work from home", "Farming and rural", "Other services", "Franchises"];
const SECTORS = ["GP / medical centre", "Dental", "Pharmacy", "Allied health", "Mental health", "Medical specialist", "Optical & hearing",
  "Pathology & imaging", "Hospital / day surgery", "Complementary", "Community / support", "Other"];
const PRICES = [100000, 200000, 300000, 500000, 750000, 1000000, 2000000];

type Search = { q?: string; show?: string; route?: string; type?: string; area?: string; max?: string; sort?: string; page?: string };

export default async function Find({ searchParams }: { searchParams: Promise<Search> }) {
  const user = await requireUser();
  const s = await searchParams;
  const page = Math.max(1, Number(s.page) || 1);
  const area = s.area ?? "perth";
  const term = (s.q ?? "").trim().toLowerCase().replace(/[%_,()]/g, " ");
  // A type belongs to one list. Otherwise the page opens on businesses for sale, or everything for a chosen route.
  const show = SECTORS.includes(s.type ?? "") ? "practice" : SALE_TYPES.includes(s.type ?? "") ? "sale" : s.show ?? (s.route ? "all" : "sale");

  let query = db().from("businesses").select("id, kind, site, status, name, types, suburb, price_text, route, tags, first_seen", { count: "exact" })
    .eq("on_sheet", true).neq("status", "Removed");
  if (show !== "all") query = query.eq("kind", show);
  if (s.route) query = query.eq("route", s.route);
  if (s.type) query = query.contains("types", [s.type]);
  if (area === "perth") query = query.eq("perth", true);
  if (s.max) query = query.lte("price", Number(s.max)).gt("price", 0);
  if (term) query = query.ilike("search_text", `%${term}%`);
  if (s.sort === "cheapest") query = query.order("price", { ascending: true, nullsFirst: false });
  else if (s.sort === "profit") query = query.order("profit", { ascending: false, nullsFirst: false });
  else if (s.sort === "suburb") query = query.order("suburb", { ascending: true, nullsFirst: false });
  else query = query.order("first_seen", { ascending: false, nullsFirst: false });
  const { data, count, error } = await query.order("id").range((page - 1) * PAGE, page * PAGE - 1);
  if (error) throw new Error(error.message);
  const rows = (data ?? []) as unknown as Business[];
  const total = count ?? 0;

  const pageLink = (number: number) => {
    const params = new URLSearchParams(Object.entries(s).filter(([, v]) => v) as [string, string][]);
    params.set("page", String(number));
    return `/find?${params}`;
  };

  return (
    <Shell user={user} active="/find">
      <h1>Find</h1>
      <p className="lede">Every business in one list. The route tells you how to reach them.</p>
      <Filters>
        <label className="field grow">Search name, suburb or seller
          <input className="input" type="search" name="q" defaultValue={s.q ?? ""} />
        </label>
        <label className="field">Show
          <select name="show" defaultValue={show}><option value="sale">For sale</option><option value="practice">Not listed: health</option><option value="all">Everything</option></select>
        </label>
        <label className="field">Route
          <select name="route" defaultValue={s.route ?? ""}><option value="">All routes</option>{ROUTES.map((r) => <option key={r}>{r}</option>)}</select>
        </label>
        <label className="field">Type
          <select name="type" defaultValue={s.type ?? ""}><option value="">All types</option>
            <optgroup label="For sale">{SALE_TYPES.map((t) => <option key={t}>{t}</option>)}</optgroup>
            <optgroup label="Health practices">{SECTORS.map((t) => <option key={t}>{t}</option>)}</optgroup>
          </select>
        </label>
        <label className="field">Where
          <select name="area" defaultValue={area}><option value="perth">Perth only</option><option value="all">All of WA</option></select>
        </label>
        <label className="field">Most you'd pay
          <select name="max" defaultValue={s.max ?? ""}><option value="">Any price</option>{PRICES.map((p) => <option key={p} value={p}>Up to ${p.toLocaleString()}</option>)}</select>
        </label>
        <label className="field">Sort
          <select name="sort" defaultValue={s.sort ?? ""}><option value="">Newest first</option><option value="cheapest">Cheapest first</option><option value="profit">Highest profit</option><option value="suburb">By suburb</option></select>
        </label>
        <button type="submit" className="btn">Search</button>
      </Filters>
      <p className="lede"><b>{total.toLocaleString()}</b> found</p>
      <div className="head"><span className="c1">Business</span><span className="c2">Route</span><span className="c3">Why</span><span className="c4">Price</span><span className="c5">Added</span></div>
      <div className="list">
        {rows.map((b) => (
          <Link className="row" key={b.id} href={link(b.id)}>
            <span className="c1"><span className="ltitle">{b.name}</span><span className="lsub">{[b.types[0], b.suburb].filter(Boolean).join(" · ")}</span></span>
            <span className="c2"><span className={routeClass(b.route)}>{b.route}</span></span>
            <span className="c3">{b.tags.map((t) => <span className="tag" key={t}>{t}</span>)}</span>
            <span className="c4 fig">{b.price_text}</span>
            <span className="c5 lsub">{when(b.first_seen)}</span>
          </Link>
        ))}
      </div>
      {rows.length === 0 ? <p className="note">Nothing matches. Try fewer filters.</p> : null}
      <div className="pages">
        {page > 1 ? <Link className="btn" href={pageLink(page - 1)}>Previous</Link> : null}
        <span>Page {page} of {Math.max(1, Math.ceil(total / PAGE))}</span>
        {page * PAGE < total ? <Link className="btn" href={pageLink(page + 1)}>Next</Link> : null}
      </div>
    </Shell>
  );
}
