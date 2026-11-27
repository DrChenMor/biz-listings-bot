-- A log of what happens on the website beyond each business's own history: sign-ins, Drive and email problems, and
-- every server error, with where it happened. Shown on the Log page, for finding out what went wrong and when.
create table if not exists public.app_log (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  who text,
  kind text not null,
  what text not null,
  detail text,
  path text
);
create index if not exists app_log_at on public.app_log (at desc);
alter table public.app_log enable row level security;
