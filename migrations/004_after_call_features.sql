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
