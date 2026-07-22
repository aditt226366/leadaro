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
