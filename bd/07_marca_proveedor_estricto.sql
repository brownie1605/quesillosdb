-- ============================================================================
-- QUESILLOS LO NUESTRO - Marca <-> Proveedor estrictamente enlazados
-- Toda marca debe pertenecer a un proveedor (marcas.id_proveedor ya no
-- admite NULL). Aplicar en LOCAL y en la NUBE. Es idempotente.
-- ============================================================================

-- 1) Proveedor placeholder para marcas antiguas que no tenian proveedor.
--    El admin debe reasignarlas a su proveedor real desde
--    Productos -> "Marcas y proveedores".
INSERT INTO proveedores (id_empresa, nombre, estado)
SELECT 1, 'Sin proveedor asignado', 'activo'
WHERE NOT EXISTS (
    SELECT 1 FROM proveedores WHERE nombre = 'Sin proveedor asignado' AND id_empresa = 1
);

-- 2) Enlazar toda marca huerfana al proveedor placeholder.
UPDATE marcas m
JOIN proveedores p ON p.nombre = 'Sin proveedor asignado' AND p.id_empresa = m.id_empresa
SET m.id_proveedor = p.id_proveedor
WHERE m.id_proveedor IS NULL;

-- 3) A partir de aqui, marcas.id_proveedor es obligatorio.
ALTER TABLE marcas MODIFY COLUMN id_proveedor INT NOT NULL;

SELECT 'listo: marcas enlazadas estrictamente a proveedores' AS resultado;
