-- keys content system (Supabase project cloudbeds-rm). Applied as migration "keys_content_system".
-- Tables are service-role only (RLS on, no policies); the page talks to edge function keys-content.
--
-- mkt_facts        every product fact a clip may state (price, trial days, features ...)
--                  source 'auto' = synced from system tables (plans, trial_settings) by mkt_sync_facts()
--                  source 'manual' = typed on the content page
-- mkt_fact_changes log of every change to a fact, with how many clips it touched
-- mkt_content      ideas → scripts → clips → posts. fact_snapshot = {fact key: value at the time it was written}
--                  When a fact changes, mkt_check_stale() compares snapshots and flags the clip:
--                  not posted yet → must be rewritten, posted → proposed for deletion.
-- mkt_settings     cadence (clips per month), post times, channels, character names

create table if not exists public.mkt_facts (
  key text primary key,
  label text not null,
  value text not null,
  source text not null default 'manual' check (source in ('auto', 'manual')),
  version int not null default 1,
  updated_at timestamptz not null default now(),
  updated_by text
);

create table if not exists public.mkt_fact_changes (
  id bigserial primary key,
  key text not null,
  label text,
  old_value text,
  new_value text,
  source text,
  changed_by text,
  changed_at timestamptz not null default now(),
  affected int not null default 0
);

create table if not exists public.mkt_settings (
  id int primary key default 1 check (id = 1),
  clips_per_month int not null default 20 check (clips_per_month between 1 and 60),
  post_times text[] not null default '{12:00,19:30}',
  channels text[] not null default '{facebook,instagram,tiktok}',
  avatar_name text not null default 'พี่คีย์',
  mascot_name text not null default 'น้องกุญแจ',
  brief text not null default '',
  updated_at timestamptz not null default now()
);
insert into public.mkt_settings (id) values (1) on conflict do nothing;

create sequence if not exists public.mkt_code_seq;

create table if not exists public.mkt_content (
  id bigserial primary key,
  code text unique not null default ('K' || lpad(nextval('public.mkt_code_seq')::text, 3, '0')),
  status text not null default 'idea'
    check (status in ('idea', 'revise', 'approved', 'rejected', 'producing', 'review', 'scheduled', 'posted', 'removed')),
  pillar text,
  character text check (character in ('avatar', 'mascot', 'both')),
  title text not null,
  hook text,
  script text,
  caption text,
  fact_keys text[] not null default '{}',
  fact_snapshot jsonb not null default '{}',
  stale boolean not null default false,
  stale_reason text,
  stale_at timestamptz,
  planned_for date,
  posted_at timestamptz,
  post_urls jsonb not null default '{}',
  feedback text,
  history jsonb not null default '[]',
  created_by text not null default 'ai',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists mkt_content_status on public.mkt_content (status);
create index if not exists mkt_content_fact_keys on public.mkt_content using gin (fact_keys);

alter table public.mkt_facts enable row level security;
alter table public.mkt_fact_changes enable row level security;
alter table public.mkt_settings enable row level security;
alter table public.mkt_content enable row level security;

-- ---------- stale check: compare each live clip's snapshot with the current facts
create or replace function public.mkt_check_stale(p_keys text[] default null)
returns int language plpgsql security definer set search_path = public as $$
declare
  r record;
  diffs text[];
  n int := 0;
begin
  for r in
    select c.* from mkt_content c
    where c.status not in ('rejected', 'removed')
      and (p_keys is null or c.fact_keys && p_keys)
  loop
    select array_agg(
             coalesce(f.label, s.key) || ': "' || s.value || '" → ' ||
             coalesce('"' || f.value || '"', 'ถูกลบออกจากระบบ')
             order by s.key)
      into diffs
      from jsonb_each_text(r.fact_snapshot) s
      left join mkt_facts f on f.key = s.key
     where f.value is distinct from s.value;

    if diffs is not null then
      if not r.stale or r.stale_reason is distinct from array_to_string(diffs, E'\n') then
        update mkt_content
           set stale = true,
               stale_reason = array_to_string(diffs, E'\n'),
               stale_at = coalesce(case when r.stale then r.stale_at end, now()),
               history = history || jsonb_build_object('at', now(), 'by', 'system', 'what', 'stale', 'note', array_to_string(diffs, ' · ')),
               updated_at = now()
         where id = r.id;
      end if;
      n := n + 1;
    elsif r.stale then
      -- fact changed back to what the clip says: clear the flag
      update mkt_content set stale = false, stale_reason = null, stale_at = null, updated_at = now(),
             history = history || jsonb_build_object('at', now(), 'by', 'system', 'what', 'fresh')
       where id = r.id;
    end if;
  end loop;
  return n;
end $$;

-- ---------- facts: version bump + change log + stale check on every change
create or replace function public.mkt_facts_changed()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'UPDATE' then
    if new.value is not distinct from old.value and new.label is not distinct from old.label then return new; end if;
    if new.value is distinct from old.value then new.version := old.version + 1; end if;
    new.updated_at := now();
  end if;
  return new;
end $$;

create or replace function public.mkt_facts_after()
returns trigger language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if tg_op = 'UPDATE' and new.value is not distinct from old.value then return null; end if;
  n := mkt_check_stale(array[coalesce(new.key, old.key)]);
  insert into mkt_fact_changes (key, label, old_value, new_value, source, changed_by, affected)
  values (coalesce(new.key, old.key), coalesce(new.label, old.label),
          case when tg_op <> 'INSERT' then old.value end,
          case when tg_op <> 'DELETE' then new.value end,
          coalesce(new.source, old.source),
          coalesce(new.updated_by, case when coalesce(new.source, old.source) = 'auto' then 'system' end),
          n);
  return null;
end $$;

drop trigger if exists mkt_facts_before on public.mkt_facts;
create trigger mkt_facts_before before update on public.mkt_facts
  for each row execute function public.mkt_facts_changed();
drop trigger if exists mkt_facts_after on public.mkt_facts;
create trigger mkt_facts_after after insert or update or delete on public.mkt_facts
  for each row execute function public.mkt_facts_after();

-- ---------- auto facts from the keys system tables
create or replace function public.mkt_set_fact(p_key text, p_label text, p_value text)
returns void language sql security definer set search_path = public as $$
  insert into mkt_facts (key, label, value, source, updated_by)
  values (p_key, p_label, p_value, 'auto', 'system')
  on conflict (key) do update
    set label = excluded.label, value = excluded.value, source = 'auto', updated_by = 'system'
    where mkt_facts.value is distinct from excluded.value or mkt_facts.label is distinct from excluded.label;
$$;

create or replace function public.mkt_sync_facts()
returns void language plpgsql security definer set search_path = public as $$
declare p record; t record; keep text[] := '{}';
begin
  for p in select * from plans loop
    if p.active and p.is_public then
      perform mkt_set_fact('plan_' || p.code || '_monthly', 'ราคา ' || p.name || ' รายเดือน',
                           to_char(p.price_monthly, 'FM999,999,990') || ' บาท/เดือน');
      perform mkt_set_fact('plan_' || p.code || '_yearly', 'ราคา ' || p.name || ' รายปี',
                           to_char(p.price_yearly, 'FM999,999,990') || ' บาท/ปี');
      perform mkt_set_fact('plan_' || p.code || '_desc', 'แพ็กเกจ ' || p.name || ' ได้อะไร', coalesce(p.description, ''));
      perform mkt_set_fact('plan_' || p.code || '_users', 'จำนวนผู้ใช้ ' || p.name,
                           coalesce((p.limits->>'max_users') || ' คน', 'ไม่จำกัด'));
      perform mkt_set_fact('plan_' || p.code || '_competitors', 'จำนวนคู่แข่งที่ติดตาม ' || p.name,
                           case when coalesce((p.limits->>'max_competitors')::int, 0) = 0 then 'ไม่มี'
                                else (p.limits->>'max_competitors') || ' โรงแรม' end);
      keep := keep || array['plan_' || p.code || '_monthly', 'plan_' || p.code || '_yearly', 'plan_' || p.code || '_desc',
                            'plan_' || p.code || '_users', 'plan_' || p.code || '_competitors'];
    end if;
  end loop;

  select * into t from trial_settings order by id limit 1;
  if found then
    perform mkt_set_fact('trial_days', 'ทดลองใช้ฟรี', t.trial_days || ' วัน');
    perform mkt_set_fact('comp_lead_points', 'ส่องราคาคู่แข่งล่วงหน้า', replace(t.lead_points, ',', ', ') || ' วัน');
    keep := keep || array['trial_days', 'comp_lead_points'];
  end if;

  -- plan removed or hidden: mark its facts retired (clips quoting them get flagged)
  update mkt_facts set value = 'ยกเลิกแล้ว (ไม่มีขายแล้ว)', updated_by = 'system'
   where source = 'auto' and key like 'plan\_%' and not (key = any(keep)) and value <> 'ยกเลิกแล้ว (ไม่มีขายแล้ว)';
end $$;

create or replace function public.mkt_sync_trigger()
returns trigger language plpgsql security definer set search_path = public as $$
begin perform mkt_sync_facts(); return null; end $$;

drop trigger if exists mkt_sync_plans on public.plans;
create trigger mkt_sync_plans after insert or update or delete on public.plans
  for each statement execute function public.mkt_sync_trigger();
drop trigger if exists mkt_sync_trial on public.trial_settings;
create trigger mkt_sync_trial after insert or update or delete on public.trial_settings
  for each statement execute function public.mkt_sync_trigger();

-- ---------- helpers for the content generator (scheduled Claude task) and the page
create or replace function public.mkt_snapshot(p_keys text[])
returns jsonb language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_object_agg(key, value), '{}'::jsonb) from mkt_facts where key = any(p_keys);
$$;

-- add a new idea; the snapshot is taken from the current facts so it is never stale at birth
create or replace function public.mkt_add_idea(p_title text, p_pillar text, p_character text, p_hook text,
                                               p_script text, p_caption text, p_fact_keys text[])
returns text language plpgsql security definer set search_path = public as $$
declare bad text[]; c text;
begin
  select array_agg(k) into bad from unnest(p_fact_keys) k where not exists (select 1 from mkt_facts f where f.key = k);
  if bad is not null then raise exception 'unknown fact keys: %', bad; end if;
  insert into mkt_content (title, pillar, character, hook, script, caption, fact_keys, fact_snapshot, history)
  values (p_title, p_pillar, p_character, p_hook, p_script, p_caption, p_fact_keys, mkt_snapshot(p_fact_keys),
          jsonb_build_array(jsonb_build_object('at', now(), 'by', 'ai', 'what', 'idea')))
  returning code into c;
  return c;
end $$;

-- rewrite a clip with current facts (after a fact change or "ขอแก้"); goes back to the approve queue
create or replace function public.mkt_revise(p_code text, p_title text, p_hook text, p_script text,
                                             p_caption text, p_fact_keys text[], p_note text default null)
returns void language plpgsql security definer set search_path = public as $$
declare bad text[];
begin
  select array_agg(k) into bad from unnest(p_fact_keys) k where not exists (select 1 from mkt_facts f where f.key = k);
  if bad is not null then raise exception 'unknown fact keys: %', bad; end if;
  update mkt_content
     set title = p_title, hook = p_hook, script = p_script, caption = p_caption,
         fact_keys = p_fact_keys, fact_snapshot = mkt_snapshot(p_fact_keys),
         stale = false, stale_reason = null, stale_at = null,
         status = 'idea', feedback = null, updated_at = now(),
         history = history || jsonb_build_object('at', now(), 'by', 'ai', 'what', 'revised', 'note', p_note)
   where code = p_code and status in ('idea', 'revise', 'approved', 'producing', 'review', 'scheduled');
  if not found then raise exception 'clip % cannot be revised (posted clips are replaced by a new idea)', p_code; end if;
end $$;

-- next free posting day for the configured cadence (Bangkok dates)
create or replace function public.mkt_next_slot()
returns date language plpgsql stable security definer set search_path = public as $$
declare per int; gap numeric; last date; today date := (now() at time zone 'Asia/Bangkok')::date; d date;
begin
  select clips_per_month into per from mkt_settings where id = 1;
  gap := 30.0 / greatest(per, 1);
  select max(planned_for) into last from mkt_content where status in ('approved', 'producing', 'review', 'scheduled');
  if last is null or last < today then return today + 1; end if;
  d := last + greatest(floor(gap)::int, 1);
  -- 20+ a month: weekdays only (skip Sat/Sun)
  if per between 20 and 23 then
    while extract(isodow from d) > 5 loop d := d + 1; end loop;
  end if;
  return d;
end $$;

revoke all on function public.mkt_check_stale(text[]), public.mkt_sync_facts(), public.mkt_set_fact(text, text, text),
  public.mkt_add_idea(text, text, text, text, text, text, text[]), public.mkt_revise(text, text, text, text, text, text[], text),
  public.mkt_snapshot(text[]), public.mkt_next_slot() from public, anon, authenticated;

-- safety net: re-sync and re-check once a day (07:10 Bangkok)
select cron.schedule('keys-content-facts-daily', '10 0 * * *', $$select public.mkt_sync_facts(); select public.mkt_check_stale();$$);
select public.mkt_sync_facts();
