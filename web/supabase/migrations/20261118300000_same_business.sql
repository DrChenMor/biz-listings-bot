-- The same business listed on more than one site is shown once. same_as points a copy at the listing that is shown;
-- also_on lists the shown listing's copies, as [{"site": ..., "url": ..., "id": ...}].
alter table public.businesses
  add column same_as text,
  add column also_on jsonb not null default '[]';

create index businesses_same_as on public.businesses (same_as) where same_as is not null;
