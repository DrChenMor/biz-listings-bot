-- The broker agent's records. A person queues an enquiry in the app; `python -m bizbot agent-send` and `agent-inbox`
-- do the rest. Like every table here, row level security is on with no policies: only the service key can read.

create table public.enquiries (
  id bigint generated always as identity primary key,
  business_id text not null unique references public.businesses (id),
  status text not null default 'Queued',
  detail text,
  asked_by text,
  message text,
  requested_at timestamptz not null default now(),
  sent_at timestamptz,
  updated_at timestamptz not null default now()
);

create index enquiries_status on public.enquiries (status);

create table public.agent_emails (
  id bigint generated always as identity primary key,
  enquiry_id bigint not null references public.enquiries (id),
  direction text not null check (direction in ('in', 'out')),
  message_id text unique,
  sender text,
  recipient text,
  subject text,
  body text,
  kind text,
  summary text,
  at timestamptz not null default now()
);

create index agent_emails_enquiry on public.agent_emails (enquiry_id, at);

create table public.agent_documents (
  id bigint generated always as identity primary key,
  enquiry_id bigint not null references public.enquiries (id),
  name text not null,
  path text not null,
  kind text not null check (kind in ('nda', 'signed nda', 'document', 'other')),
  at timestamptz not null default now()
);

create index agent_documents_enquiry on public.agent_documents (enquiry_id, at);

create table public.evaluations (
  business_id text primary key references public.businesses (id),
  enquiry_id bigint not null references public.enquiries (id),
  summary jsonb not null,
  model text not null,
  at timestamptz not null default now()
);

alter table public.enquiries enable row level security;
alter table public.agent_emails enable row level security;
alter table public.agent_documents enable row level security;
alter table public.evaluations enable row level security;

insert into storage.buckets (id, name, public) values ('deal-docs', 'deal-docs', false) on conflict (id) do nothing;
