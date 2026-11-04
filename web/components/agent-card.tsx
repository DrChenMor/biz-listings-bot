import { cancelEnquiry, queueEnquiry } from "@/lib/actions";
import { AGENT_SITES, Business, db, Enquiry, Evaluation, statusClass, when } from "@/lib/db";

function Points({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return <><h3>{title}</h3><ul className="points">{items.map((item) => <li key={item}>{item}</li>)}</ul></>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="fact"><span className="flab">{label}</span><span className="fval">{value}</span></div>;
}

/** What the broker agent has done for this business, and the button that starts it. */
export async function AgentCard({ business }: { business: Business }) {
  const { data: row } = await db().from("enquiries").select("*").eq("business_id", business.id).maybeSingle();
  const enquiry = row as Enquiry | null;
  const can = business.kind === "sale" && AGENT_SITES.includes(business.site) && business.url && business.on_sheet && business.status !== "Sold";
  const { data: emails } = enquiry ? await db().from("agent_emails").select("*").eq("enquiry_id", enquiry.id).order("at") : { data: [] };
  const { data: files } = enquiry ? await db().from("agent_documents").select("*").eq("enquiry_id", enquiry.id).order("at") : { data: [] };
  const { data: scored } = await db().from("evaluations").select("summary, at").eq("business_id", business.id).maybeSingle();
  const evaluation = scored?.summary as Evaluation | undefined;

  return (
    <>
      <section className="card"><h2>Broker agent</h2>
        {enquiry ? (
          <p><span className={statusClass(enquiry.status)}>{enquiry.status}</span> <span className="lsub">{enquiry.detail}</span></p>
        ) : can ? <p className="lsub">Sends the first enquiry, reads the reply and returns a plain NDA.</p>
          : <p className="lsub">The agent can't approach this business.</p>}
        {can && (!enquiry || enquiry.status === "Test only") ? (
          <form action={queueEnquiry}><input type="hidden" name="id" value={business.id} /><button type="submit" className="btn primary">Send first enquiry</button></form>
        ) : null}
        {enquiry?.status === "Queued" ? (
          <form action={cancelEnquiry}><input type="hidden" name="id" value={business.id} /><button type="submit" className="btn">Take it back</button></form>
        ) : null}
        {emails?.map((email: any) => (
          <div className="log" key={email.id}>
            <span className="ldate">{when(email.at)} · {email.direction === "in" ? `From ${email.sender}` : `To ${email.recipient}`}</span>
            {email.summary ?? email.subject}
          </div>
        ))}
        {files?.length ? <h3>Files</h3> : null}
        {files?.map((file: any) => <div className="log" key={file.id}><a href={`/doc/${file.id}`} target="_blank" rel="noreferrer">{file.name}</a> <span className="lsub">{file.kind}</span></div>)}
      </section>
      {evaluation ? (
        <section className="card"><h2>Evaluation</h2>
          <p><b>{evaluation.verdict}.</b> {evaluation.headline}</p>
          <Fact label="Asking price" value={evaluation.asking_price} />
          {evaluation.years.map((y) => <Fact key={y.year} label={y.year} value={`Turnover ${y.turnover}, profit ${y.profit}`} />)}
          <Fact label="Adjusted profit" value={evaluation.adjusted_profit} />
          <Fact label="Price to profit" value={evaluation.price_to_profit} />
          <Fact label="Lease" value={evaluation.lease} />
          <Fact label="Staff" value={evaluation.staff} />
          <Fact label="Owner's role" value={evaluation.owner_involvement} />
          <Points title="Strengths" items={evaluation.strengths} />
          <Points title="Risks" items={evaluation.risks} />
          <Points title="Not in the documents" items={evaluation.missing} />
          <Points title="Ask the broker" items={evaluation.questions} />
        </section>
      ) : null}
    </>
  );
}
