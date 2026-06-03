-- Adds index on key_hash for direct X-API-Key header lookups.
-- Run this only if you already applied add_developer_multikey.sql.
CREATE INDEX IF NOT EXISTS idx_access_keys_key_hash ON access_keys(key_hash);
