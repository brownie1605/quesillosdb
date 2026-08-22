-- ============================================================================
-- QUESILLOS LO NUESTRO - Actualizacion de la base de datos EN LA NUBE
-- Aplicar sobre: pos_inventario_cloud (Railway)
-- Agrega: recetas, insumos, infraestructura de sincronizacion y recuperacion
--         de contrasena por codigo de 6 digitos.
-- Es idempotente: puede ejecutarse varias veces sin romper nada.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. PRODUCTOS: clasificacion final / insumo / material
-- ---------------------------------------------------------------------------
SET @db := DATABASE();

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='tipo_producto') = 0,
  'ALTER TABLE productos ADD COLUMN tipo_producto ENUM(''final'',''insumo'',''material'') NOT NULL DEFAULT ''final'' AFTER aplica_impuesto',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='es_receta') = 0,
  'ALTER TABLE productos ADD COLUMN es_receta BOOLEAN DEFAULT FALSE AFTER tipo_producto',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='es_ingrediente_receta') = 0,
  'ALTER TABLE productos ADD COLUMN es_ingrediente_receta BOOLEAN DEFAULT FALSE AFTER es_receta',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='se_vende') = 0,
  'ALTER TABLE productos ADD COLUMN se_vende BOOLEAN DEFAULT TRUE AFTER es_ingrediente_receta',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='fecha_actualizacion') = 0,
  'ALTER TABLE productos ADD COLUMN fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='productos'
                  AND COLUMN_NAME='estado_sync') = 0,
  'ALTER TABLE productos ADD COLUMN estado_sync ENUM(''pendiente'',''sinc_local'',''sinc_remoto'') DEFAULT ''pendiente''',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;


-- ---------------------------------------------------------------------------
-- 2. RECETAS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recetas (
    id_receta INT AUTO_INCREMENT PRIMARY KEY,
    id_producto INT NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    modo_preparacion TEXT,
    tiempo_preparacion INT,
    rendimiento DECIMAL(12,2) DEFAULT 1,
    id_unidad_rendimiento INT,
    costo_total DECIMAL(12,2) DEFAULT 0,
    estado ENUM('activo','inactivo') DEFAULT 'activo',
    creado_por INT,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    estado_sync ENUM('pendiente','sinc_local','sinc_remoto') DEFAULT 'pendiente',
    UNIQUE KEY uk_receta_producto (id_producto),
    CONSTRAINT fk_receta_producto FOREIGN KEY (id_producto) REFERENCES productos(id_producto),
    CONSTRAINT fk_receta_unidad FOREIGN KEY (id_unidad_rendimiento) REFERENCES unidades_medida(id_unidad),
    CONSTRAINT fk_receta_usuario FOREIGN KEY (creado_por) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS receta_ingredientes (
    id_ingrediente INT AUTO_INCREMENT PRIMARY KEY,
    id_receta INT NOT NULL,
    id_producto INT NOT NULL,
    cantidad_necesaria DECIMAL(12,4) NOT NULL,
    id_unidad INT,
    costo_estimado DECIMAL(12,2) DEFAULT 0,
    opcional BOOLEAN DEFAULT FALSE,
    UNIQUE KEY uk_receta_ingrediente (id_receta, id_producto),
    CONSTRAINT fk_ing_receta FOREIGN KEY (id_receta) REFERENCES recetas(id_receta) ON DELETE CASCADE,
    CONSTRAINT fk_ing_producto FOREIGN KEY (id_producto) REFERENCES productos(id_producto),
    CONSTRAINT fk_ing_unidad FOREIGN KEY (id_unidad) REFERENCES unidades_medida(id_unidad)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- 3. INFRAESTRUCTURA DE SINCRONIZACION
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_queue (
    id_sync_queue INT AUTO_INCREMENT PRIMARY KEY,
    operation_type ENUM('INSERT','UPDATE','DELETE') NOT NULL,
    tabla_afectada VARCHAR(100) NOT NULL,
    registro_id INT NOT NULL,
    id_empresa INT NOT NULL DEFAULT 1,
    timestamp_operacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    timestamp_sincronizacion DATETIME,
    estado_sync ENUM('pendiente','sinc_local','sinc_remoto','en_conflicto','resuelto','error')
        NOT NULL DEFAULT 'pendiente',
    payload JSON,
    usuario_origen INT,
    dispositivo_origen VARCHAR(100),
    checksum_datos VARCHAR(64),
    intentos INT DEFAULT 0,
    ultimo_error TEXT,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tabla_estado (tabla_afectada, estado_sync),
    INDEX idx_timestamp_operacion (timestamp_operacion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS conflict_log (
    id_conflicto INT AUTO_INCREMENT PRIMARY KEY,
    tabla_afectada VARCHAR(100) NOT NULL,
    registro_id INT NOT NULL,
    id_empresa INT NOT NULL DEFAULT 1,
    timestamp_deteccion DATETIME DEFAULT CURRENT_TIMESTAMP,
    datos_local JSON,
    timestamp_local DATETIME,
    usuario_local INT,
    datos_remoto JSON,
    timestamp_remoto DATETIME,
    usuario_remoto INT,
    tipo_conflicto ENUM('venta_simultanea','update_simultaneo','delete_conflict','stock','otro')
        DEFAULT 'otro',
    estado_resolucion ENUM('pendiente_resolucion','resuelto_auto','resuelto_manual')
        DEFAULT 'pendiente_resolucion',
    resolucion_tipo ENUM('prioridad_local','prioridad_remoto','merge','manual') DEFAULT 'manual',
    datos_resueltos JSON,
    resuelto_por INT,
    fecha_resolucion DATETIME,
    notas_resolucion TEXT,
    notificado BOOLEAN DEFAULT FALSE,
    INDEX idx_estado_resolucion (estado_resolucion),
    INDEX idx_tabla_registro (tabla_afectada, registro_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sync_metadata (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tabla_nombre VARCHAR(100) NOT NULL UNIQUE,
    ultima_sincronizacion DATETIME,
    ultimo_pull DATETIME,
    ultimo_push DATETIME,
    version_remota INT DEFAULT 0,
    version_local INT DEFAULT 0,
    registros_sincronizados INT DEFAULT 0,
    estado ENUM('sincronizado','pendiente','error') DEFAULT 'pendiente',
    mensaje TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- 4. VENTAS: trazabilidad para la sincronizacion y resolucion de conflictos
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ventas' AND COLUMN_NAME='uuid_venta')=0,
  'ALTER TABLE ventas ADD COLUMN uuid_venta VARCHAR(36) NULL, ADD UNIQUE KEY uk_ventas_uuid (uuid_venta)',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ventas' AND COLUMN_NAME='origen')=0,
  'ALTER TABLE ventas ADD COLUMN origen ENUM(''local'',''nube'') DEFAULT ''local''',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ventas' AND COLUMN_NAME='timestamp_local_creacion')=0,
  'ALTER TABLE ventas ADD COLUMN timestamp_local_creacion DATETIME DEFAULT CURRENT_TIMESTAMP',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ventas' AND COLUMN_NAME='timestamp_local_actualizacion')=0,
  'ALTER TABLE ventas ADD COLUMN timestamp_local_actualizacion DATETIME NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ventas' AND COLUMN_NAME='estado_sync')=0,
  'ALTER TABLE ventas ADD COLUMN estado_sync ENUM(''pendiente'',''sinc_local'',''sinc_remoto'',''en_conflicto'') DEFAULT ''pendiente''',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ventas' AND COLUMN_NAME='motivo_anulacion')=0,
  'ALTER TABLE ventas ADD COLUMN motivo_anulacion VARCHAR(255) NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='detalle_ventas' AND COLUMN_NAME='consumio_receta')=0,
  'ALTER TABLE detalle_ventas ADD COLUMN consumio_receta BOOLEAN DEFAULT FALSE',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='detalle_ventas' AND COLUMN_NAME='timestamp_local_creacion')=0,
  'ALTER TABLE detalle_ventas ADD COLUMN timestamp_local_creacion DATETIME DEFAULT CURRENT_TIMESTAMP',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='detalle_ventas' AND COLUMN_NAME='estado_sync')=0,
  'ALTER TABLE detalle_ventas ADD COLUMN estado_sync ENUM(''pendiente'',''sinc_local'',''sinc_remoto'') DEFAULT ''pendiente''',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;


-- ---------------------------------------------------------------------------
-- 5. INVENTARIO Y MOVIMIENTOS
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='inventario' AND COLUMN_NAME='estado_sync')=0,
  'ALTER TABLE inventario ADD COLUMN estado_sync ENUM(''pendiente'',''sinc_local'',''sinc_remoto'') DEFAULT ''pendiente''',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='movimientos_inventario' AND COLUMN_NAME='estado_sync')=0,
  'ALTER TABLE movimientos_inventario ADD COLUMN estado_sync ENUM(''pendiente'',''sinc_local'',''sinc_remoto'') DEFAULT ''pendiente''',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='movimientos_inventario' AND COLUMN_NAME='timestamp_operacion')=0,
  'ALTER TABLE movimientos_inventario ADD COLUMN timestamp_operacion DATETIME DEFAULT CURRENT_TIMESTAMP',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 'receta' como nuevo tipo de movimiento (consumo de insumos por preparacion)
ALTER TABLE movimientos_inventario
  MODIFY COLUMN tipo_movimiento
  ENUM('entrada','salida','ajuste','venta','compra','devolucion','receta') NOT NULL;


-- ---------------------------------------------------------------------------
-- 6. USUARIOS: recuperacion de contrasena por codigo de 6 digitos
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='usuarios' AND COLUMN_NAME='codigo_recuperacion')=0,
  'ALTER TABLE usuarios ADD COLUMN codigo_recuperacion VARCHAR(6) NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='usuarios' AND COLUMN_NAME='codigo_expiry')=0,
  'ALTER TABLE usuarios ADD COLUMN codigo_expiry DATETIME NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='usuarios' AND COLUMN_NAME='estado_sync')=0,
  'ALTER TABLE usuarios ADD COLUMN estado_sync ENUM(''pendiente'',''sinc_local'',''sinc_remoto'') DEFAULT ''pendiente''',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

CREATE TABLE IF NOT EXISTS recuperacion_password (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    codigo VARCHAR(6) NOT NULL,
    fecha_expiracion DATETIME NOT NULL,
    usado BOOLEAN DEFAULT FALSE,
    CONSTRAINT fk_recuperacion_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- 7. NOTIFICACIONES: url de accion
-- ---------------------------------------------------------------------------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='notificaciones' AND COLUMN_NAME='url_accion')=0,
  'ALTER TABLE notificaciones ADD COLUMN url_accion VARCHAR(255) NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;


-- ---------------------------------------------------------------------------
-- 8. ROLES DEL NEGOCIO
-- ---------------------------------------------------------------------------
INSERT INTO roles (id_empresa, nombre, descripcion, estado)
SELECT 1, 'Admin', 'Acceso total al sistema', 'activo'
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'Admin');

INSERT INTO roles (id_empresa, nombre, descripcion, estado)
SELECT 1, 'Cajero', 'Ventas, cobros y manejo de caja', 'activo'
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'Cajero');

INSERT INTO roles (id_empresa, nombre, descripcion, estado)
SELECT 1, 'Mesero', 'Toma de ordenes y ventas', 'activo'
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'Mesero');

INSERT INTO roles (id_empresa, nombre, descripcion, estado)
SELECT 1, 'Cocinero', 'Recetas, insumos y ordenes de cocina', 'activo'
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'Cocinero');


-- ---------------------------------------------------------------------------
-- 9. UNIDADES DE MEDIDA usadas por las recetas
-- ---------------------------------------------------------------------------
INSERT INTO unidades_medida (nombre, abreviatura, estado)
SELECT * FROM (SELECT 'Unidad' n, 'und' a, 'activo' e) t
WHERE NOT EXISTS (SELECT 1 FROM unidades_medida WHERE abreviatura='und');
INSERT INTO unidades_medida (nombre, abreviatura, estado)
SELECT * FROM (SELECT 'Docena', 'doc', 'activo') t
WHERE NOT EXISTS (SELECT 1 FROM unidades_medida WHERE abreviatura='doc');
INSERT INTO unidades_medida (nombre, abreviatura, estado)
SELECT * FROM (SELECT 'Libra', 'lb', 'activo') t
WHERE NOT EXISTS (SELECT 1 FROM unidades_medida WHERE abreviatura='lb');
INSERT INTO unidades_medida (nombre, abreviatura, estado)
SELECT * FROM (SELECT 'Onza', 'oz', 'activo') t
WHERE NOT EXISTS (SELECT 1 FROM unidades_medida WHERE abreviatura='oz');
INSERT INTO unidades_medida (nombre, abreviatura, estado)
SELECT * FROM (SELECT 'Litro', 'L', 'activo') t
WHERE NOT EXISTS (SELECT 1 FROM unidades_medida WHERE abreviatura='L');
INSERT INTO unidades_medida (nombre, abreviatura, estado)
SELECT * FROM (SELECT 'Mililitro', 'ml', 'activo') t
WHERE NOT EXISTS (SELECT 1 FROM unidades_medida WHERE abreviatura='ml');
INSERT INTO unidades_medida (nombre, abreviatura, estado)
SELECT * FROM (SELECT 'Gramo', 'g', 'activo') t
WHERE NOT EXISTS (SELECT 1 FROM unidades_medida WHERE abreviatura='g');
INSERT INTO unidades_medida (nombre, abreviatura, estado)
SELECT * FROM (SELECT 'Kilogramo', 'kg', 'activo') t
WHERE NOT EXISTS (SELECT 1 FROM unidades_medida WHERE abreviatura='kg');
INSERT INTO unidades_medida (nombre, abreviatura, estado)
SELECT * FROM (SELECT 'Porcion', 'porc', 'activo') t
WHERE NOT EXISTS (SELECT 1 FROM unidades_medida WHERE abreviatura='porc');

-- FIN
SELECT 'Actualizacion de la nube completada' AS resultado;
