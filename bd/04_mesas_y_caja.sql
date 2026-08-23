-- ============================================================================
-- QUESILLOS LO NUESTRO - Mesas (flujo Mesas -> Pedido -> Cobrar)
-- Aplicar en LOCAL y en la NUBE (Railway).
-- Es idempotente: puede ejecutarse varias veces sin romper nada.
-- ============================================================================

SET @db := DATABASE();

-- ---------------------------------------------------------------------------
-- 1. Tabla mesas
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mesas (
    id_mesa INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT DEFAULT 1,
    nombre VARCHAR(50) NOT NULL,
    tipo ENUM('mesa','barra','llevar') DEFAULT 'mesa',
    capacidad INT DEFAULT 4,
    estado ENUM('libre','ocupada') DEFAULT 'libre',
    id_venta_actual INT NULL,
    orden INT DEFAULT 0,
    activa BOOLEAN DEFAULT TRUE,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    estado_sync ENUM('pendiente','sinc_local','sinc_remoto') DEFAULT 'pendiente'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 2. ventas.id_mesa (cuenta abierta ligada a una mesa)
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ventas'
                  AND COLUMN_NAME='id_mesa') = 0,
  'ALTER TABLE ventas ADD COLUMN id_mesa INT NULL AFTER id_cliente',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------------------------------------------------------------------
-- 3. Semilla: 13 mesas + Para llevar + 5 puestos de barra (solo si esta vacia)
-- ---------------------------------------------------------------------------
SET @hay_mesas := (SELECT COUNT(*) FROM mesas);

INSERT INTO mesas (nombre, tipo, capacidad, orden)
SELECT * FROM (
    SELECT 'Mesa 1' , 'mesa', 4, 1  UNION ALL SELECT 'Mesa 2' , 'mesa', 4, 2
    UNION ALL SELECT 'Mesa 3' , 'mesa', 4, 3  UNION ALL SELECT 'Mesa 4' , 'mesa', 4, 4
    UNION ALL SELECT 'Mesa 5' , 'mesa', 4, 5  UNION ALL SELECT 'Mesa 6' , 'mesa', 4, 6
    UNION ALL SELECT 'Mesa 7' , 'mesa', 4, 7  UNION ALL SELECT 'Mesa 8' , 'mesa', 4, 8
    UNION ALL SELECT 'Mesa 9' , 'mesa', 4, 9  UNION ALL SELECT 'Mesa 10', 'mesa', 4, 10
    UNION ALL SELECT 'Mesa 11', 'mesa', 4, 11 UNION ALL SELECT 'Mesa 12', 'mesa', 4, 12
    UNION ALL SELECT 'Mesa 13', 'mesa', 4, 13
    UNION ALL SELECT 'Para llevar', 'llevar', 1, 14
    UNION ALL SELECT 'Barra 1', 'barra', 1, 15 UNION ALL SELECT 'Barra 2', 'barra', 1, 16
    UNION ALL SELECT 'Barra 3', 'barra', 1, 17 UNION ALL SELECT 'Barra 4', 'barra', 1, 18
    UNION ALL SELECT 'Barra 5', 'barra', 1, 19
) AS semilla(nombre, tipo, capacidad, orden)
WHERE @hay_mesas = 0;

SELECT 'listo: mesas al dia' AS resultado;
