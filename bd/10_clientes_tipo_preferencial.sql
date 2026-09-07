-- ============================================================================
-- QUESILLOS LO NUESTRO - Clientes: tipo (interno/externo) y preferencial
-- Aplicar en LOCAL y en la NUBE (Railway). Es idempotente.
--
-- tipo_cliente: 'interno' (personal/familia de la empresa, por membresia)
--               'externo' (cliente normal que paga), default para todos los ya existentes.
-- es_preferencial: marca VIP/personal, usada en el dashboard de consumo.
-- ============================================================================

SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='clientes'
                  AND COLUMN_NAME='tipo_cliente') = 0,
  "ALTER TABLE clientes ADD COLUMN tipo_cliente ENUM('interno','externo') NOT NULL DEFAULT 'externo' AFTER direccion",
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='clientes'
                  AND COLUMN_NAME='es_preferencial') = 0,
  'ALTER TABLE clientes ADD COLUMN es_preferencial TINYINT(1) NOT NULL DEFAULT 0 AFTER tipo_cliente',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT 'listo: clientes.tipo_cliente y clientes.es_preferencial al dia' AS resultado;
