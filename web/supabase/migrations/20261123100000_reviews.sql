-- Whether Chen or Tom has looked at a listing yet: Seen, Not sure, Interested or Not for us. No row means not reviewed.
-- A business in the pipeline counts as reviewed without a row here. Shared by everyone who signs in.
create table if not exists public.reviews (
  business_id text primary key references public.businesses (id),
  mark text not null,
  marked_by text,
  marked_at timestamptz not null default now()
);
alter table public.reviews enable row level security;
