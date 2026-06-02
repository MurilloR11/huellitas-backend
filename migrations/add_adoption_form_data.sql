-- =============================================================================
-- HUELLITAS — Migration: add form_data column to adoption_requests
-- Run once in: Supabase Dashboard → SQL Editor
-- Safe to re-run: IF NOT EXISTS / DO $$ guard.
-- =============================================================================
--
-- Stores the structured form data submitted by the adopter
-- (housing type, ownership, residents, etc.) as a JSONB object.
-- Expected shape:
--   {
--     "phone":         "+57 300 000 0000",
--     "city":          "Medellín",
--     "housing_type":  "apartment" | "house" | "rural" | "other",
--     "ownership":     "owner" | "renter" | "family",
--     "outdoor_space": "large" | "small" | "none",
--     "residents":     "1" | "2" | "3-4" | "5+",
--     "children":      "none" | "1" | "2+",
--     "current_pets":  "none" | "1-dog" | "1-cat" | "multi" | "other",
--     "prev_pets":     "yes" | "no"
--   }
-- =============================================================================

ALTER TABLE public.adoption_requests
  ADD COLUMN IF NOT EXISTS form_data jsonb;
