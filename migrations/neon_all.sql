-- ============================================================================
-- Leadaro voice-agents — full schema for Neon (Postgres).
-- Paste this whole script into the Neon SQL Editor and run once on a fresh DB.
-- Concatenation of migrations 001 -> 002 -> 003 -> 004, in order.
-- 001 is base schema (CREATE TYPE/TABLE, first run only); 002-004 are idempotent.
-- ============================================================================


-- ─────────────────────────────────────────────────────────────────────────
-- migrations/001_init.sql
-- ─────────────────────────────────────────────────────────────────────────
-- Leadaro Outreach — initial schema
-- One engine, two modes. `campaigns.mode` is the only branch between
-- Call Outreach and Voice Outreach.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── enums ────────────────────────────────────────────────────────────────────

CREATE TYPE campaign_mode     AS ENUM ('voice', 'call');
CREATE TYPE campaign_status   AS ENUM ('draft','scheduled','active','paused','completed','archived');
CREATE TYPE voice_type        AS ENUM ('ai','human','hybrid');
CREATE TYPE schedule_mode     AS ENUM ('immediate','one_time','recurring','drip','behavior','workflow');
CREATE TYPE priority          AS ENUM ('low','normal','high','urgent');
CREATE TYPE user_role         AS ENUM ('admin','manager','sales_rep','recruiter','campaign_operator','analyst','viewer');
CREATE TYPE lead_state        AS ENUM ('pending','queued','dialing','in_progress','completed','failed','unreachable','suppressed');
CREATE TYPE call_direction    AS ENUM ('outbound','inbound');
CREATE TYPE answered_by       AS ENUM ('human','machine','unknown');
CREATE TYPE lead_tier         AS ENUM ('hot','warm','scrap');
CREATE TYPE job_status        AS ENUM ('pending','running','done','failed');

-- Call outcomes: union of both FRDs' disposition lists.
CREATE TYPE call_outcome AS ENUM (
  'interested','very_interested','qualified','disqualified','maybe',
  'not_interested','no_budget','callback','meeting_scheduled','booked_demo',
  'wrong_contact','wrong_number','do_not_call','competitor','no_answer',
  'voicemail','busy','failed','transferred','disconnected','spam'
);

-- Intents the live model can emit (FRD "AI Intent Detection" + supported responses).
CREATE TYPE turn_intent AS ENUM (
  'interested','price_inquiry','more_info','book_demo','book_meeting','support',
  'complaint','objection','not_interested','wrong_number','spam','call_later',
  'busy','speak_to_human','language_switch','voicemail','neutral','unclear'
);

CREATE TYPE turn_emotion AS ENUM (
  'friendly','professional','confident','energetic','calm','urgent','happy','empathetic'
);
CREATE TYPE turn_speed AS ENUM ('slow','normal','fast');
CREATE TYPE turn_pitch AS ENUM ('low','medium','high');

CREATE TYPE next_action AS ENUM (
  'continue','handle_objection','explain_detail','book_meeting','transfer_human',
  'schedule_callback','close_positive','close_negative','leave_voicemail'
);

-- ── tenancy ──────────────────────────────────────────────────────────────────

CREATE TABLE organizations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  timezone    text NOT NULL DEFAULT 'UTC',
  settings    jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  email         text NOT NULL,
  name          text NOT NULL,
  password_hash text NOT NULL,
  role          user_role NOT NULL DEFAULT 'viewer',
  department    text,
  phone         text,
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_org_email_idx ON users (org_id, lower(email));

-- ── phone numbers / caller IDs ───────────────────────────────────────────────

CREATE TABLE phone_numbers (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  e164        text NOT NULL,
  label       text,
  provider    text NOT NULL DEFAULT 'plivo',
  country     text,
  inbound_campaign_id uuid,      -- FK added after campaigns exists
  -- Optional DTMF keypad menu played to inbound callers before the AI takes
  -- over. Shape: {enabled, greeting, timeout_seconds, invalid_message,
  --               options:[{digit, label, action, target, message}]}
  ivr_menu    jsonb NOT NULL DEFAULT '{}',
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX phone_numbers_org_e164_idx ON phone_numbers (org_id, e164);

-- ── voices ───────────────────────────────────────────────────────────────────

CREATE TABLE voices (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid REFERENCES organizations(id) ON DELETE CASCADE,  -- NULL = stock voice
  name         text NOT NULL,
  provider     text NOT NULL DEFAULT 'cartesia',
  provider_id  text NOT NULL,
  gender       text,
  accent       text,
  language     text NOT NULL DEFAULT 'en',
  age          text,
  tone         text,          -- professional | sales | support | recruitment | healthcare | finance
  vertical     text,
  is_clone     boolean NOT NULL DEFAULT false,
  sample_url   text,
  rating       numeric(2,1),
  created_at   timestamptz NOT NULL DEFAULT now()
);
-- A provider voice id is unique per org. Stock voices (org_id IS NULL) sit
-- outside any org, so the org cascade never removes them — without this,
-- re-running the seed silently duplicates the whole gallery.
CREATE UNIQUE INDEX voices_provider_uniq
  ON voices (provider, provider_id, COALESCE(org_id, '00000000-0000-0000-0000-000000000000'::uuid));

-- ── campaigns ────────────────────────────────────────────────────────────────

CREATE TABLE campaigns (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  mode            campaign_mode NOT NULL,
  name            text NOT NULL,
  description     text,
  type            text,                 -- cold_calling | demo_booking | renewal_reminder | ...
  goal            text,
  status          campaign_status NOT NULL DEFAULT 'draft',
  owner_id        uuid REFERENCES users(id) ON DELETE SET NULL,
  department      text,
  priority        priority NOT NULL DEFAULT 'normal',
  tags            text[] NOT NULL DEFAULT '{}',
  timezone        text NOT NULL DEFAULT 'UTC',
  country         text,
  language        text NOT NULL DEFAULT 'en',
  caller_number_id uuid REFERENCES phone_numbers(id) ON DELETE SET NULL,
  caller_id       text,

  voice_type      voice_type NOT NULL DEFAULT 'ai',
  voice_id        uuid REFERENCES voices(id) ON DELETE SET NULL,
  -- speed, pitch, emotion, energy, pause_length, breathing, background_music,
  -- noise_reduction, voice_enhancement
  voice_config    jsonb NOT NULL DEFAULT '{}',

  -- greeting, introduction, pain_point, offer, cta, objection_handling, closing,
  -- thank_you, voicemail, fallback, transfer, knowledge_base, variables[]
  script          jsonb NOT NULL DEFAULT '{}',

  -- conversation node graph (call mode); {nodes:[], edges:[]}
  flow            jsonb NOT NULL DEFAULT '{}',

  -- retry_attempts, retry_delay_minutes, max_duration_sec, voicemail_detection,
  -- leave_voicemail, recording, whisper, monitoring, live_transfer
  settings        jsonb NOT NULL DEFAULT '{}',

  -- consent, dnd_check, gdpr, tcpa, ccpa, recording_notice, regional_restrictions
  compliance      jsonb NOT NULL DEFAULT '{}',

  schedule_mode   schedule_mode NOT NULL DEFAULT 'immediate',
  start_date      timestamptz,
  end_date        timestamptz,
  business_hours  jsonb NOT NULL DEFAULT '{"start":"09:00","end":"18:00"}',
  weekdays_only   boolean NOT NULL DEFAULT true,
  weekends_only   boolean NOT NULL DEFAULT false,
  holiday_rules   jsonb NOT NULL DEFAULT '{}',
  recurrence      jsonb NOT NULL DEFAULT '{}',
  max_daily_calls int,
  concurrent_calls int NOT NULL DEFAULT 5,
  calls_per_minute int NOT NULL DEFAULT 10,
  queue_size      int,
  warmup_mode     boolean NOT NULL DEFAULT false,

  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  archived_at     timestamptz
);
CREATE INDEX campaigns_org_mode_idx ON campaigns (org_id, mode, status);

ALTER TABLE phone_numbers
  ADD CONSTRAINT phone_numbers_inbound_campaign_fk
  FOREIGN KEY (inbound_campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL;

-- ── leads ────────────────────────────────────────────────────────────────────

CREATE TABLE leads (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  first_name    text,
  last_name     text,
  phone         text NOT NULL,            -- E.164
  email         text,
  company       text,
  designation   text,
  industry      text,
  city          text,
  country       text,
  website       text,
  source        text,                     -- csv | crm | apollo | linkedin | website | manual | api
  lead_score    int NOT NULL DEFAULT 0,
  intent_score  int NOT NULL DEFAULT 0,
  pipeline_stage text,
  tier          lead_tier,
  tags          text[] NOT NULL DEFAULT '{}',
  custom_fields jsonb NOT NULL DEFAULT '{}',
  crm_id        text,
  last_contacted_at timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX leads_org_phone_idx ON leads (org_id, phone);
CREATE INDEX leads_org_score_idx ON leads (org_id, lead_score DESC);

CREATE TABLE campaign_leads (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id     uuid NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  lead_id         uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  state           lead_state NOT NULL DEFAULT 'pending',
  attempts        int NOT NULL DEFAULT 0,
  next_attempt_at timestamptz,
  last_outcome    call_outcome,
  suppressed_reason text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX campaign_leads_uniq ON campaign_leads (campaign_id, lead_id);
-- The dialer's hot path: due work for a campaign, oldest first.
CREATE INDEX campaign_leads_due_idx
  ON campaign_leads (campaign_id, state, next_attempt_at)
  WHERE state IN ('pending','queued');

-- ── calls & transcript ───────────────────────────────────────────────────────

CREATE TABLE calls (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id            uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  campaign_id       uuid REFERENCES campaigns(id) ON DELETE SET NULL,
  campaign_lead_id  uuid REFERENCES campaign_leads(id) ON DELETE SET NULL,
  lead_id           uuid REFERENCES leads(id) ON DELETE SET NULL,
  direction         call_direction NOT NULL DEFAULT 'outbound',
  provider_call_id  text,
  room_name         text,
  from_number       text,
  to_number         text,
  status            text NOT NULL DEFAULT 'initiated',  -- initiated|ringing|connected|completed|failed
  answered_by       answered_by NOT NULL DEFAULT 'unknown',
  outcome           call_outcome,
  started_at        timestamptz NOT NULL DEFAULT now(),
  answered_at       timestamptz,
  ended_at          timestamptz,
  duration_sec      int,
  talk_time_sec     int,
  ai_speaking_sec   int,
  recording_url     text,
  transferred_to    uuid REFERENCES users(id) ON DELETE SET NULL,
  cost_usd          numeric(10,4),
  error             text,
  meta              jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX calls_campaign_started_idx ON calls (campaign_id, started_at DESC);
CREATE INDEX calls_org_started_idx ON calls (org_id, started_at DESC);
CREATE INDEX calls_lead_idx ON calls (lead_id, started_at DESC);

CREATE TABLE turns (
  id          bigserial PRIMARY KEY,
  call_id     uuid NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
  -- Denormalised from calls. Carries the tenant into the NOTIFY payload so the
  -- SSE fan-out can filter without a per-event lookup, and lets the latency
  -- percentiles run without joining calls.
  org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  seq         int NOT NULL,
  role        text NOT NULL,               -- 'agent' | 'lead'
  text        text NOT NULL,
  intent      turn_intent,
  sentiment   real,                        -- -1.0 .. 1.0
  emotion     turn_emotion,
  speed       turn_speed,
  pitch       turn_pitch,
  action      next_action,
  -- latency split, for the primary success metric
  stt_ms      int,
  llm_ms      int,
  tts_ms      int,
  total_ms    int,
  cache_read_tokens int,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX turns_call_seq_idx ON turns (call_id, seq);
CREATE INDEX turns_org_time_idx ON turns (org_id, created_at DESC);

CREATE TABLE call_summaries (
  call_id       uuid PRIMARY KEY REFERENCES calls(id) ON DELETE CASCADE,
  summary       text,
  key_points    text[] NOT NULL DEFAULT '{}',
  action_items  text[] NOT NULL DEFAULT '{}',
  next_steps    text,
  pain_points   text[] NOT NULL DEFAULT '{}',
  budget        text,
  timeline      text,
  sentiment_avg real,
  lead_tier     lead_tier,
  qualification_score int,
  followup_recommendation text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- ── meetings & follow-ups ────────────────────────────────────────────────────

CREATE TABLE meetings (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  lead_id       uuid REFERENCES leads(id) ON DELETE SET NULL,
  call_id       uuid REFERENCES calls(id) ON DELETE SET NULL,
  assigned_to   uuid REFERENCES users(id) ON DELETE SET NULL,
  provider      text NOT NULL DEFAULT 'google',
  external_id   text,
  starts_at     timestamptz NOT NULL,
  ends_at       timestamptz NOT NULL,
  timezone      text NOT NULL DEFAULT 'UTC',
  join_url      text,
  status        text NOT NULL DEFAULT 'scheduled',
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE followups (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  lead_id     uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  call_id     uuid REFERENCES calls(id) ON DELETE SET NULL,
  channel     text NOT NULL,              -- email|sms|whatsapp|linkedin|call|task
  due_at      timestamptz NOT NULL,
  payload     jsonb NOT NULL DEFAULT '{}',
  status      text NOT NULL DEFAULT 'pending',
  reason      text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX followups_due_idx ON followups (status, due_at);

-- ── smart routing (call mode) ────────────────────────────────────────────────

CREATE TABLE routing_rules (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  campaign_id  uuid REFERENCES campaigns(id) ON DELETE CASCADE,
  name         text NOT NULL,
  position     int NOT NULL DEFAULT 0,
  -- {signal:'lead_score', op:'gt', value:80}
  conditions   jsonb NOT NULL DEFAULT '[]',
  -- {type:'sales_rep'|'ai_voice'|'support'|'recruiter'|'manager'|'regional'|'partner'|'queue', target:...}
  destination  jsonb NOT NULL DEFAULT '{}',
  is_active    boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX routing_rules_order_idx ON routing_rules (campaign_id, position);

-- ── automation ───────────────────────────────────────────────────────────────

CREATE TABLE automation_rules (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  campaign_id  uuid REFERENCES campaigns(id) ON DELETE CASCADE,
  name         text NOT NULL,
  trigger      text NOT NULL,             -- outcome:interested | outcome:busy | outcome:voicemail | ...
  actions      jsonb NOT NULL DEFAULT '[]',
  is_active    boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ── compliance ───────────────────────────────────────────────────────────────

CREATE TABLE suppression_list (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  phone       text NOT NULL,
  kind        text NOT NULL DEFAULT 'dnc',   -- dnc | blacklist | opt_out
  reason      text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX suppression_org_phone_kind_idx ON suppression_list (org_id, phone, kind);

CREATE TABLE consents (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  lead_id     uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  kind        text NOT NULL,                 -- calling | recording
  granted     boolean NOT NULL,
  source      text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
  id          bigserial PRIMARY KEY,
  org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  actor_id    uuid REFERENCES users(id) ON DELETE SET NULL,
  action      text NOT NULL,
  entity      text,
  entity_id   text,
  detail      jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_org_time_idx ON audit_log (org_id, created_at DESC);

-- ── integrations & notifications ─────────────────────────────────────────────

CREATE TABLE integrations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  provider    text NOT NULL,               -- google_calendar|hubspot|salesforce|zoho|slack|teams|webhook
  config      jsonb NOT NULL DEFAULT '{}', -- non-secret config
  secrets     jsonb NOT NULL DEFAULT '{}', -- tokens; encrypted at rest by the app layer
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX integrations_org_provider_idx ON integrations (org_id, provider);

CREATE TABLE notifications (
  id          bigserial PRIMARY KEY,
  org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id     uuid REFERENCES users(id) ON DELETE CASCADE,
  kind        text NOT NULL,
  title       text NOT NULL,
  body        text,
  link        text,
  read_at     timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_user_idx ON notifications (user_id, created_at DESC);

-- ── job queue (Postgres-as-broker; no Redis until throughput demands it) ──────

CREATE TABLE jobs (
  id          bigserial PRIMARY KEY,
  kind        text NOT NULL,
  payload     jsonb NOT NULL DEFAULT '{}',
  run_at      timestamptz NOT NULL DEFAULT now(),
  status      job_status NOT NULL DEFAULT 'pending',
  attempts    int NOT NULL DEFAULT 0,
  last_error  text,
  locked_at   timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX jobs_due_idx ON jobs (status, run_at) WHERE status = 'pending';

-- ── realtime bus: NOTIFY on call/turn changes; API relays to SSE ─────────────

-- One function for every table. Reading fields off to_jsonb(NEW) rather than
-- NEW.<field> keeps it table-agnostic: a missing key yields NULL instead of
-- "record NEW has no field", which is what a direct NEW.call_id would raise
-- when the trigger fires on `calls`.
CREATE OR REPLACE FUNCTION notify_change() RETURNS trigger AS $$
DECLARE j jsonb := to_jsonb(NEW);
BEGIN
  PERFORM pg_notify('leadaro_events', json_build_object(
    'table',       TG_TABLE_NAME,
    'op',          TG_OP,
    'id',          j->>'id',
    'org_id',      j->>'org_id',
    'campaign_id', j->>'campaign_id',
    'call_id',     j->>'call_id',
    'status',      j->>'status',
    'outcome',     j->>'outcome'
  )::text);
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER calls_notify AFTER INSERT OR UPDATE ON calls
  FOR EACH ROW EXECUTE FUNCTION notify_change();
CREATE TRIGGER turns_notify AFTER INSERT ON turns
  FOR EACH ROW EXECUTE FUNCTION notify_change();

-- ─────────────────────────────────────────────────────────────────────────
-- migrations/002_ivr_menu.sql
-- ─────────────────────────────────────────────────────────────────────────
-- Adds the DTMF keypad menu to existing databases.
-- 001_init.sql already carries this column for fresh installs; this migration
-- exists so a running database can be upgraded without a reseed.
ALTER TABLE phone_numbers
  ADD COLUMN IF NOT EXISTS ivr_menu jsonb NOT NULL DEFAULT '{}';

-- ─────────────────────────────────────────────────────────────────────────
-- migrations/003_directive_enum.sql
-- ─────────────────────────────────────────────────────────────────────────
-- turns.action records what the RULES engine decided, not what the model
-- suggested. Those are two different vocabularies: the model emits NextAction
-- (9 values, already present), while rules.decide() returns a Directive, whose
-- threshold outcomes had no matching enum labels.
--
-- Consequence before this migration: every turn where a deterministic FRD rule
-- fired — negative streak, silence x2, unclear x2, positive 8+, neutral
-- flatline — failed to insert with "invalid input value for enum next_action",
-- which killed the agent task and dropped the live call. Only the five
-- pass-through directives could ever be saved.
--
-- Observed on the first live call: the model returned exit_polite, the insert
-- threw, and the caller's last utterance went unanswered.

ALTER TYPE next_action ADD VALUE IF NOT EXISTS 'exit_polite';
ALTER TYPE next_action ADD VALUE IF NOT EXISTS 'exit_apologetic';
ALTER TYPE next_action ADD VALUE IF NOT EXISTS 'offer_callback';
ALTER TYPE next_action ADD VALUE IF NOT EXISTS 'push_for_meeting';
ALTER TYPE next_action ADD VALUE IF NOT EXISTS 'shorten_and_ask';

-- ─────────────────────────────────────────────────────────────────────────
-- migrations/004_after_call_features.sql
-- ─────────────────────────────────────────────────────────────────────────
-- Feature-timing split (FRD features 4/5/6/7/8/9).
--
-- The live turn only converses; the SIX analytics features are computed
-- post-call from the saved TRANSCRIPT (the turns table) by services/agent/
-- post_call.py. Two shape changes support that:
--
--   1. Each transcript row carries its language, so the after-call worker reads
--      (speaker, text, timestamp, language) per turn.
--   2. The call summary record stores the outputs of the features that did not
--      have a home before: AI Intent Recognition (intents), AI Next Best Action
--      (next_best_action), and the sentiment trajectory. Summary, tier,
--      sentiment_avg and follow-up already had columns.
--
-- Idempotent so it is safe to re-run against an existing database.

ALTER TABLE turns
  ADD COLUMN IF NOT EXISTS lang text;

ALTER TABLE call_summaries
  ADD COLUMN IF NOT EXISTS intents              text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS next_best_action     text,
  ADD COLUMN IF NOT EXISTS sentiment_trajectory text;

-- ─────────────────────────────────────────────────────────────────────────
-- migrations/005_opt_out_intent.sql
-- ─────────────────────────────────────────────────────────────────────────
-- In-call compliance opt-out ("remove me / stop calling / do not call again").
-- The model classifies it as intent 'do_not_call'; rules.decide() maps it to
-- the Directive 'opt_out'; the worker writes the number to the DNC suppression
-- list and speaks only a bare confirmation before hanging up. Two enum columns
-- record that turn and need the new labels (calls.outcome already has
-- 'do_not_call'). ADD VALUE cannot run in a transaction — run standalone.

ALTER TYPE turn_intent ADD VALUE IF NOT EXISTS 'do_not_call';
ALTER TYPE next_action ADD VALUE IF NOT EXISTS 'opt_out';
