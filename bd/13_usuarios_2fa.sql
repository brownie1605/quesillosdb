-- ============================================================================
-- QUESILLOS LO NUESTRO - 2FA (TOTP) por usuario. Aplicar en LOCAL y en la
-- NUBE (Railway). Es idempotente.
-- ============================================================================

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='usuarios'
                  AND COLUMN_NAME='totp_secret') = 0,
  'ALTER TABLE usuarios ADD COLUMN totp_secret VARCHAR(64) NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='usuarios'
                  AND COLUMN_NAME='totp_habilitado') = 0,
  'ALTER TABLE usuarios ADD COLUMN totp_habilitado TINYINT(1) NOT NULL DEFAULT 0',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='usuarios'
                  AND COLUMN_NAME='totp_recovery_codes') = 0,
  'ALTER TABLE usuarios ADD COLUMN totp_recovery_codes TEXT NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT 'listo: usuarios.totp_* al dia' AS resultado;
