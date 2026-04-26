-- =============================================================================
-- HUELLITAS — Supabase database bootstrap
-- Run once in the Supabase Dashboard → SQL Editor.
-- Safe to re-run: CREATE IF NOT EXISTS / OR REPLACE / DROP IF EXISTS guards.
-- =============================================================================

-- =============================================================================
-- 1. ENUM TYPES
-- =============================================================================
DO $$ BEGIN
  CREATE TYPE public.user_role AS ENUM ('ciudadano', 'fundacion', 'developer', 'admin');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE public.foundation_status AS ENUM ('pending', 'approved', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;


-- =============================================================================
-- 2. TABLES
-- =============================================================================

-- profiles ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
  id         uuid                    PRIMARY KEY
               REFERENCES auth.users (id) ON DELETE CASCADE,
  role       public.user_role        NOT NULL DEFAULT 'ciudadano',
  full_name  text                    NOT NULL,
  email      text                    NOT NULL,
  created_at timestamptz             NOT NULL DEFAULT now()
);

-- foundations -------------------------------------------------------------
-- Only rows with role = 'fundacion' have a record here.
CREATE TABLE IF NOT EXISTS public.foundations (
  id               uuid                      PRIMARY KEY
                     REFERENCES public.profiles (id) ON DELETE CASCADE,
  org_name         text                      NOT NULL,
  municipio        text                      NOT NULL,
  phone            text                      NOT NULL,
  status           public.foundation_status  NOT NULL DEFAULT 'pending',
  rejection_reason text,
  reviewed_by      uuid                      REFERENCES public.profiles (id),
  reviewed_at      timestamptz
);

-- developers --------------------------------------------------------------
-- Only rows with role = 'developer' have a record here.
CREATE TABLE IF NOT EXISTS public.developers (
  id          uuid  PRIMARY KEY
                REFERENCES public.profiles (id) ON DELETE CASCADE,
  permissions jsonb NOT NULL DEFAULT '{}'
);

-- audit_logs --------------------------------------------------------------
-- Append-only log of admin actions (approve / reject).
-- Written exclusively by the Flask backend via service_role.
CREATE TABLE IF NOT EXISTS public.audit_logs (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_id    uuid        NOT NULL REFERENCES public.profiles (id),
  action      text        NOT NULL,
  target_id   uuid,
  target_type text,
  ip_address  text,
  metadata    jsonb       NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now()
);


-- =============================================================================
-- 3. TRIGGER: auto-create profiles (and role rows) on sign-up
-- =============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER            -- runs as the function owner, not the calling user
SET search_path = public     -- prevent search_path injection
AS $$
DECLARE
  _role  text;
  _name  text;
  _email text;
BEGIN
  _role  := COALESCE(NEW.raw_user_meta_data ->> 'role', 'ciudadano');
  _name  := COALESCE(NEW.raw_user_meta_data ->> 'full_name', '');
  _email := COALESCE(NEW.email, NEW.raw_user_meta_data ->> 'email', '');

  -- Reject unknown roles silently (default to ciudadano).
  -- 'admin' cannot be self-assigned; admins are created manually.
  IF _role NOT IN ('ciudadano', 'fundacion', 'developer') THEN
    _role := 'ciudadano';
  END IF;

  INSERT INTO public.profiles (id, role, full_name, email)
  VALUES (NEW.id, _role::public.user_role, _name, _email);

  IF _role = 'fundacion' THEN
    INSERT INTO public.foundations (id, org_name, municipio, phone)
    VALUES (
      NEW.id,
      COALESCE(NEW.raw_user_meta_data ->> 'org_name',  ''),
      COALESCE(NEW.raw_user_meta_data ->> 'municipio', ''),
      COALESCE(NEW.raw_user_meta_data ->> 'phone',     '')
    );

  ELSIF _role = 'developer' THEN
    INSERT INTO public.developers (id)
    VALUES (NEW.id);
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();


-- =============================================================================
-- 4. HELPER: resolve the current user's app role without RLS recursion
-- =============================================================================

-- SECURITY DEFINER lets this function read profiles bypassing RLS,
-- so policies that call it don't recurse infinitely.
CREATE OR REPLACE FUNCTION public.current_user_role()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT role::text FROM public.profiles WHERE id = auth.uid();
$$;


-- =============================================================================
-- 5. PREVENT SELF-ROLE ESCALATION
-- =============================================================================

-- Revoke the ability for authenticated users to update the role column.
-- The service_role (Flask backend) retains full access.
REVOKE UPDATE (role) ON public.profiles FROM authenticated;


-- =============================================================================
-- 6. ROW LEVEL SECURITY
-- =============================================================================

ALTER TABLE public.profiles    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.foundations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.developers  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs  ENABLE ROW LEVEL SECURITY;

-- Drop existing policies so this script is idempotent -------------------
DROP POLICY IF EXISTS "profiles: own select"     ON public.profiles;
DROP POLICY IF EXISTS "profiles: own update"     ON public.profiles;
DROP POLICY IF EXISTS "profiles: admin select"   ON public.profiles;
DROP POLICY IF EXISTS "foundations: own select"  ON public.foundations;
DROP POLICY IF EXISTS "foundations: admin select" ON public.foundations;
DROP POLICY IF EXISTS "developers: own select"   ON public.developers;
DROP POLICY IF EXISTS "audit_logs: admin select" ON public.audit_logs;

-- profiles ---------------------------------------------------------------

-- A user can always read their own profile row.
CREATE POLICY "profiles: own select"
  ON public.profiles
  FOR SELECT
  USING (auth.uid() = id);

-- A user can update their own profile (role column is revoked above).
CREATE POLICY "profiles: own update"
  ON public.profiles
  FOR UPDATE
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

-- An admin can read every profile.
-- current_user_role() uses SECURITY DEFINER to avoid infinite recursion.
CREATE POLICY "profiles: admin select"
  ON public.profiles
  FOR SELECT
  USING (public.current_user_role() = 'admin');

-- foundations ------------------------------------------------------------

-- A foundation can only see its own row.
CREATE POLICY "foundations: own select"
  ON public.foundations
  FOR SELECT
  USING (auth.uid() = id);

-- An admin can see all foundation rows.
CREATE POLICY "foundations: admin select"
  ON public.foundations
  FOR SELECT
  USING (public.current_user_role() = 'admin');

-- No INSERT / UPDATE / DELETE policies for foundations from the client.
-- All writes (approve, reject, initial insert via trigger) go through
-- service_role, which bypasses RLS entirely.

-- developers -------------------------------------------------------------

-- A developer can only see their own row.
CREATE POLICY "developers: own select"
  ON public.developers
  FOR SELECT
  USING (auth.uid() = id);

-- audit_logs -------------------------------------------------------------

-- Audit logs are write-only for clients; only admins may read them.
CREATE POLICY "audit_logs: admin select"
  ON public.audit_logs
  FOR SELECT
  USING (public.current_user_role() = 'admin');

-- =============================================================================
-- Done.
-- =============================================================================
