-- Tom's "Connect Google Drive": lets the website save files into the Acquisitions folders as Tom. The refresh token is
-- encrypted with APP_SECRET before it is stored, and only the service key can read this table.
create table public.google_connections (
  id text primary key check (id = 'drive'),
  email text not null,
  refresh_token text not null,
  connected_by text not null,
  connected_at timestamptz not null default now()
);

alter table public.google_connections enable row level security;

-- The Google Doc each worksheet was last saved to, so saving again updates it instead of making a copy.
alter table public.worksheets add column drive_file_id text;
