-- ============================================================================
-- QUESILLOS LO NUESTRO - Notas en la factura (ej. para justificar un
-- descuento). Aplicar en LOCAL y en la NUBE (Railway). Es idempotente.
-- ============================================================================

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ventas'
                  AND COLUMN_NAME='notas') = 0,
  'ALTER TABLE ventas ADD COLUMN notas TEXT NULL AFTER metodo_pago',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT 'listo: ventas.notas al dia' AS resultado;
