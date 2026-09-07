-- ============================================================================
-- QUESILLOS LO NUESTRO - Cierre de caja detallado (arqueo por denominacion:
-- monedas/billetes en cordobas + billetes en dolares). Aplicar en LOCAL y en
-- la NUBE (Railway). Es idempotente.
-- ============================================================================

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='cierres_caja'
                  AND COLUMN_NAME='detalle_conteo') = 0,
  'ALTER TABLE cierres_caja ADD COLUMN detalle_conteo JSON NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='cierres_caja'
                  AND COLUMN_NAME='tipo_cambio') = 0,
  'ALTER TABLE cierres_caja ADD COLUMN tipo_cambio DECIMAL(10,4) NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT 'listo: cierres_caja.detalle_conteo / tipo_cambio al dia' AS resultado;
