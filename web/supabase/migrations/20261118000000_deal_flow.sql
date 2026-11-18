-- The deal flow from the Deal desk notebook page: new stages, the facts each pipeline card shows, the dates a business was
-- approached and followed up, and the three worksheets (Deal Review, Deal Analysis, Deal Bundle) for each business.

alter table public.tracking
  add column location text,
  add column product text,
  add column selling_reason text,
  add column asking_price numeric,
  add column turnover numeric,
  add column expenses numeric,
  add column profit numeric,
  add column under_management text,
  add column approached_on date,
  add column followed_up_on date;

-- When each business was first approached, from its history.
update public.tracking t set approached_on = (
  select min(a.at)::date from public.activity a
  where a.business_id = t.business_id and a.text in ('Moved to Approaching', 'Moved to Talking', 'Asked the agent to send the first enquiry')
);

update public.tracking set stage = case stage
  when 'New' then 'Shortlist'
  when 'Researching' then 'Shortlist'
  when 'Approaching' then 'Approached'
  when 'Talking' then 'Approached'
  when 'NDA and numbers' then 'Documents in'
  when 'Offer' then 'Pitch / offer'
  else stage end;

alter table public.tracking alter column stage set default 'Shortlist';

create table public.worksheets (
  business_id text not null references public.businesses (id),
  kind text not null check (kind in ('review', 'analysis', 'bundle')),
  data jsonb not null default '{}',
  updated_by text,
  updated_at timestamptz not null default now(),
  primary key (business_id, kind)
);

alter table public.worksheets enable row level security;
