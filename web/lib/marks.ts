/** What Chen or Tom made of a listing in Find. Not reviewed is where every listing starts. Safe for the browser. */
export const MARKS = ["Not reviewed", "Seen", "Not sure", "Interested", "Not for us"];
/** Marks that come from the pipeline, not from the review menu. */
export const PIPELINE_MARKS = ["In pipeline", "Passed", "Archived"];

export function markClass(mark: string): string {
  return `mark m-${mark.toLowerCase().replace(/[^a-z]+/g, "-")}`;
}
