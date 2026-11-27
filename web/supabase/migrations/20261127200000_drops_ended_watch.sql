-- Price drops and ended listings, noticed by the bots' sync, and "what we look for" rules for new listings.
alter table public.businesses
  add column if not exists previous_price numeric,
  add column if not exists price_dropped_at timestamptz,
  add column if not exists ended_at timestamptz;

-- Filters saved from Find: a new listing that fits one gets a star in Find and a place in Tom's morning email.
create table if not exists public.watch_rules (
  id bigint generated always as identity primary key,
  name text not null,
  filters jsonb not null,
  created_by text,
  created_at timestamptz not null default now()
);
alter table public.watch_rules enable row level security;

-- The Find view lists columns as they were when it was made, so it's made again to carry the new ones.
drop view if exists public.find_list;
create view public.find_list with (security_invoker = true) as
select b.*,
       t.display_name,
       t.archived_at,
       case
         when t.archived_at is not null then 'Archived'
         when t.stage = 'Passed' then 'Passed'
         when t.business_id is not null then 'In pipeline'
         else coalesce(r.mark, 'Not reviewed')
       end as mark
from public.businesses b
left join public.tracking t on t.business_id = b.id
left join public.reviews r on r.business_id = b.id;
