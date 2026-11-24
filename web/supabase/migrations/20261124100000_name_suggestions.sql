-- Real business names found for free in a pipeline business's Drive folder: from ABN Lookup (an ABN printed in a
-- document) or from the file names. They are only suggestions: Accept puts one on the card, Ignore hides it.
create table if not exists public.name_suggestions (
  id bigint generated always as identity primary key,
  business_id text not null references public.businesses (id) on delete cascade,
  name text not null,
  source text not null,
  evidence text,
  file_id text,
  file_name text,
  abn text,
  status text not null default 'new',
  found_at timestamptz not null default now(),
  unique (business_id, name)
);

-- Which files the name finder has read, so each file is read once (again only when it changes).
create table if not exists public.doc_scans (
  file_id text not null,
  business_id text not null references public.businesses (id) on delete cascade,
  modified_time text,
  abns text[] not null default '{}',
  scanned_at timestamptz not null default now(),
  primary key (file_id, business_id)
);

alter table public.name_suggestions enable row level security;
alter table public.doc_scans enable row level security;
