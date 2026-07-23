-- In-call compliance opt-out ("remove me / stop calling / do not call again").
--
-- The live model can now classify a caller's removal request as the intent
-- 'do_not_call' (distinct from 'not_interested' — a legal opt-out, not just a
-- no for today), and rules.decide() maps it to the new Directive 'opt_out',
-- which the worker turns into an immediate DNC suppression write + a bare
-- confirmation before hanging up.
--
-- Two enum columns record that turn and must learn the two new labels, or the
-- transcript write throws "invalid input value for enum" and the fire-and-forget
-- insert is lost (the compliance record of WHY the call ended):
--
--   * turns.intent  (turn_intent)  <- the model's classification: 'do_not_call'
--   * turns.action  (next_action)  <- the resolved directive value: 'opt_out'
--
-- calls.outcome (call_outcome) already has 'do_not_call' — no change needed.
--
-- ALTER TYPE ... ADD VALUE cannot run inside a transaction block; run these as
-- standalone statements (the Neon SQL editor / psql do this by default).
-- Idempotent via IF NOT EXISTS, so it is safe to re-run.

ALTER TYPE turn_intent ADD VALUE IF NOT EXISTS 'do_not_call';
ALTER TYPE next_action ADD VALUE IF NOT EXISTS 'opt_out';
