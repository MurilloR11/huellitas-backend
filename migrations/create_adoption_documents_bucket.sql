-- Run in Supabase Dashboard → SQL Editor
-- Creates the storage bucket for adoption documents (ID, proof of address, landlord auth)

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'adoption-documents',
  'adoption-documents',
  true,
  5242880,
  ARRAY['application/pdf', 'image/jpeg', 'image/png', 'image/webp']
)
ON CONFLICT (id) DO NOTHING;
