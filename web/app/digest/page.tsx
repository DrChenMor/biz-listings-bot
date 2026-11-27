import { headers } from "next/headers";
import { Shell } from "@/components/shell";
import { requireUser } from "@/lib/auth";
import { buildDigest } from "@/lib/digest";

export const dynamic = "force-dynamic";

/** What Tom's morning email would say right now, so Chen and Tom can see it without waiting for 7am. */
export default async function DigestPreview() {
  const user = await requireUser();
  const host = (await headers()).get("host") ?? "deal-desk-red.vercel.app";
  const digest = await buildDigest(`${host.startsWith("localhost") ? "http" : "https"}://${host}`);
  return (
    <Shell user={user} active="/sources">
      <h1>Morning email</h1>
      <p className="lede">What Tom&apos;s 7am email would say right now. Subject: <b>{digest.subject}</b>{digest.send ? "" : " (nothing new, so it wouldn't be sent)"}</p>
      <iframe title="Morning email preview" srcDoc={digest.html} className="digestframe" />
    </Shell>
  );
}
