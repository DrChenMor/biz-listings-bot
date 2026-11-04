import Link from "next/link";
import { Filters } from "@/components/filters";
import { Shell } from "@/components/shell";
import { requireUser } from "@/lib/auth";
import { Business, db, link, routeClass, when } from "@/lib/db";

export const dynamic = "force-dynamic";

const PAGE = 50;
const SALE_TYPES = ["Health and medical", "Beauty and hair", "Fitness and sport", "Childcare and education", "Cleaning and home services",
  "Trades and construction", "Automotive and transport", "Retail and shops", "Professional and finance", "Manufacturing and wholesale",
  "Pets and animals", "Accommodation and tourism", "Online and work from home", "Farming and rural", "Other services", "Franchises"];
const SECTORS = ["GP / medical centre", "Dental", "Pharmacy", "Allied health", "Mental health", "Medical specialist", "Optical & hearing",
  "Pathology & imaging", "Hospital / day surgery", "Complementary", "Community / support", "Other"];
const SALE_ROUTES = ["Private seller", "Via broker", "Franchisor", "Site enquiry"];
const SITES = ["bsale", "business2sell", "AnyBusiness", "businessforsale.com.au", "No Agent Business", "commercialrealestate.com.au", "SEEK Business"];
const PRICES = [50000, 100000, 200000, 300000, 500000, 750000, 1000000, 2000000];
const FIGURES = [50000, 100000, 250000, 500000, 1000000];
const FLAGS: [string, string][] = [["fresh", "New this week"], ["priced", "Has a price"], ["earning", "Shows profit"], ["phone", "Has a phone"], ["active", "Hide under offer"]];

type Search = Record<string, string | undefined>;

const list = (value?: string) => (value ? value.split("|").filter(Boolean) : []);
const dollars = (value: number) => (value >= 1000000 ? `$${value / 1000000}M` : `$${value / 1000}k`);

export default async function Find({ searchParams }: { searchParams: Promise<Search> }) {
  const user = await requireUser();
  const s = await searchParams;
  const page = Math.max(1, Number(s.page) || 1);
  const area = s.area ?? "perth";
  const routes = list(s.route);
  const types = list(s.type);
  const show = types.some((t) => SECTORS.includes(t)) ? "practice" : s.show ?? "sale";
  const term = (s.q ?? "").trim().toLowerCase().replace(/[%_,()]/g, " ");
  const suburb = (s.suburb ?? "").trim().replace(/[%_,()]/g, " ");

  let query = db().from("businesses").select("id, kind, site, status, name, types, suburb, price_text, route, tags, first_seen, turnover, profit", { count: "exact" })
    .eq("on_sheet", true).neq("status", "Removed");
  if (show !== "all") query = query.eq("kind", show);
  if (routes.length) query = query.in("route", routes);
  if (types.length) query = query.overlaps("types", types);
  if (area === "perth") query = query.eq("perth", true);
  if (s.site) query = query.eq("site", s.site);
  if (suburb) query = query.ilike("suburb", `%${suburb}%`);
  if (term) query = query.ilike("search_text", `%${term}%`);
  if (s.min) query = query.gte("price", Number(s.min));
  if (s.max) query = query.lte("price", Number(s.max)).gt("price", 0);
  if (s.turnover) query = query.gte("turnover", Number(s.turnover));
  if (s.profit) query = query.gte("profit", Number(s.profit));
  if (s.fresh) query = query.gte("first_seen", new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString());
  if (s.priced) query = query.gt("price", 0);
  if (s.earning) query = query.gt("profit", 0);
  if (s.phone) query = query.not("phone", "is", null).neq("phone", "");
  if (s.active) query = query.neq("status", "Under offer");
  if (s.sort === "cheapest") query = query.order("price", { ascending: true, nullsFirst: false });
  else if (s.sort === "profit") query = query.order("profit", { ascending: false, nullsFirst: false });
  else if (s.sort === "suburb") query = query.order("suburb", { ascending: true, nullsFirst: false });
  else query = query.order("first_seen", { ascending: false, nullsFirst: false });
  const { data, count, error } = await query.order("id").range((page - 1) * PAGE, page * PAGE - 1);
  if (error) throw new Error(error.message);
  const rows = (data ?? []) as unknown as Business[];
  const total = count ?? 0;

  /** This page's address with some filters changed. Changing a filter goes back to page 1. */
  const href = (change: Search) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries({ ...s, page: undefined, ...change })) if (value) params.set(key, value);
    const text = params.toString();
    return text ? `/find?${text}` : "/find";
  };
  const toggled = (key: string, current: string[], value: string) => {
    const next = current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
    return href({ [key]: next.join("|") || undefined });
  };

  const active: { label: string; off: string }[] = [
    ...(term ? [{ label: `"${s.q}"`, off: href({ q: undefined }) }] : []),
    ...routes.map((r) => ({ label: r, off: toggled("route", routes, r) })),
    ...types.map((t) => ({ label: t, off: toggled("type", types, t) })),
    ...FLAGS.filter(([key]) => s[key]).map(([key, label]) => ({ label, off: href({ [key]: undefined }) })),
    ...(suburb ? [{ label: suburb, off: href({ suburb: undefined }) }] : []),
    ...(s.site ? [{ label: s.site, off: href({ site: undefined }) }] : []),
    ...(s.min ? [{ label: `From ${dollars(Number(s.min))}`, off: href({ min: undefined }) }] : []),
    ...(s.max ? [{ label: `Up to ${dollars(Number(s.max))}`, off: href({ max: undefined }) }] : []),
    ...(s.turnover ? [{ label: `Turnover ${dollars(Number(s.turnover))}+`, off: href({ turnover: undefined }) }] : []),
    ...(s.profit ? [{ label: `Profit ${dollars(Number(s.profit))}+`, off: href({ profit: undefined }) }] : []),
  ];
  const kept = Object.entries(s).filter(([key, value]) => value && !["q", "suburb", "site", "min", "max", "turnover", "profit", "sort", "page"].includes(key)) as [string, string][];

  return (
    <Shell user={user} active="/find">
      <h1>Find</h1>
      <Filters>
        {kept.map(([key, value]) => <input key={key} type="hidden" name={key} value={value} />)}
        <div className="searchrow">
          <input className="input search" type="search" name="q" aria-label="Search name, suburb or seller" placeholder="Search name, suburb or seller" defaultValue={s.q ?? ""} />
          <button type="submit" className="btn primary">Search</button>
        </div>
        <div className="chips">
          {[["sale", "For sale"], ["practice", "Health practices"], ["all", "Everything"]].map(([value, label]) => (
            <Link key={value} className={show === value ? "chip on" : "chip"} href={href({ show: value, type: undefined, route: undefined })}>{label}</Link>
          ))}
          <span className="chipgap" />
          <Link className={area === "perth" ? "chip on" : "chip"} href={href({ area: area === "perth" ? "all" : "perth" })}>Perth only</Link>
        </div>
        <div className="chips">
          {show !== "practice" ? SALE_ROUTES.map((r) => <Link key={r} className={routes.includes(r) ? "chip on" : "chip"} href={toggled("route", routes, r)}>{r}</Link>) : null}
          {FLAGS.map(([key, label]) => <Link key={key} className={s[key] ? "chip on" : "chip"} href={href({ [key]: s[key] ? undefined : "1" })}>{label}</Link>)}
        </div>
        <details className="more" open={Boolean(types.length)}>
          <summary>Type of business{types.length ? ` (${types.length})` : ""}</summary>
          <div className="chips">
            {(show === "practice" ? SECTORS : SALE_TYPES).map((t) => <Link key={t} className={types.includes(t) ? "chip on" : "chip"} href={toggled("type", types, t)}>{t}</Link>)}
          </div>
        </details>
        <details className="more" open={Boolean(s.min || s.max || s.turnover || s.profit || s.site || suburb)}>
          <summary>More filters</summary>
          <div className="fieldgrid">
            <label className="field">Suburb<input className="input" name="suburb" defaultValue={s.suburb ?? ""} /></label>
            <label className="field">Lowest price
              <select name="min" defaultValue={s.min ?? ""}><option value="">Any</option>{PRICES.map((p) => <option key={p} value={p}>{dollars(p)}</option>)}</select>
            </label>
            <label className="field">Highest price
              <select name="max" defaultValue={s.max ?? ""}><option value="">Any</option>{PRICES.map((p) => <option key={p} value={p}>{dollars(p)}</option>)}</select>
            </label>
            <label className="field">Turnover at least
              <select name="turnover" defaultValue={s.turnover ?? ""}><option value="">Any</option>{FIGURES.map((p) => <option key={p} value={p}>{dollars(p)}</option>)}</select>
            </label>
            <label className="field">Profit at least
              <select name="profit" defaultValue={s.profit ?? ""}><option value="">Any</option>{FIGURES.map((p) => <option key={p} value={p}>{dollars(p)}</option>)}</select>
            </label>
            <label className="field">Site
              <select name="site" defaultValue={s.site ?? ""}><option value="">All sites</option>{SITES.map((site) => <option key={site}>{site}</option>)}</select>
            </label>
          </div>
        </details>
        <div className="resultbar">
          <span><b>{total.toLocaleString()}</b> found</span>
          {active.map((tag) => <Link key={tag.label} className="tagoff" href={tag.off} aria-label={`Remove ${tag.label}`}>{tag.label} <span aria-hidden="true">×</span></Link>)}
          {active.length ? <Link className="clear" href={`/find${show === "sale" ? "" : `?show=${show}`}`}>Clear all</Link> : null}
          <label className="field sort">Sort
            <select name="sort" defaultValue={s.sort ?? ""}><option value="">Newest first</option><option value="cheapest">Cheapest first</option><option value="profit">Highest profit</option><option value="suburb">By suburb</option></select>
          </label>
        </div>
      </Filters>
      <div className="head"><span className="c1">Business</span><span className="c2">Route</span><span className="c3">Details</span><span className="c4">Price</span><span className="c5">Added</span></div>
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
      {rows.length === 0 ? <p className="note">Nothing matches. Try removing a tag.</p> : null}
      <div className="pages">
        {page > 1 ? <Link className="btn" href={`${href({})}${href({}).includes("?") ? "&" : "?"}page=${page - 1}`}>Previous</Link> : null}
        <span>Page {page} of {Math.max(1, Math.ceil(total / PAGE))}</span>
        {page * PAGE < total ? <Link className="btn" href={`${href({})}${href({}).includes("?") ? "&" : "?"}page=${page + 1}`}>Next</Link> : null}
      </div>
    </Shell>
  );
}
