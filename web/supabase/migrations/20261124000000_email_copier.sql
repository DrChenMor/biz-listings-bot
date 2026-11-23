-- The email copier: who we talk to for each business, the emails copied from Tom's deals inbox, and the emails
-- it couldn't match yet. The Apps Script in Tom's Google account reads Gmail; the website only stores what it sends.
create table if not exists public.contacts (
  id bigint generated always as identity primary key,
  business_id text not null references public.businesses (id) on delete cascade,
  email text not null,
  name text,
  role text,
  added_by text,
  added_at timestamptz not null default now(),
  unique (business_id, email)
);

-- One row per email per business: a broker's email can belong to two businesses.
create table if not exists public.mail (
  gmail_id text not null,
  business_id text not null references public.businesses (id) on delete cascade,
  thread_id text,
  sent_at timestamptz not null,
  sender text,
  recipients text,
  subject text,
  body text,
  incoming boolean not null default true,
  attachments jsonb not null default '[]',
  saved_at timestamptz not null default now(),
  primary key (gmail_id, business_id)
);
create index if not exists mail_business on public.mail (business_id, sent_at desc);

create table if not exists public.unmatched_mail (
  gmail_id text primary key,
  thread_id text,
  sent_at timestamptz,
  sender text,
  sender_name text,
  subject text,
  snippet text,
  dismissed boolean not null default false,
  seen_at timestamptz not null default now()
);

alter table public.contacts enable row level security;
alter table public.mail enable row level security;
alter table public.unmatched_mail enable row level security;
