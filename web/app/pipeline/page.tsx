import Link from "next/link";
import { Shell } from "@/components/shell";
import { addBusiness, addFromFolder, archiveBusiness, binFolder, deleteBusiness, followedUp, linkFolder, moveOn, restoreBusiness, setStage } from "@/lib/actions";
import { requireUser } from "@/lib/auth";
import { BY_HAND, Business, dealCard, db, link, money, nameOf, NEXT_STAGE, PASSED, STAGES, Tracking, when } from "@/lib/db";
import { businessFolders, driveReady, DriveFolder, folderLink } from "@/lib/drive";

export const dynamic = "force-dynamic";

type Row = Tracking & { businesses: Business };

/** The views on the strip: one stage, or a group of them. Each is its own address, so it can be bookmarked. */
const VIEWS: Record<string, { label: string; shows: (r: Row) => boolean }> = {
  active: { label: "Active", shows: (r) => !r.archived_at && r.stage !== PASSED },
  all: { label: "All", shows: (r) => !r.archived_at },
  passed: { label: "Passed", shows: (r) => !r.archived_at && r.stage === PASSED },
  archive: { label: "Archive", shows: (r) => Boolean(r.archived_at) },
};

const stageLink = (stage: string) => `/pipeline?stage=${encodeURIComponent(stage)}`;

function Figure({ label, value }: { label: string; value: number | null }) {
  return <div><dt>{label}</dt><dd className="fig">{value ? money(value) : "—"}</dd></div>;
}

/** Delete right away, behind a confirm. Says what happens, which differs for a business added by hand. */
function DeleteForm({ row, name, hidden }: { row: Row; name: string; hidden: (more?: Record<string, string>) => React.ReactNode }) {
  const byHand = row.businesses.site === BY_HAND;
  return (
    <form action={deleteBusiness}>
      {hidden({ sure: "yes" })}
      <p className="lsub">{byHand ? "Removes it, its card, worksheets and notes from the website."
        : "Removes it from the pipeline with its card and worksheets, and marks it Not for us in Find. The bots keep the listing itself."}</p>
      {row.drive_folder_id ? <label className="lsub dcheck"><input type="checkbox" name="bin_folder" value="yes" /> Also put its Drive folder in the Drive bin</label> : null}
      <button type="submit" className="pmove danger">Yes, delete {name.slice(0, 40)}</button>
    </form>
  );
}

function DealCard({ row, here }: { row: Row; here: string }) {
  const b = row.businesses;
  const card = dealCard(b, row);
  const next = NEXT_STAGE[row.stage];
  const name = nameOf(b, row);
  const hidden = (more: Record<string, string> = {}) => Object.entries({ id: b.id, back: here, ...more })
    .map(([key, value]) => <input key={key} type="hidden" name={key} value={value} />);
  if (row.archived_at) {
    return (
      <article className="dcard">
        <Link href={link(b.id)} className="dname">{name}</Link>
        <span className="lsub">Was at {row.stage} · archived {when(row.archived_at)}{row.archived_by ? ` by ${row.archived_by}` : ""}</span>
        <div className="dbuttons">
          <form action={restoreBusiness}>{hidden()}<button type="submit" className="pmove">Restore</button></form>
        </div>
        <details className="dline">
          <summary className="lsub">Delete</summary>
          <DeleteForm row={row} name={name} hidden={hidden} />
        </details>
      </article>
    );
  }
  return (
    <article className="dcard">
      <Link href={link(b.id)} className="dname">{name}</Link>
      {name !== b.name ? <span className="lsub">Listed as: {b.name}</span> : null}
      {b.status === "Removed" ? <span className="pill r-stop">Listing ended</span> : null}
      <span className="lsub">{[card.location, card.product].filter(Boolean).join(" · ")}</span>
      <dl className="dfacts">
        <Figure label="Asking" value={card.asking} />
        <Figure label="Turnover" value={card.turnover} />
        <Figure label="Expenses" value={card.expenses} />
        <Figure label="Profit" value={card.profit} />
      </dl>
      {card.sellingReason ? <p className="dline"><b>Selling:</b> {card.sellingReason}</p> : null}
      {card.underManagement ? <p className="dline"><b>Under management:</b> {card.underManagement}</p> : null}
      <p className="dline lsub">
        {row.approached_on ? `Approached ${when(row.approached_on)}` : "Not approached yet"}
        {row.followed_up_on ? ` · followed up ${when(row.followed_up_on)}` : ""}
      </p>
      {row.next_step ? <p className="dline"><b>Next:</b> {row.next_step}{row.next_due ? ` (by ${when(row.next_due)})` : ""}</p> : null}
      {row.drive_folder_id ? <a className="dline" href={folderLink(row.drive_folder_id)} target="_blank" rel="noreferrer">Drive folder</a> : null}
      <div className="dbuttons">
        {next ? (
          <form action={moveOn}>{hidden({ stage: row.stage })}<button type="submit" className="pmove">Move to {next}</button></form>
        ) : null}
        {row.stage === "Approached" ? (
          <form action={followedUp}>{hidden()}<button type="submit" className="pmove">Followed up today</button></form>
        ) : null}
        {row.stage === "Due diligence" ? (
          <form action={setStage}>{hidden({ stage: "Deal re-work" })}<button type="submit" className="pmove">Needs re-work</button></form>
        ) : null}
      </div>
      <form action={setStage} className="dstage">
        {hidden()}
        <select name="stage" aria-label={`Stage for ${name}`} defaultValue={row.stage}>
          {[...STAGES, PASSED].map((s) => <option key={s}>{s}</option>)}
        </select>
        <button type="submit" className="btn">Move</button>
      </form>
      <details className="dline">
        <summary className="lsub">Archive or delete</summary>
        <form action={archiveBusiness}>
          {hidden()}
          <p className="lsub">Takes it off every list. Nothing is deleted, and Restore in the Archive view brings it back.</p>
          {row.drive_folder_id ? <label className="lsub dcheck"><input type="checkbox" name="move_folder" value="yes" defaultChecked /> Also move its Drive folder to Passed</label> : null}
          <button type="submit" className="pmove">Archive {name.slice(0, 40)}</button>
        </form>
        <p className="lsub dor">or delete it now:</p>
        <DeleteForm row={row} name={name} hidden={hidden} />
      </details>
    </article>
  );
}

export default async function Pipeline({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const user = await requireUser();
  const params = await searchParams;
  const stage = params.stage && [...STAGES, PASSED].includes(params.stage) ? params.stage : null;
  const view = stage ? null : params.view && VIEWS[params.view] ? params.view : "active";
  const here = stage ? stageLink(stage) : view === "active" ? "/pipeline" : `/pipeline?view=${view}`;
  const { data, error } = await db().from("tracking").select("*, businesses(*)").order("updated_at", { ascending: false });
  if (error) throw new Error(error.message);
  const rows = (data ?? []) as unknown as Row[];
  const live = rows.filter((r) => !r.archived_at);
  const shown = rows.filter((r) => (stage ? !r.archived_at && r.stage === stage : VIEWS[view ?? "active"].shows(r)));
  const linked = new Set(rows.map((r) => r.drive_folder_id));
  let unlinked: DriveFolder[] = [];
  try {
    if (driveReady()) unlinked = (await businessFolders()).filter((f) => !linked.has(f.id));
  } catch {
    unlinked = [];  // Drive having a bad moment shouldn't stop the pipeline from showing.
  }
  const working = live.filter((r) => r.stage !== PASSED && !r.drive_folder_id);
  const overview = view === "active" || view === "all";
  const groups = stage ? [stage] : view === "archive" ? ["Archived"] : view === "passed" ? [PASSED] : view === "all" ? [...STAGES, PASSED] : STAGES;

  return (
    <Shell user={user} active="/pipeline">
      <h1>Pipeline</h1>
      <p className="lede">Every business you're working on, and the stage it's at.</p>
      <nav className="stagestrip" aria-label="Views">
        {Object.entries(VIEWS).map(([key, v]) => {
          const href = key === "active" ? "/pipeline" : `/pipeline?view=${key}`;
          return <Link key={key} href={href} className={href === here ? "chip on" : "chip"} aria-current={href === here ? "page" : undefined}>
            {v.label} {rows.filter(v.shows).length}</Link>;
        })}
      </nav>
      <nav className="stagestrip" aria-label="One stage">
        {STAGES.map((s) => {
          const count = live.filter((r) => r.stage === s).length;
          const on = s === stage;
          return <Link key={s} href={stageLink(s)} className={on ? "chip on" : count ? "chip" : "chip empty"} aria-current={on ? "page" : undefined}>{s} {count}</Link>;
        })}
      </nav>
      {groups.map((group) => {
        const inGroup = group === "Archived" ? shown : shown.filter((r) => r.stage === group);
        return inGroup.length ? (
          <section key={group} className="stagesec">
            <h2>{group} <span className="lsub">({inGroup.length})</span></h2>
            <div className="dcards">{inGroup.map((row) => <DealCard key={row.business_id} row={row} here={here} />)}</div>
          </section>
        ) : null;
      })}
      {!shown.length ? (
        <p className="note">{view === "archive" ? "Nothing archived. Archive a business from its card when it's off the table."
          : stage ? `Nothing at ${stage} right now.` : "Nothing in the pipeline yet. Open a business in Find and give it a stage."}</p>
      ) : null}
      {overview && unlinked.length ? (
        <section className="stagesec card">
          <h2>Drive folders not linked yet ({unlinked.length})</h2>
          <p className="lsub">Folders in Acquisitions. Link each one to its business, or add it to the pipeline as a new business.</p>
          {unlinked.map((folder) => (
            <div className="item folderrow" key={folder.id}>
              <a className="ltitle" href={folderLink(folder.id)} target="_blank" rel="noreferrer">{folder.name}{folder.passed ? " (Passed)" : ""}</a>
              {working.length ? (
                <form action={linkFolder} className="actions">
                  <input type="hidden" name="folder" value={folder.id} /><input type="hidden" name="folder_name" value={folder.name} />
                  <input type="hidden" name="back" value="/pipeline" />
                  <select name="id" aria-label={`Business for ${folder.name}`} defaultValue="">
                    <option value="" disabled>It's this business…</option>
                    {working.map((r) => <option key={r.business_id} value={r.business_id}>{nameOf(r.businesses, r).slice(0, 70)}</option>)}
                  </select>
                  <button type="submit" className="btn">Link</button>
                </form>
              ) : null}
              <form action={addFromFolder} className="actions">
                <input type="hidden" name="folder" value={folder.id} /><input type="hidden" name="folder_name" value={folder.name} />
                <select name="stage" aria-label={`Stage for ${folder.name}`} defaultValue={folder.passed ? PASSED : "Documents in"}>
                  {[...STAGES, PASSED].map((s) => <option key={s}>{s}</option>)}
                </select>
                <button type="submit" className="btn">Add as new business</button>
              </form>
              <details className="folderdel">
                <summary className="lsub">Delete</summary>
                <form action={binFolder} className="actions">
                  <input type="hidden" name="folder" value={folder.id} /><input type="hidden" name="sure" value="yes" />
                  <span className="lsub">Puts the folder and everything in it in the Drive bin. Drive keeps it there for 30 days.</span>
                  <button type="submit" className="btn danger">Yes, delete {folder.name.slice(0, 30)}</button>
                </form>
              </details>
            </div>
          ))}
        </section>
      ) : null}
      {overview ? (
      <details className="more stagesec">
        <summary>Add a business that isn't listed</summary>
        <form action={addBusiness} className="fieldgrid">
          <label className="field">Business name<input className="input" name="name" required /></label>
          <label className="field">Location<input className="input" name="location" /></label>
          <label className="field">Link (optional)<input className="input" name="url" type="url" /></label>
          <label className="field">Stage<select name="stage" defaultValue="Approached">{STAGES.map((s) => <option key={s}>{s}</option>)}</select></label>
          <button type="submit" className="btn primary">Add</button>
        </form>
      </details>
      ) : null}
    </Shell>
  );
}
