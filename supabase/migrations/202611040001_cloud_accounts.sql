-- Cloud account storage. Game session cookies are encrypted by the API before
-- being written; never store plaintext game credentials or session cookies.
create table if not exists public.game_accounts (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  label text not null check (char_length(label) between 1 and 48),
  game_username text not null,
  session_ciphertext text not null,
  session_iv text not null,
  session_tag text not null,
  config jsonb not null default '{}'::jsonb,
  automation_data jsonb not null default '{}'::jsonb,
  enabled boolean not null default false,
  next_run_at timestamptz,
  lease_until timestamptz,
  state_snapshot jsonb,
  last_tick_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (owner_id, game_username)
);

create index if not exists game_accounts_due_idx
  on public.game_accounts (next_run_at)
  where enabled = true;

create table if not exists public.automation_logs (
  id bigint generated always as identity primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  account_id uuid not null references public.game_accounts(id) on delete cascade,
  level text not null check (level in ('info', 'success', 'warn', 'error')),
  message text not null,
  detail text,
  created_at timestamptz not null default now()
);

create index if not exists automation_logs_account_idx
  on public.automation_logs (account_id, created_at desc);

alter table public.game_accounts enable row level security;
alter table public.automation_logs enable row level security;

create policy "owners manage their game accounts"
  on public.game_accounts for all
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

create policy "owners read their automation logs"
  on public.automation_logs for select
  using (auth.uid() = owner_id);

-- The Vercel backend uses the service-role key for atomic leasing and cron work.
-- The key must only exist in Vercel server-side environment variables.
