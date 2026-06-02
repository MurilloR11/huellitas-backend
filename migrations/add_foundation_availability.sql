-- foundation_availability -------------------------------------------------------
-- Stores the days (and working hours) that a foundation makes available for
-- in-person adoption visits.  Foundations replace their future availability
-- wholesale every week via POST /foundations/me/availability.
CREATE TABLE IF NOT EXISTS public.foundation_availability (
  id              bigint      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  foundation_id   uuid        NOT NULL
                    REFERENCES public.foundations(id) ON DELETE CASCADE,
  available_date  date        NOT NULL,
  start_time      time        NOT NULL DEFAULT '09:00',
  end_time        time        NOT NULL DEFAULT '17:00',
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (foundation_id, available_date)
);

CREATE INDEX IF NOT EXISTS avail_foundation_idx
  ON public.foundation_availability (foundation_id);

CREATE INDEX IF NOT EXISTS avail_date_idx
  ON public.foundation_availability (available_date);
