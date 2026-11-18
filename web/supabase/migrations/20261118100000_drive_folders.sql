-- Each pipeline business can be linked to its folder in Tom's Google Drive "Acquisitions" folder.
alter table public.tracking add column drive_folder_id text;
