import { acceptName, ignoreName } from "@/lib/actions";

export type NameSuggestion = { id: number; business_id: string; name: string; source: string; evidence: string | null };

/** Names found in the business's documents, to accept or ignore. Hover shows where each was found. */
export function NameSuggestions({ suggestions, back, compact = false }: { suggestions: NameSuggestion[]; back: string; compact?: boolean }) {
  if (!suggestions.length) return null;
  return (
    <div className={compact ? "namesugg compact" : "namesugg note"}>
      {suggestions.slice(0, compact ? 1 : 5).map((s) => (
        <div className="namerow" key={s.id}>
          <span title={s.evidence ?? s.source}>{compact ? "Real name? " : "Found in the documents: "}<b>{s.name}</b>{compact ? "" : <span className="lsub"> · {s.evidence ?? s.source}</span>}</span>
          <span className="namebtns">
            <form action={acceptName}><input type="hidden" name="suggestion" value={s.id} /><input type="hidden" name="back" value={back} /><button type="submit" className="plain dark">Use it</button></form>
            <form action={ignoreName}><input type="hidden" name="suggestion" value={s.id} /><input type="hidden" name="back" value={back} /><button type="submit" className="plain dark">Ignore</button></form>
          </span>
        </div>
      ))}
    </div>
  );
}
