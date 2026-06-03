-- Phase 1: support multiple named API keys per user
-- Run this migration in Supabase SQL editor

-- Add columns to access_keys
ALTER TABLE access_keys ADD COLUMN IF NOT EXISTS name   TEXT    NOT NULL DEFAULT '';
ALTER TABLE access_keys ADD COLUMN IF NOT EXISTS prefix TEXT    NOT NULL DEFAULT '';
ALTER TABLE access_keys ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true;

-- Drop the unique constraint on user_id so multiple keys are allowed per user
-- (Supabase default constraint name; adjust if yours differs)
ALTER TABLE access_keys DROP CONSTRAINT IF EXISTS access_keys_user_id_key;

-- Index for efficient per-user lookups
CREATE INDEX IF NOT EXISTS idx_access_keys_user_id ON access_keys(user_id);

-- Index for direct API-key lookup by hash (used by X-API-Key middleware)
CREATE INDEX IF NOT EXISTS idx_access_keys_key_hash ON access_keys(key_hash);

-- Backfill prefix for any existing rows
UPDATE access_keys SET prefix = substring(key_hash, 1, 9) WHERE prefix = '';
