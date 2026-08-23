-- ============================================================================
-- QUESILLOS LO NUESTRO - Alinea ENUMs de la nube con el esquema local
-- Aplicar SOLO en la NUBE (Railway) -- el local ya tiene estos valores.
-- Es idempotente (MODIFY COLUMN no falla si ya esta asi).
-- ============================================================================

-- ventas.estado: a la nube le faltaba 'pendiente' (cuenta abierta de mesa).
-- Sin esto, cualquier venta de mesa fallaba al sincronizar con
-- "Data truncated for column 'estado'" y se quedaba trabada en conflicto.
ALTER TABLE ventas
    MODIFY COLUMN estado ENUM('completada','anulada','pendiente') DEFAULT 'completada';

-- compras.estado: local y nube tenian conjuntos de valores distintos
-- ('cancelada' vs 'pendiente'/'anulada'). Se deja un superset que acepta
-- los valores de ambos lados para que no truene sin importar cual se use.
ALTER TABLE compras
    MODIFY COLUMN estado ENUM('completada','cancelada','pendiente','anulada') DEFAULT 'completada';

SELECT 'listo: enums de la nube alineados' AS resultado;
