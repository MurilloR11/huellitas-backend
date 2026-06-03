-- Tracks every request authenticated via X-API-Key.
-- Run in Supabase SQL editor.

CREATE TABLE IF NOT EXISTS public.api_call_logs (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  key_id      uuid        NOT NULL
                CONSTRAINT api_call_logs_key_id_fkey
                REFERENCES public.access_keys(id) ON DELETE CASCADE,
  user_id     uuid        NOT NULL
                CONSTRAINT api_call_logs_user_id_fkey
                REFERENCES public.profiles(id) ON DELETE CASCADE,
  method      text        NOT NULL,
  path        text        NOT NULL,
  status_code integer     NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_call_logs_user_created ON api_call_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_call_logs_key_created  ON api_call_logs(key_id,  created_at DESC);
