-- When Google stops accepting Tom's Drive connection (it expired or was removed), the website records it, says so
-- on every page, and asks for a reconnect instead of failing with a server error.
alter table public.google_connections add column if not exists broken_at timestamptz;
