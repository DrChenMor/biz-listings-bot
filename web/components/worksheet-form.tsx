"use client";

import { useEffect, useRef, useState } from "react";
import { saveWorksheet, saveWorksheetToDrive } from "@/lib/actions";
import { Field, Kind, number, planTotal, SHEETS } from "@/lib/worksheets";

type Data = Record<string, string>;

const dollars = (n: number) => `${n < 0 ? "-" : ""}$${Math.abs(Math.round(n)).toLocaleString("en-AU")}`;
const times = (price: number, profit: number) => (price && profit ? `${(price / profit).toFixed(2)}×` : "—");

function Choice({ value, options, label, onPick }: { value: string; options: string[]; label: string; onPick: (v: string) => void }) {
  return (
    <span className="wchoice" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button key={option} type="button" role="radio" aria-checked={value === option} className={value === option ? "chip on" : "chip"}
          onClick={() => onPick(value === option ? "" : option)}>{option}</button>
      ))}
    </span>
  );
}

function Money({ value, label, onType }: { value: string; label: string; onType: (v: string) => void }) {
  return <span className="wmoney"><span aria-hidden="true">$</span><input className="input" inputMode="decimal" aria-label={label} value={value} onChange={(e) => onType(e.target.value)} /></span>;
}

function Input({ field, data, set }: { field: Field; data: Data; set: (key: string, value: string) => void }) {
  const value = (key: string) => data[key] ?? "";
  if (field.type === "text") return <label className="wfield"><span>{field.label}</span><input className="input" value={value(field.key)} onChange={(e) => set(field.key, e.target.value)} /></label>;
  if (field.type === "long") return <label className="wfield"><span>{field.label}</span><textarea className="input" rows={3} value={value(field.key)} onChange={(e) => set(field.key, e.target.value)} /></label>;
  if (field.type === "money") return <div className="wfield"><span>{field.label}</span><Money label={field.label} value={value(field.key)} onType={(v) => set(field.key, v)} /></div>;
  if (field.type === "choice") return <div className="wfield"><span>{field.label}</span><Choice label={field.label} options={field.options} value={value(field.key)} onPick={(v) => set(field.key, v)} /></div>;
  if (field.type === "row") {
    return (
      <div className="wrow">
        <span className="wlabel">{field.label}</span>
        <Choice label={`${field.label}: yes or no`} options={["Y", "N"]} value={value(`${field.key}.yn`)} onPick={(v) => set(`${field.key}.yn`, v)} />
        {field.money ? <Money label={`${field.label}: value`} value={value(`${field.key}.value`)} onType={(v) => set(`${field.key}.value`, v)} /> : <span />}
        <input className="input" aria-label={`${field.label}: notes`} placeholder="Notes" value={value(`${field.key}.notes`)} onChange={(e) => set(`${field.key}.notes`, e.target.value)} />
      </div>
    );
  }
  if (field.type !== "plan") return null;
  return (
    <>
      {Array.from({ length: field.rows }, (_, i) => {
        const key = `${field.key}.${i}`;
        return (
          <div className="wrow" key={key}>
            <input className="input" aria-label={`${field.label} ${i + 1}`} placeholder={`Strategy ${i + 1}`} value={value(`${key}.name`)} onChange={(e) => set(`${key}.name`, e.target.value)} />
            <Choice label={`${field.label} ${i + 1}: used`} options={["Y", "N"]} value={value(`${key}.used`)} onPick={(v) => set(`${key}.used`, v)} />
            <Money label={`${field.label} ${i + 1}: cash impact`} value={value(`${key}.cash`)} onType={(v) => set(`${key}.cash`, v)} />
            <input className="input" aria-label={`${field.label} ${i + 1}: notes`} placeholder="Notes" value={value(`${key}.notes`)} onChange={(e) => set(`${key}.notes`, e.target.value)} />
          </div>
        );
      })}
      <div className="wrow wtotal"><span className="wlabel">Total</span><span /><span className="fig">{dollars(planTotal(data, field.key, field.rows))}</span><span /></div>
    </>
  );
}

/** Worked-out figures, so nobody does the sums by hand. */
function Sums({ kind, data }: { kind: Kind; data: Data }) {
  if (kind === "analysis") {
    const ask = number(data["ask.value"]), profit = number(data["ebitda.value"]);
    return <p className="wsums">Ask multiple: <b>{times(ask, profit)}</b> (ask price ÷ EBITDA)</p>;
  }
  if (kind !== "bundle") return null;
  const ask = number(data.ask), profit = number(data.ebitda), goal = number(data.goal);
  const bundle = planTotal(data, "pre", 12), gap = planTotal(data, "gap", 4), post = planTotal(data, "post", 5);
  return (
    <dl className="wsums dfacts">
      <div><dt>Ask multiple</dt><dd className="fig">{times(ask, profit)}</dd></div>
      <div><dt>Goal multiple</dt><dd className="fig">{times(goal, profit)}</dd></div>
      <div><dt>Deal bundle value</dt><dd className="fig">{dollars(bundle)}</dd></div>
      <div><dt>Gap left</dt><dd className="fig">{dollars(goal - bundle)}</dd></div>
      <div><dt>Total gap funded</dt><dd className="fig">{dollars(gap)}</dd></div>
      <div><dt>Post closing cash</dt><dd className="fig">{dollars(post)}</dd></div>
    </dl>
  );
}

export function WorksheetForm({ id, kind, initial, saved, inDrive }: { id: string; kind: Kind; initial: Data; saved: boolean; inDrive: boolean }) {
  const sheet = SHEETS[kind];
  const [data, setData] = useState(initial);
  const [status, setStatus] = useState(saved ? "Saved" : "Filled in from the listing. Not saved yet.");
  const changed = useRef(false);

  useEffect(() => {
    if (!changed.current) return;
    setStatus("Saving…");
    const timer = setTimeout(() => {
      saveWorksheet(id, kind, data).then(() => setStatus("Saved")).catch(() => setStatus("Couldn't save. Check your connection and keep this page open."));
    }, 700);
    return () => clearTimeout(timer);
  }, [data, id, kind]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (status !== "Saved" && changed.current) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [status]);

  const set = (key: string, value: string) => {
    changed.current = true;
    setData((current) => ({ ...current, [key]: value }));
  };

  /** Save what's on screen first, so the Doc never misses the last few seconds of typing. */
  async function toDrive() {
    setStatus("Saving to Drive…");
    try {
      await saveWorksheet(id, kind, data);
      changed.current = false;
      const form = new FormData();
      form.set("id", id);
      form.set("kind", kind);
      await saveWorksheetToDrive(form);
    } catch (e) {
      if (e && typeof e === "object" && "digest" in e && String((e as { digest: unknown }).digest).startsWith("NEXT_REDIRECT")) throw e;
      setStatus("Couldn't save to Drive. Try again in a minute.");
    }
  }

  return (
    <div className="wsheet">
      <div className="wbar noprint">
        <span className="lsub" role="status">{status}</span>
        <span className="actions">
          <button type="button" className="btn" onClick={toDrive}>{inDrive ? "Update the copy in Drive" : "Save to Drive"}</button>
          <button type="button" className="btn" onClick={() => window.print()}>Print or save as PDF</button>
        </span>
      </div>
      <Sums kind={kind} data={data} />
      {sheet.sections.map((section) => (
        <section className="card wsection" key={section.title}>
          <h2>{section.title}</h2>
          {section.heads ? <div className="wrow whead" aria-hidden="true">{section.heads.map((head, i) => <span key={i}>{head}</span>)}</div> : null}
          {section.fields.map((field) => <Input key={field.key} field={field} data={data} set={set} />)}
        </section>
      ))}
    </div>
  );
}
