-- =============================================================================
-- Cuentas de demo públicas (solo lectura)
-- =============================================================================
-- Las credenciales de estas cuentas están publicadas en el README del frontend
-- para que cualquiera pueda probar los 4 roles.
--
-- Protección en dos capas:
--   1. Backend (Flask): los IDs de estas cuentas van en la variable de entorno
--      DEMO_USER_IDS. Cualquier escritura responde 403 y el panel admin
--      enmascara los correos.
--   2. Base de datos (RLS): la cuenta admin de demo NO obtiene el rol 'admin'
--      en las políticas RLS, así que no puede leer perfiles de otros usuarios
--      directamente con su token contra la API de Supabase.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.demo_accounts (
  user_id    uuid        PRIMARY KEY
               REFERENCES public.profiles (id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Sin políticas: solo el service_role (backend) puede leer o escribir.
ALTER TABLE public.demo_accounts ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.current_user_role()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT CASE
           WHEN p.role = 'admin'
                AND EXISTS (SELECT 1 FROM public.demo_accounts d WHERE d.user_id = p.id)
             THEN 'admin_demo'
           ELSE p.role::text
         END
  FROM public.profiles p
  WHERE p.id = auth.uid();
$$;
