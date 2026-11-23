import { requireUser } from "@/lib/auth";
import { MANIFEST, SCRIPT } from "@/lib/apps-script";

export const dynamic = "force-dynamic";

/** The email copier's code, for pasting into Apps Script. Signed-in people only. ?file=manifest gives appsscript.json. */
export async function GET(request: Request) {
  await requireUser();
  const manifest = new URL(request.url).searchParams.get("file") === "manifest";
  return new Response(manifest ? MANIFEST : SCRIPT, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
