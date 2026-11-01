import { Shell } from "@/components/shell";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

const SITES = ["healthdirect", "bsale", "business2sell", "AnyBusiness", "businessforsale.com.au", "commercialrealestate.com.au", "SEEK Business"];

export default async function Sources() {
  const user = await requireUser();
  const counts = await Promise.all(SITES.map(async (site) => {
    const { count } = await db().from("businesses").select("id", { count: "exact", head: true }).eq("on_sheet", true).eq("site", site);
    return [site, count ?? 0] as const;
  }));
  const { data: runs } = await db().from("site_runs").select("*").order("site");

  return (
    <Shell user={user} active="/sources">
      <h1>Sources</h1>
      <p className="lede">Where the data comes from, and what each bot did last.</p>
      <div className="tablewrap"><table>
        <thead><tr><th scope="col">Site</th><th scope="col">Rows here</th></tr></thead>
        <tbody>{counts.filter(([, total]) => total > 0).sort((a, b) => b[1] - a[1]).map(([site, total]) => <tr key={site}><td><b>{site}</b></td><td className="fig">{total.toLocaleString()}</td></tr>)}</tbody>
      </table></div>
      <h2 style={{ marginTop: 20 }}>Last run of each bot</h2>
      <div className="tablewrap"><table>
        <thead><tr><th scope="col">Bot</th><th scope="col">When</th><th scope="col">Result</th></tr></thead>
        <tbody>{runs?.map((r: any) => <tr key={r.site}><td><b>{r.site}</b></td><td>{r.started}</td><td>{r.result}</td></tr>)}</tbody>
      </table></div>
    </Shell>
  );
}
