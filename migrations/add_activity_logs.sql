-- =============================================================================
-- HUELLITAS — activity_logs table
-- Run once in the Supabase Dashboard → SQL Editor.
-- Tracks all user-originated platform events (unlike audit_logs, which only
-- covers admin actions). User info is denormalized at insert time so reads
-- are a simple table scan with no joins.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.activity_logs (
  id          bigserial    PRIMARY KEY,
  user_id     uuid         NOT NULL,
  user_name   text         NOT NULL DEFAULT '',
  user_email  text         NOT NULL DEFAULT '',
  user_role   text         NOT NULL DEFAULT 'ciudadano',
  action      text         NOT NULL,
  description text         NOT NULL DEFAULT '',
  metadata    jsonb        NOT NULL DEFAULT '{}',
  ip_address  text,
  created_at  timestamptz  NOT NULL DEFAULT now()
);

-- Indexes for the common admin query patterns
CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON public.activity_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_logs_action     ON public.activity_logs (action);
CREATE INDEX IF NOT EXISTS idx_activity_logs_user_id    ON public.activity_logs (user_id);

-- Row-level security: only service-role can read/write (backend uses service key)
ALTER TABLE public.activity_logs ENABLE ROW LEVEL SECURITY;
