import type { Instrumentation } from "next";

/** Every server error on the website is written to the log, with the page or action it happened on. */
export const onRequestError: Instrumentation.onRequestError = async (error, request, context) => {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { logEvent } = await import("./lib/log");
  const problem = error as Error & { digest?: string };
  await logEvent("error", `${request.method} ${request.path}`,
    `${problem?.message ?? String(error)}${problem?.digest ? ` (error code ${problem.digest})` : ""} · ${context.routeType} ${context.routePath}`,
    null, request.path);
};
