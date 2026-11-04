-- Initial persistence schema. Access is intended through the Python API only.
-- Never expose SUPABASE_SERVICE_ROLE_KEY in frontend environment variables.

create extension if not exists pgcrypto;

create table if not exists public.app_users (
  id uuid primary key default gen_random_uuid(),
  username text not null unique,
  password_hash text not null,
  created_at timestamptz not null default now(),
  disabled_at timestamptz
);

create table if not exists public.dashboard_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.app_users(id) on delete cascade,
  token_hash text not null unique,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  revoked_at timestamptz
);

create table if not exists public.game_accounts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.app_users(id) on delete cascade,
  label text not null,
  game_username text,
  session_ciphertext text,
  session_iv text,
  session_tag text,
  session_expires_at timestamptz,
  status text not null default 'needs_login'
    check (status in ('needs_login', 'active', 'expired', 'error')),
  automation_data jsonb not null default '{}'::jsonb,
  enabled boolean not null default false,
  next_run_at timestamptz,
  lease_until timestamptz,
  state_snapshot jsonb,
  last_tick_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, game_username)
);

-- Upgrade compatibility for an existing single-owner schema (which used
-- owner_id and may already contain accounts). Do not drop existing sessions.
alter table public.game_accounts
  add column if not exists user_id uuid references public.app_users(id) on delete cascade,
  add column if not exists label text not null default 'Game account',
  add column if not exists game_username text,
  add column if not exists session_ciphertext text,
  add column if not exists session_iv text,
  add column if not exists session_tag text,
  add column if not exists session_expires_at timestamptz,
  add column if not exists status text not null default 'active',
  add column if not exists automation_data jsonb not null default '{}'::jsonb,
  add column if not exists enabled boolean not null default false,
  add column if not exists next_run_at timestamptz,
  add column if not exists lease_until timestamptz,
  add column if not exists state_snapshot jsonb,
  add column if not exists last_tick_at timestamptz,
  add column if not exists last_error text,
  add column if not exists config jsonb not null default '{}'::jsonb,
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();

create table if not exists public.account_configs (
  account_id uuid primary key references public.game_accounts(id) on delete cascade,
  config jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- Preserve config from the previous schema, where it lived on game_accounts.
insert into public.account_configs (account_id, config)
select id, coalesce(config, '{}'::jsonb)
from public.game_accounts
on conflict (account_id) do nothing;

create table if not exists public.automation_runs (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.game_accounts(id) on delete cascade,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'partial', 'failed')),
  started_at timestamptz,
  finished_at timestamptz,
  cursor jsonb not null default '{}'::jsonb,
  error_summary text,
  created_at timestamptz not null default now()
);

create table if not exists public.activity_logs (
  id bigint generated always as identity primary key,
  account_id uuid not null references public.game_accounts(id) on delete cascade,
  run_id uuid references public.automation_runs(id) on delete set null,
  level text not null default 'info'
    check (level in ('info', 'success', 'warning', 'error')),
  action text not null,
  message text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists game_accounts_user_id_idx on public.game_accounts(user_id);
create unique index if not exists game_accounts_user_username_uidx
  on public.game_accounts(user_id, game_username)
  where user_id is not null and game_username is not null;
create index if not exists game_accounts_due_idx on public.game_accounts(next_run_at)
  where enabled = true;
create index if not exists dashboard_sessions_user_id_idx on public.dashboard_sessions(user_id);
create index if not exists activity_logs_account_created_idx on public.activity_logs(account_id, created_at desc);
create index if not exists automation_runs_queue_idx on public.automation_runs(status, created_at)
  where status in ('queued', 'running');

-- Enable RLS as defense in depth. The service-role key bypasses RLS, so every
-- backend query must still constrain records by authenticated user ownership.
alter table public.app_users enable row level security;
alter table public.dashboard_sessions enable row level security;
alter table public.game_accounts enable row level security;
alter table public.account_configs enable row level security;
alter table public.automation_runs enable row level security;
alter table public.activity_logs enable row level security;
