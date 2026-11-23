-- What Find lists: every business with its real name, archive flag and review mark, so Find can filter on them.
-- security_invoker keeps the tables' own access rules.
create or replace view public.find_list with (security_invoker = true) as
select b.*,
       t.display_name,
       t.archived_at,
       case
         when t.archived_at is not null then 'Archived'
         when t.business_id is not null then 'In pipeline'
         else coalesce(r.mark, 'Not reviewed')
       end as mark
from public.businesses b
left join public.tracking t on t.business_id = b.id
left join public.reviews r on r.business_id = b.id;
