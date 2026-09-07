-- ============================================================================
-- QUESILLOS LO NUESTRO - Bloqueo por intentos fallidos (login y codigo de
-- recuperacion de contrasena). Aplicar en LOCAL y en la NUBE. Es idempotente.
--
-- Agrega a `usuarios`:
--   intentos_fallidos   -> contador de logins con contrasena incorrecta.
--   bloqueado_hasta     -> si tiene fecha futura, el login queda bloqueado
--                          temporalmente (distinto de `estado='bloqueado'`,
--                          que es un bloqueo manual y permanente del Admin).
--   intentos_codigo     -> contador de intentos fallidos verificando el
--                          codigo de recuperacion de 6 digitos.
-- ============================================================================

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='usuarios'
                  AND COLUMN_NAME='intentos_fallidos') = 0,
  'ALTER TABLE usuarios ADD COLUMN intentos_fallidos INT NOT NULL DEFAULT 0',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='usuarios'
                  AND COLUMN_NAME='bloqueado_hasta') = 0,
  'ALTER TABLE usuarios ADD COLUMN bloqueado_hasta DATETIME NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='usuarios'
                  AND COLUMN_NAME='intentos_codigo') = 0,
  'ALTER TABLE usuarios ADD COLUMN intentos_codigo INT NOT NULL DEFAULT 0',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT 'listo: columnas de bloqueo por intentos agregadas' AS resultado;
