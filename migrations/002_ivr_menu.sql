-- Adds the DTMF keypad menu to existing databases.
-- 001_init.sql already carries this column for fresh installs; this migration
-- exists so a running database can be upgraded without a reseed.
ALTER TABLE phone_numbers
  ADD COLUMN IF NOT EXISTS ivr_menu jsonb NOT NULL DEFAULT '{}';
