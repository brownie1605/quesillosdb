-- ============================================================================
-- QUESILLOS LO NUESTRO - Marca ligada a Proveedor
-- Aplicar en LOCAL y en la NUBE (Railway).
-- Es idempotente: puede ejecutarse varias veces sin romper nada.
-- ============================================================================

SET @db := DATABASE();

-- ---------------------------------------------------------------------------
-- marcas.id_proveedor: de que proveedor viene esa marca
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='marcas'
                  AND COLUMN_NAME='id_proveedor') = 0,
  'ALTER TABLE marcas ADD COLUMN id_proveedor INT NULL AFTER nombre',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT 'listo: marcas.id_proveedor al dia' AS resultado;
