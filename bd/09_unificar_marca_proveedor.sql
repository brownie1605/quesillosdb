-- ============================================================================
-- QUESILLOS LO NUESTRO - Unificar Marca y Proveedor
-- Aplicar en LOCAL y en la NUBE (Railway). Es idempotente.
--
-- Para un restaurante que compra insumos (no reventa de productos de marca),
-- "Marca" era una capa intermedia obligatoria sin informacion propia: toda
-- marca ya estaba enlazada 1 a 1 a un proveedor (ver 07_marca_proveedor_estricto.sql).
-- Esto quita esa capa: los productos se enlazan directo a su Proveedor.
--
-- 1) productos.id_proveedor (nueva columna)
-- 2) Copia el proveedor real de cada producto, via la marca que tenia
-- 3) Elimina productos.id_marca
-- 4) Elimina la tabla marcas
-- ============================================================================

SET @db := DATABASE();

-- ---------------------------------------------------------------------------
-- 1) productos.id_proveedor
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='id_proveedor') = 0,
  'ALTER TABLE productos ADD COLUMN id_proveedor INT NULL AFTER id_categoria',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------------------------------------------------------------------
-- 2) Migrar el dato: productos.id_marca -> marcas.id_proveedor -> productos.id_proveedor
--    Solo si la tabla marcas todavia existe (una segunda corrida ya la habra
--    borrado, y no hay nada que migrar).
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.TABLES
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='marcas') > 0
               AND (SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='id_marca') > 0,
  'UPDATE productos p
     JOIN marcas m ON m.id_marca = p.id_marca
   SET p.id_proveedor = m.id_proveedor
   WHERE p.id_marca IS NOT NULL AND p.id_proveedor IS NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------------------------------------------------------------------
-- 3) Eliminar productos.id_marca (primero su FK si el motor la creo, como
--    en la nube -- en local nunca se llego a crear un constraint real)
-- ---------------------------------------------------------------------------
SET @fk := (SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
              AND COLUMN_NAME='id_marca' AND REFERENCED_TABLE_NAME IS NOT NULL
            LIMIT 1);
SET @sql := IF(@fk IS NOT NULL,
  CONCAT('ALTER TABLE productos DROP FOREIGN KEY `', @fk, '`'),
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='id_marca') > 0,
  'ALTER TABLE productos DROP COLUMN id_marca',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------------------------------------------------------------------
-- 4) Eliminar la tabla marcas
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS marcas;

SELECT 'listo: productos enlazados directo a proveedor, tabla marcas eliminada' AS resultado;
