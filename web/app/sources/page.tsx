import { Shell } from "@/components/shell";
import { disconnectDrive } from "@/lib/actions";
import { requireUser } from "@/lib/auth";
import { db, when } from "@/lib/db";
import { connection, connectReady } from "@/lib/google";

export const dynamic = "force-dynamic";

const SITES = ["healthdirect", "bsale", "business2sell", "AnyBusiness", "businessforsale.com.au", "No Agent Business", "commercialrealestate.com.au", "SEEK Business"];

const DRIVE_NOTES: Record<string, [string, string]> = {
  connected: ["note", "Google Drive is connected."],
  cancelled: ["note warn", "Connecting was cancelled, so nothing changed."],
  expired: ["note warn", "That sign-in took too long or came from another window. Press Connect Google Drive again."],
  failed: ["note warn", "Google didn't finish connecting. Press Connect Google Drive again."],
  "not-set-up": ["note warn", "Connecting needs the Google sign-in settings first (GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET)."],
  disconnected: ["note", "Google Drive is disconnected. The website can still read the folders, but can't save into them."],
};

export default async function Sources({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const user = await requireUser();
  const shown = DRIVE_NOTES[(await searchParams).drive ?? ""];
  const counts = await Promise.all(SITES.map(async (site) => {
    const { count } = await db().from("businesses").select("id", { count: "exact", head: true }).eq("on_sheet", true).eq("site", site);
    return [site, count ?? 0] as const;
  }));
  const { data: runs } = await db().from("site_runs").select("*").order("site");
  const drive = await connection();

  return (
    <Shell user={user} active="/sources">
      <h1>Sources</h1>
      <p className="lede">Where the data comes from, and what each bot did last.</p>
      {shown ? <p className={shown[0]} role="status">{shown[1]}</p> : null}
      <section className="card" style={{ marginBottom: 20 }}>
        <h2>Google Drive</h2>
        {drive ? (
          <>
            <p>Connected as <b>{drive.email}</b>, by {drive.connected_by} on {when(drive.connected_at)}. The website saves worksheets into each business&apos;s folder as this account.</p>
            <form action={disconnectDrive}><button type="submit" className="btn">Disconnect</button></form>
          </>
        ) : (
          <>
            <p>Connect Tom&apos;s Google account so the website can save files into the Acquisitions folders, such as filled-in worksheets. Sign in as <b>contacttomharari@gmail.com</b>.</p>
            {connectReady() ? <a className="btn primary" href="/drive/connect">Connect Google Drive</a>
              : <p className="lsub">Not set up yet: the Google sign-in settings are missing.</p>}
          </>
        )}
      </section>
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
