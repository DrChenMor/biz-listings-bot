-- The business's real name (once the documents arrive), and an archive for businesses that are off the table.
-- Only adds empty columns: every stage, date, card figure and linked folder stays as it is.
-- On tracking, not businesses, because the bots rewrite businesses.name from the listing on every run.
alter table public.tracking
  add column if not exists display_name text,
  add column if not exists archived_at timestamptz,
  add column if not exists archived_by text;
