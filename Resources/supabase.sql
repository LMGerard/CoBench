-- CoBench: locks of a FreeCAD project in Supabase.
-- Run once in Supabase > SQL Editor > New query > Run.
-- The part files stay in your shared folder; only these two small tables live here.

create table if not exists public.cobench_locks (
    project   text        not null,              -- id of the CoBench project (cobench.json)
    part      text        not null,              -- path of the part inside the project
    user_name text        not null,
    host      text        not null,
    pid       integer     not null default 0,
    session   text        not null,
    app       text        not null default '',
    since     timestamptz not null default now(),
    primary key (project, part)                  -- one lock per part: the database refuses a second one
);

create table if not exists public.cobench_versions (
    project  text        not null,
    part     text        not null,
    sha1     text        not null,               -- fingerprint of the file as last saved
    size     bigint      not null default 0,
    saved_by text        not null default '',
    saved_at timestamptz not null default now(),
    primary key (project, part)
);

-- Keep saved_at up to date when a version is replaced.
create or replace function public.cobench_touch() returns trigger
language plpgsql set search_path = '' as $$
begin
    new.saved_at := now();
    return new;
end $$;

drop trigger if exists cobench_versions_touch on public.cobench_versions;
create trigger cobench_versions_touch before update on public.cobench_versions
    for each row execute function public.cobench_touch();

-- The public (anon / publishable) key may read and write these two tables, and nothing else.
alter table public.cobench_locks    enable row level security;
alter table public.cobench_versions enable row level security;

drop policy if exists cobench_locks_all on public.cobench_locks;
create policy cobench_locks_all on public.cobench_locks
    for all to anon, authenticated using (true) with check (true);

drop policy if exists cobench_versions_all on public.cobench_versions;
create policy cobench_versions_all on public.cobench_versions
    for all to anon, authenticated using (true) with check (true);

grant select, insert, update, delete on public.cobench_locks    to anon, authenticated;
grant select, insert, update, delete on public.cobench_versions to anon, authenticated;

-- Optional (CoBench 0.5): the copy of the files watched on the server.
-- server/cobench_scanner.py runs next to the reference copy of the project (for example on the
-- Nextcloud server) and writes the fingerprint of every part here; each FreeCAD compares it with
-- its own copy to tell a part that does not arrive, or does not leave, through the sync.
-- Running this part again on an existing database is safe.
create table if not exists public.cobench_projects (
    project     text        primary key,
    min_version text        not null default '',  -- older CoBench versions may not lock parts
    files_rev   bigint      not null default 0,   -- increased by the scanner when a file changes
    scanned_at  timestamptz,                      -- heartbeat of the scanner
    scanner     text        not null default ''
);

create table if not exists public.cobench_server_files (
    project text        not null,
    part    text        not null,                 -- path inside the project, as on the server
    sha1    text        not null,
    size    bigint      not null default 0,
    mtime   double precision not null default 0,  -- seconds since 1970 on the server
    primary key (project, part)
);

-- Everybody reads; only the scanner writes, with the service_role key (never put it in cobench.json).
alter table public.cobench_projects     enable row level security;
alter table public.cobench_server_files enable row level security;

drop policy if exists cobench_projects_read on public.cobench_projects;
create policy cobench_projects_read on public.cobench_projects
    for select to anon, authenticated using (true);

drop policy if exists cobench_server_files_read on public.cobench_server_files;
create policy cobench_server_files_read on public.cobench_server_files
    for select to anon, authenticated using (true);

grant select on public.cobench_projects     to anon, authenticated;
grant select on public.cobench_server_files to anon, authenticated;
grant select, insert, update, delete on public.cobench_projects     to service_role;
grant select, insert, update, delete on public.cobench_server_files to service_role;
