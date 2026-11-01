import Link from "next/link";
import { Shell } from "@/components/shell";
import { moveOn } from "@/lib/actions";
import { requireUser } from "@/lib/auth";
import { db, LAST_STAGE, link, routeClass, STAGES } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function Pipeline() {
  const user = await requireUser();
  const { data, error } = await db().from("tracking").select("business_id, stage, next_step, businesses(name, route)");
  if (error) throw new Error(error.message);
  const cards = (data ?? []) as any[];

  return (
    <Shell user={user} active="/pipeline">
      <h1>Pipeline</h1>
      <p className="lede">Where every conversation stands. Open a business in Find and choose Add to pipeline to start.</p>
      <div className="boardwrap"><div className="board">
        {STAGES.map((stage) => {
          const here = cards.filter((c) => c.stage === stage);
          return (
            <section className="col" key={stage}>
              <div className="colhead"><span>{stage}</span><span>{here.length}</span></div>
              {here.map((c) => (
                <div className="pcard" key={c.business_id}>
                  <Link href={link(c.business_id)}><span className="ltitle">{c.businesses?.name}</span><span className="lsub">{c.next_step}</span></Link>
                  <span className={routeClass(c.businesses?.route ?? "")}>{c.businesses?.route}</span>
                  {stage === LAST_STAGE ? null : (
                    <form action={moveOn}>
                      <input type="hidden" name="id" value={c.business_id} />
                      <input type="hidden" name="stage" value={stage} />
                      <button type="submit" className="pmove">Move on</button>
                    </form>
                  )}
                </div>
              ))}
            </section>
          );
        })}
      </div></div>
    </Shell>
  );
}
