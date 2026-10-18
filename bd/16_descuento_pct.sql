-- ============================================================================
-- QUESILLOS LO NUESTRO - Descuento en porcentaje para las cuentas de mesa.
-- Aplicar en LOCAL y en la NUBE (Railway) ANTES de desplegar el codigo que
-- usa esta columna. Es idempotente: solo agrega lo que falta, no borra datos.
--
--   ventas.descuento_pct  DECIMAL(5,2)  porcentaje elegido con el boton
--                                       "Descuento" de la mesa. El monto
--                                       (ventas.descuento) se recalcula solo
--                                       al agregar o quitar productos.
--                                       NULL = sin porcentaje (como siempre).
-- ============================================================================

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ventas'
                  AND COLUMN_NAME='descuento_pct') = 0,
  'ALTER TABLE ventas ADD COLUMN descuento_pct DECIMAL(5,2) NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT 'listo: ventas.descuento_pct al dia' AS resultado;
