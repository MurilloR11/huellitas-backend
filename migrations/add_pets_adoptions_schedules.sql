-- =============================================================================
-- HUELLITAS — Migration: pets, adoption_requests, visit_schedules,
--             developer_usage_logs
-- Run once in: Supabase Dashboard → SQL Editor
-- Safe to re-run: IF NOT EXISTS guards on every statement.
-- =============================================================================


-- =============================================================================
-- 1. ENUM TYPES
-- =============================================================================

DO $$ BEGIN
  CREATE TYPE public.pet_species AS ENUM ('dog', 'cat', 'rabbit', 'other');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE public.pet_gender AS ENUM ('male', 'female');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE public.pet_size AS ENUM ('small', 'medium', 'large');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE public.pet_status AS ENUM ('available', 'in_process', 'adopted');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE public.adoption_status AS ENUM (
    'pending', 'reviewing', 'approved', 'rejected', 'completed'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE public.visit_status AS ENUM (
    'pending', 'confirmed', 'completed', 'cancelled'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;


-- =============================================================================
-- 2. TABLES
-- =============================================================================

-- pets ------------------------------------------------------------------------
-- Each pet belongs to one approved foundation.
-- Clinical record fields are stored as columns (no separate table needed).
CREATE TABLE IF NOT EXISTS public.pets (
  id             bigint                  PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  name           text                    NOT NULL,
  species        public.pet_species      NOT NULL,
  breed          text,
  age_months     int                     NOT NULL CHECK (age_months >= 0),
  gender         public.pet_gender       NOT NULL,
  size           public.pet_size         NOT NULL,
  description    text,
  photos         text[]                  NOT NULL DEFAULT '{}',
  status         public.pet_status       NOT NULL DEFAULT 'available',
  foundation_id  uuid                    NOT NULL
                   REFERENCES public.foundations (id) ON DELETE CASCADE,
  city           text                    NOT NULL,
  -- clinical record
  vaccinated     boolean                 NOT NULL DEFAULT false,
  sterilized     boolean                 NOT NULL DEFAULT false,
  dewormed       boolean                 NOT NULL DEFAULT false,
  microchipped   boolean                 NOT NULL DEFAULT false,
  health_notes   text,
  created_at     timestamptz             NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pets_foundation_id_idx ON public.pets (foundation_id);
CREATE INDEX IF NOT EXISTS pets_status_idx        ON public.pets (status);
CREATE INDEX IF NOT EXISTS pets_species_idx       ON public.pets (species);
CREATE INDEX IF NOT EXISTS pets_city_idx          ON public.pets (city);


-- adoption_requests -----------------------------------------------------------
-- One request per (adopter, pet). A pet can have multiple requests over time
-- (e.g. after a rejection), but only one active one at a time.
CREATE TABLE IF NOT EXISTS public.adoption_requests (
  id             bigint                  PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  pet_id         bigint                  NOT NULL
                   REFERENCES public.pets (id) ON DELETE RESTRICT,
  adopter_id     uuid                    NOT NULL
                   REFERENCES public.profiles (id) ON DELETE CASCADE,
  foundation_id  uuid                    NOT NULL
                   REFERENCES public.foundations (id) ON DELETE CASCADE,
  status         public.adoption_status  NOT NULL DEFAULT 'pending',
  message        text                    NOT NULL DEFAULT '',
  created_at     timestamptz             NOT NULL DEFAULT now(),
  updated_at     timestamptz             NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS adoptions_adopter_idx     ON public.adoption_requests (adopter_id);
CREATE INDEX IF NOT EXISTS adoptions_foundation_idx  ON public.adoption_requests (foundation_id);
CREATE INDEX IF NOT EXISTS adoptions_pet_idx         ON public.adoption_requests (pet_id);
CREATE INDEX IF NOT EXISTS adoptions_status_idx      ON public.adoption_requests (status);

-- Auto-update updated_at on every row change
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS adoption_requests_updated_at ON public.adoption_requests;
CREATE TRIGGER adoption_requests_updated_at
  BEFORE UPDATE ON public.adoption_requests
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();


-- visit_schedules -------------------------------------------------------------
-- A foundation schedules a physical visit for an adoption request.
CREATE TABLE IF NOT EXISTS public.visit_schedules (
  id                    bigint              PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  adoption_request_id   bigint              NOT NULL
                          REFERENCES public.adoption_requests (id) ON DELETE CASCADE,
  foundation_id         uuid                NOT NULL
                          REFERENCES public.foundations (id) ON DELETE CASCADE,
  adopter_id            uuid                NOT NULL
                          REFERENCES public.profiles (id) ON DELETE CASCADE,
  scheduled_at          timestamptz         NOT NULL,
  location              text,
  notes                 text,
  status                public.visit_status NOT NULL DEFAULT 'pending',
  created_at            timestamptz         NOT NULL DEFAULT now(),
  updated_at            timestamptz         NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS visits_adoption_idx   ON public.visit_schedules (adoption_request_id);
CREATE INDEX IF NOT EXISTS visits_foundation_idx ON public.visit_schedules (foundation_id);
CREATE INDEX IF NOT EXISTS visits_adopter_idx    ON public.visit_schedules (adopter_id);

DROP TRIGGER IF EXISTS visit_schedules_updated_at ON public.visit_schedules;
CREATE TRIGGER visit_schedules_updated_at
  BEFORE UPDATE ON public.visit_schedules
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();


-- developer_usage_logs --------------------------------------------------------
-- One row per API call made with a developer access key.
-- Written by Flask middleware; never by the client directly.
CREATE TABLE IF NOT EXISTS public.developer_usage_logs (
  id             bigint      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  developer_id   uuid        NOT NULL
                   REFERENCES public.developers (id) ON DELETE CASCADE,
  endpoint       text        NOT NULL,
  method         text        NOT NULL,
  status_code    int         NOT NULL,
  response_ms    int,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS dev_logs_developer_idx  ON public.developer_usage_logs (developer_id);
CREATE INDEX IF NOT EXISTS dev_logs_created_at_idx ON public.developer_usage_logs (created_at DESC);


-- =============================================================================
-- 3. ROW LEVEL SECURITY
-- =============================================================================

ALTER TABLE public.pets                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.adoption_requests    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visit_schedules      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.developer_usage_logs ENABLE ROW LEVEL SECURITY;

-- Drop policies first so this script is idempotent ---------------------------
DROP POLICY IF EXISTS "pets: select available"          ON public.pets;
DROP POLICY IF EXISTS "pets: foundation select own"     ON public.pets;
DROP POLICY IF EXISTS "adoptions: adopter select own"   ON public.adoption_requests;
DROP POLICY IF EXISTS "adoptions: foundation select"    ON public.adoption_requests;
DROP POLICY IF EXISTS "visits: adopter select own"      ON public.visit_schedules;
DROP POLICY IF EXISTS "visits: foundation select own"   ON public.visit_schedules;
DROP POLICY IF EXISTS "dev_logs: developer select own"  ON public.developer_usage_logs;

-- pets -----------------------------------------------------------------------

-- Anyone (including anonymous) can browse available pets
CREATE POLICY "pets: select available"
  ON public.pets FOR SELECT
  USING (status = 'available');

-- A foundation sees all its own pets regardless of status
CREATE POLICY "pets: foundation select own"
  ON public.pets FOR SELECT
  TO authenticated
  USING (foundation_id = auth.uid());

-- All writes go through Flask service_role → no client INSERT/UPDATE/DELETE.

-- adoption_requests ----------------------------------------------------------

-- An adopter can see only their own requests
CREATE POLICY "adoptions: adopter select own"
  ON public.adoption_requests FOR SELECT
  TO authenticated
  USING (adopter_id = auth.uid());

-- A foundation can see requests directed at it
CREATE POLICY "adoptions: foundation select"
  ON public.adoption_requests FOR SELECT
  TO authenticated
  USING (foundation_id = auth.uid());

-- All writes go through Flask service_role.

-- visit_schedules ------------------------------------------------------------

-- An adopter can see visits tied to their requests
CREATE POLICY "visits: adopter select own"
  ON public.visit_schedules FOR SELECT
  TO authenticated
  USING (adopter_id = auth.uid());

-- A foundation can see visits it scheduled
CREATE POLICY "visits: foundation select own"
  ON public.visit_schedules FOR SELECT
  TO authenticated
  USING (foundation_id = auth.uid());

-- All writes go through Flask service_role.

-- developer_usage_logs -------------------------------------------------------

-- A developer can only see their own usage logs
CREATE POLICY "dev_logs: developer select own"
  ON public.developer_usage_logs FOR SELECT
  TO authenticated
  USING (developer_id = auth.uid());

-- All writes go through Flask service_role.


-- =============================================================================
-- Done.
-- =============================================================================
