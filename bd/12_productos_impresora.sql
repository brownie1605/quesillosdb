-- ============================================================================
-- QUESILLOS LO NUESTRO - Impresora asignada por producto (Quesillo/Cocina/
-- Bebidas). Aplicar en LOCAL y en la NUBE (Railway). Es idempotente.
-- ============================================================================

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='impresora') = 0,
  "ALTER TABLE productos ADD COLUMN impresora ENUM('quesillo','cocina','bebidas') NULL AFTER se_vende",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT 'listo: productos.impresora al dia' AS resultado;
