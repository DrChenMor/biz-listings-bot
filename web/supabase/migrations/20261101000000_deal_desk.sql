-- The Deal desk app's data. Businesses are copied from the Google Sheet by `python -m bizbot sync-db`.
-- Tracking and activity belong to the app. Only the app's server and the sync use this database, with the
-- service key, so row level security is on with no policies: the public key can read nothing.

create table public.businesses (
  id text primary key,
  kind text not null check (kind in ('sale', 'practice')),
  site text not null,
  status text,
  name text not null,
  summary text,
  types text[] not null default '{}',
  category text,
  suburb text,
  postcode text,
  region text,
  perth boolean not null default false,
  price_text text,
  price numeric,
  turnover numeric,
  profit numeric,
  route text not null,
  tags text[] not null default '{}',
  seller text,
  phone text,
  email text,
  website text,
  address text,
  url text,
  map_url text,
  description text,
  facts jsonb not null default '[]',
  first_seen timestamptz,
  search_text text,
  on_sheet boolean not null default true,
  synced_at timestamptz not null default now()
);

create index businesses_kind on public.businesses (kind);
create index businesses_route on public.businesses (route);
create index businesses_first_seen on public.businesses (first_seen desc nulls last);
create index businesses_types on public.businesses using gin (types);

create table public.tracking (
  business_id text primary key references public.businesses (id),
  stage text not null default 'New',
  next_step text,
  next_due date,
  owner text,
  updated_at timestamptz not null default now()
);

create table public.activity (
  id bigint generated always as identity primary key,
  business_id text not null references public.businesses (id),
  at timestamptz not null default now(),
  who text not null,
  text text not null
);

create index activity_business on public.activity (business_id, at desc);

create table public.site_runs (
  site text primary key,
  started text,
  result text
);

alter table public.businesses enable row level security;
alter table public.tracking enable row level security;
alter table public.activity enable row level security;
alter table public.site_runs enable row level security;
