-- ============================================================
-- RLS Policies — Huellitas
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- El backend Flask usa SUPABASE_SERVICE_ROLE_KEY, que bypasea
-- RLS completamente. Estas políticas solo afectan llamadas
-- directas a la API de Supabase (ej. desde DevTools).
-- ============================================================


-- ── profiles ─────────────────────────────────────────────────────────────────

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Cada usuario puede leer su propio perfil
CREATE POLICY "profiles_select_own"
ON profiles FOR SELECT
TO authenticated
USING (auth.uid() = id);

-- Cada usuario puede crear su propio perfil al registrarse
-- (solo si el id coincide con su auth.uid y el rol no es admin)
CREATE POLICY "profiles_insert_own"
ON profiles FOR INSERT
TO authenticated
WITH CHECK (
    auth.uid() = id
    AND role IN ('ciudadano', 'fundacion', 'developer')
);

-- Cada usuario puede actualizar su propio perfil
-- pero NO puede cambiar su propio rol ni su id
CREATE POLICY "profiles_update_own"
ON profiles FOR UPDATE
TO authenticated
USING (auth.uid() = id)
WITH CHECK (
    auth.uid() = id
    AND role = (SELECT role FROM profiles WHERE id = auth.uid())
);

-- Nadie puede borrar perfiles directamente (solo service_role)


-- ── foundations ──────────────────────────────────────────────────────────────

ALTER TABLE foundations ENABLE ROW LEVEL SECURITY;

-- Cualquiera puede ver fundaciones aprobadas
CREATE POLICY "foundations_select_approved"
ON foundations FOR SELECT
USING (status = 'approved');

-- La fundación puede ver su propio registro (cualquier estado)
CREATE POLICY "foundations_select_own"
ON foundations FOR SELECT
TO authenticated
USING (auth.uid() = id);

-- Nadie puede insertar, actualizar ni borrar fundaciones directamente
-- (solo el backend Flask via service_role puede hacerlo)


-- ── pets ─────────────────────────────────────────────────────────────────────

ALTER TABLE pets ENABLE ROW LEVEL SECURITY;

-- Cualquiera puede ver mascotas disponibles
CREATE POLICY "pets_select_available"
ON pets FOR SELECT
USING (status = 'available');

-- Las fundaciones pueden ver todas sus propias mascotas
CREATE POLICY "pets_select_own_foundation"
ON pets FOR SELECT
TO authenticated
USING (
    foundation_id = (
        SELECT id FROM foundations WHERE id = auth.uid()
    )
);

-- Nadie puede insertar, actualizar ni borrar mascotas directamente
-- (solo el backend Flask via service_role)


-- ── adoption_requests ────────────────────────────────────────────────────────

ALTER TABLE adoption_requests ENABLE ROW LEVEL SECURITY;

-- El adoptante puede ver sus propias solicitudes
CREATE POLICY "adoptions_select_own"
ON adoption_requests FOR SELECT
TO authenticated
USING (adopter_id = auth.uid());

-- La fundación puede ver las solicitudes de sus mascotas
CREATE POLICY "adoptions_select_foundation"
ON adoption_requests FOR SELECT
TO authenticated
USING (
    foundation_id = (
        SELECT id FROM foundations WHERE id = auth.uid()
    )
);

-- Nadie puede insertar, actualizar ni borrar solicitudes directamente
-- (solo el backend Flask via service_role)


-- ── audit_logs ───────────────────────────────────────────────────────────────

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Nadie tiene acceso directo a audit_logs (solo service_role del backend)
