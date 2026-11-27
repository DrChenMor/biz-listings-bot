import { addContact, removeContact } from "@/lib/actions";
import { db, when } from "@/lib/db";
import { followUpLink } from "@/lib/mail";

type Mail = { gmail_id: string; sent_at: string; sender: string | null; recipients: string | null; subject: string | null; body: string | null; incoming: boolean; attachments: string[] };

const shortName = (header: string | null) => (header ?? "").replace(/<[^>]*>/g, "").replace(/"/g, "").trim() || header || "";

/** The people we email about this business. The email copier copies their emails here. */
export async function ContactsCard({ id, name }: { id: string; name: string }) {
  const { data } = await db().from("contacts").select("email, name, role").eq("business_id", id).order("added_at");
  const { data: last } = await db().from("mail").select("thread_id").eq("business_id", id).not("thread_id", "is", null)
    .order("sent_at", { ascending: false }).limit(1).maybeSingle();
  const follow = followUpLink(name, data ?? [], last?.thread_id ?? null);
  return (
    <section className="card"><h2>Contacts</h2>
      <p className="lsub">The seller's and broker's email addresses. Emails to and from them are copied here and into the Communication doc in Drive each day.</p>
      {follow ? <p><a className="btn" href={follow} target="_blank" rel="noreferrer">{last?.thread_id ? "Follow up in the last email thread" : "Write a follow-up email"}</a>
        <span className="lsub"> Opens Tom&apos;s deals Gmail. Nothing is sent until you press Send.</span></p> : null}
      {(data ?? []).map((c) => (
        <form action={removeContact} className="item contactrow" key={c.email}>
          <input type="hidden" name="id" value={id} /><input type="hidden" name="email" value={c.email} />
          <span><span className="ltitle">{c.name || c.email}</span><span className="lsub">{c.role} · {c.email}</span></span>
          <button type="submit" className="plain danger" aria-label={`Remove ${c.email}`}>Remove</button>
        </form>
      ))}
      <form action={addContact} className="actions folderrow" style={{ marginTop: 8 }}>
        <input type="hidden" name="id" value={id} />
        <input className="input" name="email" type="email" required placeholder="Email address" aria-label="Email address" style={{ flex: "2 1 200px" }} />
        <input className="input" name="name" placeholder="Name (optional)" aria-label="Name" style={{ flex: "1 1 140px" }} />
        <select name="role" aria-label="Role" defaultValue="Seller"><option>Seller</option><option>Broker</option><option>Other</option></select>
        <button type="submit" className="btn">Add</button>
      </form>
    </section>
  );
}

/** Every email copied for this business, newest first, without the quoted earlier replies. */
export async function CommunicationCard({ id }: { id: string }) {
  const { data } = await db().from("mail").select("*").eq("business_id", id).order("sent_at", { ascending: false }).limit(50);
  const mail = (data ?? []) as Mail[];
  if (!mail.length) return null;
  return (
    <section className="card"><h2>Communication</h2>
      {mail.map((m) => (
        <details className="mail" key={m.gmail_id}>
          <summary>
            <span className="ltitle">{m.incoming ? shortName(m.sender) : `Tom to ${shortName(m.recipients)}`}{m.subject ? `: ${m.subject}` : ""}</span>
            <span className="lsub">{when(m.sent_at)}{m.attachments?.length ? ` · ${m.attachments.length} attachment${m.attachments.length > 1 ? "s" : ""}` : ""}</span>
          </summary>
          <div className="writing">{m.body}</div>
          {m.attachments?.length ? <p className="lsub">Attached: {m.attachments.join(", ")}. Saved in the Drive folder.</p> : null}
        </details>
      ))}
    </section>
  );
}
