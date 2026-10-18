-- ============================================================================
-- QUESILLOS LO NUESTRO - Pago dividido y Pedidos Ya. Aplicar en LOCAL y en la
-- NUBE (Railway) ANTES de desplegar el codigo que usa estas columnas.
-- Es idempotente: solo agrega lo que falta, no borra datos.
--
--   ventas.pagos_detalle     JSON  [{"metodo": "Efectivo", "monto": 300.0}, ...]
--                                  NULL = venta pagada con un solo metodo
--                                  (el de ventas.metodo_pago, como siempre).
--   productos.es_pedidos_ya  0/1   el producto es de la carta de Pedidos Ya.
-- ============================================================================

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ventas'
                  AND COLUMN_NAME='pagos_detalle') = 0,
  'ALTER TABLE ventas ADD COLUMN pagos_detalle JSON NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='es_pedidos_ya') = 0,
  'ALTER TABLE productos ADD COLUMN es_pedidos_ya TINYINT(1) NOT NULL DEFAULT 0',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT 'listo: ventas.pagos_detalle / productos.es_pedidos_ya al dia' AS resultado;
