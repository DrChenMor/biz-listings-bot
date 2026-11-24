import Link from "next/link";
import { Shell } from "@/components/shell";
import { ConfirmButton } from "@/components/confirm-button";
import { StageSelect } from "@/components/stage-select";
import { addBusiness, addFromFolder, archiveBusiness, binFolder, deleteBusiness, dismissUnmatched, followedUp, linkFolder, linkUnmatched, restoreBusiness, setStage } from "@/lib/actions";
import { requireUser } from "@/lib/auth";
import { BY_HAND, Business, dealCard, db, link, money, nameOf, PASSED, STAGES, Tracking, when } from "@/lib/db";
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

/** $710k, $3.6M: short enough for a card. */
function short(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1).replace(/\.0$/, "")}M`;
  if (value >= 1_000) return `$${Math.round(value / 1_000)}k`;
  return money(value);
}

/** The small links at the bottom of a card. Delete asks first; archive is undone with Restore. */
function CardActions({ row, name, hidden }: { row: Row; name: string; hidden: (more?: Record<string, string>) => React.ReactNode }) {
  const byHand = row.businesses.site === BY_HAND;
  const deleteQuestion = byHand
    ? `Delete ${name}? Its card, worksheets and notes are removed from the website. The Drive folder stays.`
    : `Delete ${name}? It leaves the pipeline with its card and worksheets, and is marked Not for us in Find. The Drive folder stays.`;
  return (
    <div className="dsmall">
      {!row.archived_at && row.drive_folder_id ? <a className="plain dark" href={folderLink(row.drive_folder_id)} target="_blank" rel="noreferrer">Drive</a> : null}
      {!row.archived_at && row.stage === "Approached"
        ? <form action={followedUp}>{hidden()}<button type="submit" className="plain dark">Followed up today</button></form> : null}
      {row.archived_at
        ? <form action={restoreBusiness}>{hidden()}<button type="submit" className="plain dark">Restore</button></form>
        : <form action={archiveBusiness}>{hidden({ move_folder: "yes" })}<button type="submit" className="plain dark" title="Takes it off every list and moves its Drive folder to Passed. Restore brings it back.">Archive</button></form>}
      <form action={deleteBusiness}>{hidden({ sure: "yes" })}<ConfirmButton question={deleteQuestion} className="plain danger">Delete</ConfirmButton></form>
    </div>
  );
}

function DealCard({ row, here }: { row: Row; here: string }) {
  const b = row.businesses;
  const card = dealCard(b, row);
  const name = nameOf(b, row);
  const hidden = (more: Record<string, string> = {}) => Object.entries({ id: b.id, back: here, ...more })
    .map(([key, value]) => <input key={key} type="hidden" name={key} value={value} />);
  if (row.archived_at) {
    return (
      <article className="dcard">
        <Link href={link(b.id)} className="dname">{name}</Link>
        <span className="lsub">Was at {row.stage} · archived {when(row.archived_at)}{row.archived_by ? ` by ${row.archived_by}` : ""}</span>
        <CardActions row={row} name={name} hidden={hidden} />
      </article>
    );
  }
  // Only the figures we know, on one line: no rows of dashes.
  const figures = ([["Asking", card.asking], ["Turnover", card.turnover], ["Expenses", card.expenses], ["Profit", card.profit]] as const)
    .filter(([, value]) => value);
  const dates = [row.approached_on ? `Approached ${when(row.approached_on)}` : "", row.followed_up_on ? `followed up ${when(row.followed_up_on)}` : ""]
    .filter(Boolean).join(" · ");
  return (
    <article className="dcard">
      <Link href={link(b.id)} className="dname" title={name !== b.name ? `Listed as: ${b.name}` : name}>{name}</Link>
      <span className="lsub dclip">{[card.location, card.product].filter(Boolean).join(" · ")}</span>
      {b.status === "Removed" ? <span className="pill r-stop">Listing ended</span> : null}
      {figures.length ? <p className="dline dfigs">{figures.map(([label, value]) => <span key={label}>{label} <b className="fig">{short(value as number)}</b></span>)}</p> : null}
      {card.sellingReason ? <p className="dline dclip"><b>Selling:</b> {card.sellingReason}</p> : null}
      {dates ? <p className="dline lsub">{dates}</p> : null}
      {row.next_step ? <p className="dline dclip"><b>Next:</b> {row.next_step}{row.next_due ? ` (by ${when(row.next_due)})` : ""}</p> : null}
      <form action={setStage} className="dstage">
        <StageSelect stages={[...STAGES, PASSED]} current={row.stage} label={`Stage for ${name}`}>{hidden()}</StageSelect>
      </form>
      <CardActions row={row} name={name} hidden={hidden} />
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
  const { data: unmatchedData } = await db().from("unmatched_mail").select("gmail_id, sent_at, sender, sender_name, subject, snippet")
    .eq("dismissed", false).order("sent_at", { ascending: false }).limit(30);
  const unmatched = unmatchedData ?? [];
  const inPipeline = live.filter((r) => r.stage !== PASSED);
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
              <form action={binFolder} className="folderdel">
                <input type="hidden" name="folder" value={folder.id} /><input type="hidden" name="sure" value="yes" />
                <ConfirmButton question={`Delete the folder ${folder.name}? It goes to the Drive bin with everything in it, and Drive keeps it there for 30 days.`} className="plain danger">Delete folder</ConfirmButton>
              </form>
            </div>
          ))}
        </section>
      ) : null}
      {overview && unmatched.length ? (
        <section className="stagesec card" id="emails">
          <h2>Emails not matched yet ({unmatched.length})</h2>
          <p className="lsub">Emails in Tom's deals inbox from people who aren't in any business's contacts. Pick the business and the sender becomes its contact, so the next run copies their emails. Not about a deal? Dismiss skips that sender from now on.</p>
          {unmatched.map((m) => (
            <div className="item folderrow" key={m.gmail_id}>
              <span className="ltitle">{m.sender_name || m.sender}{m.subject ? `: ${m.subject}` : ""}<span className="lsub"> {m.sender} · {when(m.sent_at)}</span></span>
              <form action={linkUnmatched} className="actions">
                <input type="hidden" name="gmail_id" value={m.gmail_id} />
                <select name="id" aria-label={`Business for the email from ${m.sender}`} defaultValue="" required>
                  <option value="" disabled>It's about…</option>
                  {inPipeline.map((r) => <option key={r.business_id} value={r.business_id}>{nameOf(r.businesses, r).slice(0, 70)}</option>)}
                </select>
                <button type="submit" className="btn">Add as contact</button>
              </form>
              <form action={dismissUnmatched}><input type="hidden" name="gmail_id" value={m.gmail_id} /><button type="submit" className="plain dark">Dismiss</button></form>
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
