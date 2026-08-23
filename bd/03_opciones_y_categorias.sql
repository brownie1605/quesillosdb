-- ============================================================================
-- QUESILLOS LO NUESTRO - Personalizacion de recetas (opciones y exclusiones)
-- Aplicar en LOCAL y en la NUBE (Railway).
-- Agrega:
--   1. receta_ingredientes.excluible  -> el cliente puede pedir quitarlo
--      (ej. "quesillo sin cebolla") sin editar la receta.
--   2. receta_opciones_grupo / receta_opciones_item -> grupos de eleccion
--      unica (ej. "Proteina: salsa ranchera / jamon / chorizo criollo").
--   3. detalle_ventas.personalizacion / comentario -> que eligio el cliente
--      en esa linea de venta, para verlo en el carrito y el ticket.
-- Es idempotente: puede ejecutarse varias veces sin romper nada.
-- ============================================================================

SET @db := DATABASE();

-- ---------------------------------------------------------------------------
-- 1. receta_ingredientes.excluible
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='receta_ingredientes'
                  AND COLUMN_NAME='excluible') = 0,
  'ALTER TABLE receta_ingredientes ADD COLUMN excluible BOOLEAN DEFAULT FALSE AFTER opcional',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- ---------------------------------------------------------------------------
-- 2. Grupos de opciones
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS receta_opciones_grupo (
    id_grupo INT AUTO_INCREMENT PRIMARY KEY,
    id_receta INT NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    obligatorio BOOLEAN DEFAULT TRUE,
    orden INT DEFAULT 0,
    estado_sync ENUM('pendiente','sinc_local','sinc_remoto') DEFAULT 'pendiente',
    CONSTRAINT fk_opgrupo_receta FOREIGN KEY (id_receta) REFERENCES recetas(id_receta) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS receta_opciones_item (
    id_item INT AUTO_INCREMENT PRIMARY KEY,
    id_grupo INT NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    id_producto_insumo INT NULL,
    cantidad DECIMAL(12,4) DEFAULT 0,
    es_default BOOLEAN DEFAULT FALSE,
    orden INT DEFAULT 0,
    estado_sync ENUM('pendiente','sinc_local','sinc_remoto') DEFAULT 'pendiente',
    CONSTRAINT fk_opitem_grupo FOREIGN KEY (id_grupo) REFERENCES receta_opciones_grupo(id_grupo) ON DELETE CASCADE,
    CONSTRAINT fk_opitem_insumo FOREIGN KEY (id_producto_insumo) REFERENCES productos(id_producto)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 3. detalle_ventas: que eligio el cliente en esa linea
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='detalle_ventas'
                  AND COLUMN_NAME='personalizacion') = 0,
  'ALTER TABLE detalle_ventas ADD COLUMN personalizacion JSON NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='detalle_ventas'
                  AND COLUMN_NAME='comentario') = 0,
  'ALTER TABLE detalle_ventas ADD COLUMN comentario VARCHAR(500) NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT 'listo: opciones de receta y comentarios de venta al dia' AS resultado;
