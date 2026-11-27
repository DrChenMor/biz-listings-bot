import { Shell } from "@/components/shell";
import { disconnectDrive } from "@/lib/actions";
import { requireUser } from "@/lib/auth";
import { db, when } from "@/lib/db";
import { brokenSince, checkConnection, connection, connectReady } from "@/lib/google";

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
  // Ask Google whether the saved connection still works, so this page never says "connected" when it isn't.
  await checkConnection();
  const drive = await connection();
  const brokenAt = drive ? null : await brokenSince();
  const copier = (runs ?? []).find((r: { site: string }) => r.site === "email copier") as { started: string; result: string } | undefined;

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
            {brokenAt ? <p className="note warn">The connection stopped working on {when(brokenAt)}: Google needs Tom to sign in again. Press the button below, signed in as <b>contacttomharari@gmail.com</b>.</p>
              : <p>Connect Tom&apos;s Google account so the website can save files into the Acquisitions folders, such as filled-in worksheets. Sign in as <b>contacttomharari@gmail.com</b>.</p>}
            {connectReady() ? <a className="btn primary" href="/drive/connect">Connect Google Drive</a>
              : <p className="lsub">Not set up yet: the Google sign-in settings are missing.</p>}
          </>
        )}
      </section>
      <section className="card" style={{ marginBottom: 20 }} id="email-copier">
        <h2>Email copier</h2>
        <p>A small script in Tom&apos;s deals Google account copies emails with each business&apos;s contacts into its Communication doc and its page, every morning at 7. It can only read Gmail: it can&apos;t send, delete or change any email.</p>
        {copier ? <p className={copier.result.startsWith("ok") ? "note" : "note warn"}>Last run {copier.started}: {copier.result}</p>
          : <p className="lsub">Not set up yet. Tom sets it up once, in about five minutes:</p>}
        <details className="more" open={!copier}>
          <summary>How to set it up</summary>
          <ol className="steps">
            <li>Signed in to Google as <b>contacttomharari@gmail.com</b>, open <a href="https://script.google.com/home/projects/create" target="_blank" rel="noreferrer">a new Apps Script project</a> and name it &quot;Deal desk email copier&quot;.</li>
            <li>In <b>Project Settings</b> (the gear), tick <b>Show &quot;appsscript.json&quot; manifest file in editor</b>.</li>
            <li>Back in the editor, replace everything in <b>appsscript.json</b> with <a href="/api/mail/script?file=manifest" target="_blank">this</a>, and everything in <b>Code.gs</b> with <a href="/api/mail/script" target="_blank">this</a>. Save.</li>
            <li>In <b>Project Settings</b>, under <b>Script properties</b>, add <code>DEAL_DESK_URL</code> = <code>https://deal-desk-red.vercel.app</code> and <code>DEAL_DESK_KEY</code> = the key Chen sends you privately.</li>
            <li>Pick <b>setup</b> in the function menu and press <b>Run</b>. Google warns the app isn&apos;t verified, because it&apos;s your own script: choose Advanced, then Go to the project, and allow it to view your email and edit Drive and Docs.</li>
            <li>That&apos;s it. It runs every morning. To run it now, pick <b>copyEmails</b> and press Run.</li>
          </ol>
        </details>
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
