CREATE DATABASE IF NOT EXISTS pos_inventario_cloud
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE pos_inventario_cloud;

-- =========================
-- 1. EMPRESAS
-- =========================

CREATE TABLE empresas (
    id_empresa INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    ruc VARCHAR(30),
    telefono VARCHAR(30),
    correo VARCHAR(100),
    direccion TEXT,
    logo_url VARCHAR(255),
    estado ENUM('activo', 'inactivo') DEFAULT 'activo',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sucursales (
    id_sucursal INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    telefono VARCHAR(30),
    direccion TEXT,
    estado ENUM('activo', 'inactivo') DEFAULT 'activo',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa)
);

-- =========================
-- 2. SEGURIDAD
-- =========================

CREATE TABLE roles (
    id_rol INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT,
    estado ENUM('activo', 'inactivo') DEFAULT 'activo',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa)
);

CREATE TABLE permisos (
    id_permiso INT AUTO_INCREMENT PRIMARY KEY,
    modulo VARCHAR(100) NOT NULL,
    accion VARCHAR(100) NOT NULL,
    descripcion TEXT
);

CREATE TABLE rol_permiso (
    id_rol_permiso INT AUTO_INCREMENT PRIMARY KEY,
    id_rol INT NOT NULL,
    id_permiso INT NOT NULL,
    FOREIGN KEY (id_rol) REFERENCES roles(id_rol),
    FOREIGN KEY (id_permiso) REFERENCES permisos(id_permiso)
);

CREATE TABLE usuarios (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    id_sucursal INT,
    id_rol INT NOT NULL,
    usuario VARCHAR(80) NOT NULL,
    nombre_completo VARCHAR(150) NOT NULL,
    correo VARCHAR(100),
    telefono VARCHAR(30),
    password_hash VARCHAR(255) NOT NULL,
    imagen_url VARCHAR(255),
    estado ENUM('activo', 'inactivo', 'bloqueado') DEFAULT 'activo',
    ultimo_acceso DATETIME,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_usuario_empresa (id_empresa, usuario),
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa),
    FOREIGN KEY (id_sucursal) REFERENCES sucursales(id_sucursal),
    FOREIGN KEY (id_rol) REFERENCES roles(id_rol)
);

CREATE TABLE historial_login (
    id_login INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    ip VARCHAR(50),
    dispositivo VARCHAR(150),
    navegador VARCHAR(150),
    estado ENUM('exitoso', 'fallido') NOT NULL,
    fecha_login DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

-- =========================
-- 3. CATÁLOGOS
-- =========================

CREATE TABLE categorias (
    id_categoria INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT,
    estado ENUM('activo', 'inactivo') DEFAULT 'activo',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa)
);

CREATE TABLE marcas (
    id_marca INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    estado ENUM('activo', 'inactivo') DEFAULT 'activo',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa)
);

CREATE TABLE unidades_medida (
    id_unidad INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    abreviatura VARCHAR(20),
    estado ENUM('activo', 'inactivo') DEFAULT 'activo'
);

CREATE TABLE metodos_pago (
    id_metodo_pago INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    estado ENUM('activo', 'inactivo') DEFAULT 'activo'
);

-- =========================
-- 4. PRODUCTOS E INVENTARIO
-- =========================

CREATE TABLE productos (
    id_producto INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    id_categoria INT NOT NULL,
    id_marca INT,
    id_unidad INT,
    codigo VARCHAR(80) NOT NULL,
    codigo_barra VARCHAR(100),
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    precio_compra DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    precio_venta DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    imagen_url VARCHAR(255),
    aplica_impuesto BOOLEAN DEFAULT FALSE,
    estado ENUM('activo', 'inactivo') DEFAULT 'activo',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_codigo_empresa (id_empresa, codigo),
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa),
    FOREIGN KEY (id_categoria) REFERENCES categorias(id_categoria),
    FOREIGN KEY (id_marca) REFERENCES marcas(id_marca),
    FOREIGN KEY (id_unidad) REFERENCES unidades_medida(id_unidad)
);

CREATE TABLE inventario (
    id_inventario INT AUTO_INCREMENT PRIMARY KEY,
    id_producto INT NOT NULL,
    id_sucursal INT NOT NULL,
    stock_actual DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    stock_minimo DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    stock_maximo DECIMAL(12,2) DEFAULT 0.00,
    fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_producto_sucursal (id_producto, id_sucursal),
    FOREIGN KEY (id_producto) REFERENCES productos(id_producto),
    FOREIGN KEY (id_sucursal) REFERENCES sucursales(id_sucursal)
);

-- =========================
-- 5. CLIENTES Y PROVEEDORES
-- =========================

CREATE TABLE clientes (
    id_cliente INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    cedula VARCHAR(30),
    telefono VARCHAR(30),
    direccion TEXT,
    estado ENUM('activo', 'inactivo') DEFAULT 'activo',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa)
);

CREATE TABLE proveedores (
    id_proveedor INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    ruc VARCHAR(30),
    telefono VARCHAR(30),
    correo VARCHAR(100),
    direccion TEXT,
    estado ENUM('activo', 'inactivo') DEFAULT 'activo',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa)
);

-- =========================
-- 6. VENTAS
-- =========================

CREATE TABLE ventas (
    id_venta INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    id_sucursal INT NOT NULL,
    id_usuario INT NOT NULL,
    id_cliente INT,
    numero_venta VARCHAR(50) NOT NULL,
    subtotal DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    descuento DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    impuesto DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    total DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    monto_recibido DECIMAL(12,2) DEFAULT 0.00,
    cambio DECIMAL(12,2) DEFAULT 0.00,
    estado ENUM('completada', 'anulada') DEFAULT 'completada',
    fecha_venta DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_numero_venta_empresa (id_empresa, numero_venta),
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa),
    FOREIGN KEY (id_sucursal) REFERENCES sucursales(id_sucursal),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
);

CREATE TABLE detalle_ventas (
    id_detalle_venta INT AUTO_INCREMENT PRIMARY KEY,
    id_venta INT NOT NULL,
    id_producto INT NOT NULL,
    cantidad DECIMAL(12,2) NOT NULL,
    precio_unitario DECIMAL(12,2) NOT NULL,
    descuento DECIMAL(12,2) DEFAULT 0.00,
    subtotal DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (id_venta) REFERENCES ventas(id_venta),
    FOREIGN KEY (id_producto) REFERENCES productos(id_producto)
);

CREATE TABLE pagos_venta (
    id_pago_venta INT AUTO_INCREMENT PRIMARY KEY,
    id_venta INT NOT NULL,
    id_metodo_pago INT NOT NULL,
    monto DECIMAL(12,2) NOT NULL,
    referencia VARCHAR(100),
    fecha_pago DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_venta) REFERENCES ventas(id_venta),
    FOREIGN KEY (id_metodo_pago) REFERENCES metodos_pago(id_metodo_pago)
);

-- =========================
-- 7. COMPRAS
-- =========================

CREATE TABLE compras (
    id_compra INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    id_sucursal INT NOT NULL,
    id_usuario INT NOT NULL,
    id_proveedor INT NOT NULL,
    numero_compra VARCHAR(50) NOT NULL,
    subtotal DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    impuesto DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    total DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    estado ENUM('pendiente', 'completada', 'anulada') DEFAULT 'completada',
    fecha_compra DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_numero_compra_empresa (id_empresa, numero_compra),
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa),
    FOREIGN KEY (id_sucursal) REFERENCES sucursales(id_sucursal),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_proveedor) REFERENCES proveedores(id_proveedor)
);

CREATE TABLE detalle_compras (
    id_detalle_compra INT AUTO_INCREMENT PRIMARY KEY,
    id_compra INT NOT NULL,
    id_producto INT NOT NULL,
    cantidad DECIMAL(12,2) NOT NULL,
    precio_unitario DECIMAL(12,2) NOT NULL,
    subtotal DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (id_compra) REFERENCES compras(id_compra),
    FOREIGN KEY (id_producto) REFERENCES productos(id_producto)
);

-- =========================
-- 8. MOVIMIENTOS DE INVENTARIO
-- =========================

CREATE TABLE movimientos_inventario (
    id_movimiento INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    id_sucursal INT NOT NULL,
    id_producto INT NOT NULL,
    id_usuario INT NOT NULL,
    tipo_movimiento ENUM('entrada', 'salida', 'ajuste', 'venta', 'compra', 'devolucion') NOT NULL,
    cantidad DECIMAL(12,2) NOT NULL,
    stock_anterior DECIMAL(12,2) NOT NULL,
    stock_nuevo DECIMAL(12,2) NOT NULL,
    referencia VARCHAR(100),
    observacion TEXT,
    fecha_movimiento DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa),
    FOREIGN KEY (id_sucursal) REFERENCES sucursales(id_sucursal),
    FOREIGN KEY (id_producto) REFERENCES productos(id_producto),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

-- =========================
-- 9. CAJA
-- =========================

CREATE TABLE cajas (
    id_caja INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    id_sucursal INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    estado ENUM('activa', 'inactiva') DEFAULT 'activa',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa),
    FOREIGN KEY (id_sucursal) REFERENCES sucursales(id_sucursal)
);

CREATE TABLE aperturas_caja (
    id_apertura INT AUTO_INCREMENT PRIMARY KEY,
    id_caja INT NOT NULL,
    id_usuario INT NOT NULL,
    monto_inicial DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    estado ENUM('abierta', 'cerrada') DEFAULT 'abierta',
    fecha_apertura DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_caja) REFERENCES cajas(id_caja),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE movimientos_caja (
    id_movimiento_caja INT AUTO_INCREMENT PRIMARY KEY,
    id_apertura INT NOT NULL,
    id_usuario INT NOT NULL,
    tipo_movimiento ENUM('ingreso', 'egreso', 'venta', 'retiro', 'ajuste') NOT NULL,
    monto DECIMAL(12,2) NOT NULL,
    descripcion TEXT,
    referencia VARCHAR(100),
    fecha_movimiento DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_apertura) REFERENCES aperturas_caja(id_apertura),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE cierres_caja (
    id_cierre INT AUTO_INCREMENT PRIMARY KEY,
    id_apertura INT NOT NULL,
    id_usuario INT NOT NULL,
    monto_inicial DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    total_ingresos DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    total_egresos DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    total_ventas DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    monto_esperado DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    monto_real DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    diferencia DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    observacion TEXT,
    fecha_cierre DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_apertura) REFERENCES aperturas_caja(id_apertura),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

-- =========================
-- 10. CONFIGURACIÓN, NOTIFICACIONES Y AUDITORÍA
-- =========================

CREATE TABLE configuraciones (
    id_configuracion INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    clave VARCHAR(100) NOT NULL,
    valor TEXT,
    descripcion TEXT,
    fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_config_empresa (id_empresa, clave),
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa)
);

CREATE TABLE notificaciones (
    id_notificacion INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    id_usuario INT,
    titulo VARCHAR(150) NOT NULL,
    mensaje TEXT NOT NULL,
    tipo ENUM('info', 'warning', 'success', 'error') DEFAULT 'info',
    leida BOOLEAN DEFAULT FALSE,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE auditoria (
    id_auditoria INT AUTO_INCREMENT PRIMARY KEY,
    id_empresa INT NOT NULL,
    id_usuario INT,
    tabla_afectada VARCHAR(100) NOT NULL,
    accion ENUM('crear', 'actualizar', 'eliminar', 'anular', 'login') NOT NULL,
    descripcion TEXT,
    datos_anteriores JSON,
    datos_nuevos JSON,
    fecha_accion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);














USE pos_inventario_cloud;

-- =========================
-- EMPRESA DEMO
-- =========================

INSERT INTO empresas (
    nombre,
    ruc,
    telefono,
    correo,
    direccion,
    logo_url
)
VALUES (
    'POS Inventario Cloud Demo',
    'J031000000001',
    '8888-8888',
    'admin@poscloud.com',
    'Managua, Nicaragua',
    'https://via.placeholder.com/300x300.png'
);

-- =========================
-- SUCURSALES
-- =========================

INSERT INTO sucursales (
    id_empresa,
    nombre,
    telefono,
    direccion
)
VALUES
(1, 'Sucursal Central', '8888-1111', 'Managua'),
(1, 'Sucursal León', '8888-2222', 'León');

-- =========================
-- ROLES
-- =========================

INSERT INTO roles (
    id_empresa,
    nombre,
    descripcion
)
VALUES
(1, 'Administrador', 'Acceso completo al sistema'),
(1, 'Cajero', 'Gestión de ventas y caja'),
(1, 'Inventario', 'Gestión de productos e inventario');

-- =========================
-- PERMISOS
-- =========================

INSERT INTO permisos (
    modulo,
    accion,
    descripcion
)
VALUES
('dashboard', 'ver', 'Ver dashboard'),
('usuarios', 'crear', 'Crear usuarios'),
('usuarios', 'editar', 'Editar usuarios'),
('usuarios', 'eliminar', 'Eliminar usuarios'),
('productos', 'crear', 'Crear productos'),
('productos', 'editar', 'Editar productos'),
('productos', 'eliminar', 'Eliminar productos'),
('inventario', 'ver', 'Ver inventario'),
('inventario', 'editar', 'Editar inventario'),
('ventas', 'crear', 'Registrar ventas'),
('ventas', 'anular', 'Anular ventas'),
('compras', 'crear', 'Registrar compras'),
('reportes', 'ver', 'Ver reportes'),
('caja', 'abrir', 'Abrir caja'),
('caja', 'cerrar', 'Cerrar caja');

-- =========================
-- ASIGNACIÓN DE PERMISOS
-- =========================

-- ADMINISTRADOR
INSERT INTO rol_permiso (id_rol, id_permiso)
SELECT 1, id_permiso FROM permisos;

-- CAJERO
INSERT INTO rol_permiso (id_rol, id_permiso)
VALUES
(2, 1),
(2, 10),
(2, 11),
(2, 14),
(2, 15);

-- INVENTARIO
INSERT INTO rol_permiso (id_rol, id_permiso)
VALUES
(3, 1),
(3, 5),
(3, 6),
(3, 8),
(3, 9),
(3, 12);

-- =========================
-- USUARIO ADMIN
-- PASSWORD DEMO: admin123
-- =========================

INSERT INTO usuarios (
    id_empresa,
    id_sucursal,
    id_rol,
    usuario,
    nombre_completo,
    correo,
    telefono,
    password_hash
)
VALUES (
    1,
    1,
    1,
    'admin',
    'Administrador General',
    'admin@poscloud.com',
    '8888-0000',
    '$2b$12$abcdefghijklmnopqrstuv'
);

-- =========================
-- CATEGORÍAS
-- =========================

INSERT INTO categorias (
    id_empresa,
    nombre,
    descripcion
)
VALUES
(1, 'Bebidas', 'Productos líquidos y refrescos'),
(1, 'Snacks', 'Productos de consumo rápido'),
(1, 'Lácteos', 'Productos derivados de leche'),
(1, 'Limpieza', 'Productos de limpieza');

-- =========================
-- MARCAS
-- =========================

INSERT INTO marcas (
    id_empresa,
    nombre
)
VALUES
(1, 'Coca Cola'),
(1, 'Nestlé'),
(1, 'Maggi'),
(1, 'La Perfecta');

-- =========================
-- UNIDADES DE MEDIDA
-- =========================

INSERT INTO unidades_medida (
    nombre,
    abreviatura
)
VALUES
('Unidad', 'UND'),
('Litro', 'LT'),
('Kilogramo', 'KG'),
('Caja', 'CJ');

-- =========================
-- MÉTODOS DE PAGO
-- =========================

INSERT INTO metodos_pago (
    nombre
)
VALUES
('Efectivo'),
('Tarjeta'),
('Transferencia'),
('Pago Móvil');

-- =========================
-- PRODUCTOS DEMO
-- =========================

INSERT INTO productos (
    id_empresa,
    id_categoria,
    id_marca,
    id_unidad,
    codigo,
    codigo_barra,
    nombre,
    descripcion,
    precio_compra,
    precio_venta,
    imagen_url
)
VALUES
(
    1,
    1,
    1,
    1,
    'P001',
    '750100000001',
    'Coca Cola 1L',
    'Refresco Coca Cola 1 litro',
    25.00,
    35.00,
    'https://via.placeholder.com/300x300.png'
),
(
    1,
    2,
    2,
    1,
    'P002',
    '750100000002',
    'Galletas Nestlé',
    'Galletas dulces',
    10.00,
    18.00,
    'https://via.placeholder.com/300x300.png'
),
(
    1,
    3,
    4,
    1,
    'P003',
    '750100000003',
    'Leche La Perfecta',
    'Leche entera',
    30.00,
    42.00,
    'https://via.placeholder.com/300x300.png'
);

-- =========================
-- INVENTARIO DEMO
-- =========================

INSERT INTO inventario (
    id_producto,
    id_sucursal,
    stock_actual,
    stock_minimo,
    stock_maximo
)
VALUES
(1, 1, 50, 10, 100),
(2, 1, 80, 15, 150),
(3, 1, 40, 8, 80),
(1, 2, 20, 10, 50),
(2, 2, 35, 10, 80);

-- =========================
-- CLIENTES DEMO
-- =========================

INSERT INTO clientes (
    id_empresa,
    nombre,
    cedula,
    telefono,
    direccion
)
VALUES
(
    1,
    'Cliente General',
    '000-000000-0000A',
    '8888-9999',
    'Managua'
),
(
    1,
    'Paulo Estrada',
    '001-000000-0001A',
    '8888-7777',
    'León'
);

-- =========================
-- PROVEEDORES DEMO
-- =========================

INSERT INTO proveedores (
    id_empresa,
    nombre,
    ruc,
    telefono,
    correo,
    direccion
)
VALUES
(
    1,
    'Distribuidora Central',
    'J031111111111',
    '8888-3333',
    'proveedor@demo.com',
    'Managua'
),
(
    1,
    'Nestlé Nicaragua',
    'J032222222222',
    '8888-4444',
    'ventas@nestle.com',
    'Managua'
);

-- =========================
-- CAJAS
-- =========================

INSERT INTO cajas (
    id_empresa,
    id_sucursal,
    nombre
)
VALUES
(1, 1, 'Caja Principal'),
(1, 2, 'Caja León');

-- =========================
-- CONFIGURACIONES
-- =========================

INSERT INTO configuraciones (
    id_empresa,
    clave,
    valor,
    descripcion
)
VALUES
(1, 'moneda', 'NIO', 'Moneda principal'),
(1, 'impuesto', '15', 'IVA del sistema'),
(1, 'nombre_negocio', 'POS Inventario Cloud Demo', 'Nombre comercial'),
(1, 'modo_oscuro', 'false', 'Modo oscuro del sistema');



USE pos_inventario_cloud;

-- =========================
-- 1. SUCURSALES CON EMPRESA
-- =========================

CREATE OR REPLACE VIEW vw_sucursales_empresa AS
SELECT
    s.id_sucursal,
    s.nombre AS sucursal,
    e.id_empresa,
    e.nombre AS empresa,
    s.telefono,
    s.direccion,
    s.estado,
    s.fecha_creacion
FROM sucursales s
INNER JOIN empresas e
    ON s.id_empresa = e.id_empresa;


-- =========================
-- 2. USUARIOS CON ROL Y SUCURSAL
-- =========================

CREATE OR REPLACE VIEW vw_usuarios_roles AS
SELECT
    u.id_usuario,
    u.id_empresa,
    e.nombre AS empresa,
    u.id_sucursal,
    s.nombre AS sucursal,
    u.id_rol,
    r.nombre AS rol,
    u.usuario,
    u.nombre_completo,
    u.correo,
    u.telefono,
    u.estado,
    u.ultimo_acceso,
    u.fecha_creacion
FROM usuarios u
INNER JOIN empresas e
    ON u.id_empresa = e.id_empresa
LEFT JOIN sucursales s
    ON u.id_sucursal = s.id_sucursal
INNER JOIN roles r
    ON u.id_rol = r.id_rol;


-- =========================
-- 3. PRODUCTOS DETALLE
-- =========================

CREATE OR REPLACE VIEW vw_productos_detalle AS
SELECT
    p.id_producto,
    p.id_empresa,
    e.nombre AS empresa,
    p.codigo,
    p.codigo_barra,
    p.nombre AS producto,
    p.descripcion,
    p.id_categoria,
    c.nombre AS categoria,
    p.id_marca,
    m.nombre AS marca,
    p.id_unidad,
    um.nombre AS unidad_medida,
    um.abreviatura,
    p.precio_compra,
    p.precio_venta,
    (p.precio_venta - p.precio_compra) AS ganancia_unitaria,
    p.imagen_url,
    p.aplica_impuesto,
    p.estado,
    p.fecha_creacion
FROM productos p
INNER JOIN empresas e
    ON p.id_empresa = e.id_empresa
INNER JOIN categorias c
    ON p.id_categoria = c.id_categoria
LEFT JOIN marcas m
    ON p.id_marca = m.id_marca
LEFT JOIN unidades_medida um
    ON p.id_unidad = um.id_unidad;


-- =========================
-- 4. INVENTARIO COMPLETO
-- =========================

CREATE OR REPLACE VIEW vw_inventario_completo AS
SELECT
    i.id_inventario,
    p.id_empresa,
    e.nombre AS empresa,
    i.id_sucursal,
    s.nombre AS sucursal,
    i.id_producto,
    p.codigo,
    p.codigo_barra,
    p.nombre AS producto,
    c.nombre AS categoria,
    m.nombre AS marca,
    i.stock_actual,
    i.stock_minimo,
    i.stock_maximo,
    p.precio_compra,
    p.precio_venta,
    (i.stock_actual * p.precio_compra) AS valor_stock_compra,
    (i.stock_actual * p.precio_venta) AS valor_stock_venta,
    (i.stock_actual * (p.precio_venta - p.precio_compra)) AS ganancia_potencial,
    CASE
        WHEN i.stock_actual <= i.stock_minimo THEN 'stock_bajo'
        WHEN i.stock_maximo > 0 AND i.stock_actual >= i.stock_maximo THEN 'stock_alto'
        ELSE 'stock_normal'
    END AS estado_stock,
    i.fecha_actualizacion
FROM inventario i
INNER JOIN productos p
    ON i.id_producto = p.id_producto
INNER JOIN empresas e
    ON p.id_empresa = e.id_empresa
INNER JOIN sucursales s
    ON i.id_sucursal = s.id_sucursal
INNER JOIN categorias c
    ON p.id_categoria = c.id_categoria
LEFT JOIN marcas m
    ON p.id_marca = m.id_marca;


-- =========================
-- 5. PRODUCTOS CON STOCK BAJO
-- =========================

CREATE OR REPLACE VIEW vw_productos_stock_bajo AS
SELECT
    id_inventario,
    id_empresa,
    empresa,
    id_sucursal,
    sucursal,
    id_producto,
    codigo,
    producto,
    categoria,
    marca,
    stock_actual,
    stock_minimo,
    estado_stock,
    fecha_actualizacion
FROM vw_inventario_completo
WHERE stock_actual <= stock_minimo;


-- =========================
-- 6. ROLES Y PERMISOS
-- =========================

CREATE OR REPLACE VIEW vw_roles_permisos AS
SELECT
    r.id_rol,
    r.id_empresa,
    e.nombre AS empresa,
    r.nombre AS rol,
    p.id_permiso,
    p.modulo,
    p.accion,
    p.descripcion
FROM rol_permiso rp
INNER JOIN roles r
    ON rp.id_rol = r.id_rol
INNER JOIN empresas e
    ON r.id_empresa = e.id_empresa
INNER JOIN permisos p
    ON rp.id_permiso = p.id_permiso;


-- =========================
-- 7. CAJAS POR SUCURSAL
-- =========================

CREATE OR REPLACE VIEW vw_cajas_sucursal AS
SELECT
    c.id_caja,
    c.id_empresa,
    e.nombre AS empresa,
    c.id_sucursal,
    s.nombre AS sucursal,
    c.nombre AS caja,
    c.estado,
    c.fecha_creacion
FROM cajas c
INNER JOIN empresas e
    ON c.id_empresa = e.id_empresa
INNER JOIN sucursales s
    ON c.id_sucursal = s.id_sucursal;


-- =========================
-- 8. VALOR TOTAL DEL INVENTARIO POR EMPRESA
-- =========================

CREATE OR REPLACE VIEW vw_valor_inventario_empresa AS
SELECT
    id_empresa,
    empresa,
    SUM(valor_stock_compra) AS valor_inventario_compra,
    SUM(valor_stock_venta) AS valor_inventario_venta
FROM vw_inventario_completo
GROUP BY id_empresa, empresa;


-- =========================
-- 9. VALOR TOTAL DEL INVENTARIO POR SUCURSAL
-- =========================

CREATE OR REPLACE VIEW vw_valor_inventario_sucursal AS
SELECT
    id_empresa,
    empresa,
    id_sucursal,
    sucursal,
    SUM(valor_stock_compra) AS valor_inventario_compra,
    SUM(valor_stock_venta) AS valor_inventario_venta,
    SUM(ganancia_potencial) AS ganancia_potencial
FROM vw_inventario_completo
GROUP BY id_empresa, empresa, id_sucursal, sucursal;


-- =========================
-- 10. GANANCIA POTENCIAL POR EMPRESA
-- =========================

CREATE OR REPLACE VIEW vw_ganancia_potencial_empresa AS
SELECT
    id_empresa,
    empresa,
    SUM(ganancia_potencial) AS ganancia_potencial
FROM vw_inventario_completo
GROUP BY id_empresa, empresa;


-- =========================
-- 11. DASHBOARD GENERAL POR EMPRESA
-- =========================

CREATE OR REPLACE VIEW vw_dashboard_general_empresa AS
SELECT
    e.id_empresa,
    e.nombre AS empresa,

    COUNT(DISTINCT p.id_producto) AS total_productos,
    COUNT(DISTINCT c.id_cliente) AS total_clientes,
    COUNT(DISTINCT pr.id_proveedor) AS total_proveedores,
    COUNT(DISTINCT u.id_usuario) AS total_usuarios,
    COUNT(DISTINCT s.id_sucursal) AS total_sucursales,

    COALESCE(SUM(i.stock_actual), 0) AS unidades_inventario,
    COALESCE(SUM(i.stock_actual * p.precio_compra), 0) AS valor_inventario_compra,
    COALESCE(SUM(i.stock_actual * p.precio_venta), 0) AS valor_inventario_venta,
    COALESCE(SUM(i.stock_actual * (p.precio_venta - p.precio_compra)), 0) AS ganancia_potencial,

    COUNT(DISTINCT CASE
        WHEN i.stock_actual <= i.stock_minimo THEN i.id_producto
    END) AS productos_stock_bajo

FROM empresas e
LEFT JOIN productos p
    ON e.id_empresa = p.id_empresa
LEFT JOIN inventario i
    ON p.id_producto = i.id_producto
LEFT JOIN clientes c
    ON e.id_empresa = c.id_empresa
LEFT JOIN proveedores pr
    ON e.id_empresa = pr.id_empresa
LEFT JOIN usuarios u
    ON e.id_empresa = u.id_empresa
LEFT JOIN sucursales s
    ON e.id_empresa = s.id_empresa
GROUP BY e.id_empresa, e.nombre;


-- =========================
-- 12. PRODUCTOS MÁS CAROS
-- =========================

CREATE OR REPLACE VIEW vw_productos_mas_caros AS
SELECT
    id_empresa,
    empresa,
    id_producto,
    codigo,
    producto,
    categoria,
    marca,
    precio_venta
FROM vw_productos_detalle
ORDER BY precio_venta DESC;


-- =========================
-- 13. CLIENTES DETALLE
-- =========================

CREATE OR REPLACE VIEW vw_clientes_detalle AS
SELECT
    c.id_cliente,
    c.id_empresa,
    e.nombre AS empresa,
    c.nombre,
    c.cedula,
    c.telefono,
    c.direccion,
    c.estado,
    c.fecha_creacion
FROM clientes c
INNER JOIN empresas e
    ON c.id_empresa = e.id_empresa;


-- =========================
-- 14. PROVEEDORES DETALLE
-- =========================

CREATE OR REPLACE VIEW vw_proveedores_detalle AS
SELECT
    p.id_proveedor,
    p.id_empresa,
    e.nombre AS empresa,
    p.nombre,
    p.ruc,
    p.telefono,
    p.correo,
    p.direccion,
    p.estado,
    p.fecha_creacion
FROM proveedores p
INNER JOIN empresas e
    ON p.id_empresa = e.id_empresa;


-- =========================
-- 15. CONFIGURACIONES POR EMPRESA
-- =========================

CREATE OR REPLACE VIEW vw_configuraciones_empresa AS
SELECT
    c.id_configuracion,
    c.id_empresa,
    e.nombre AS empresa,
    c.clave,
    c.valor,
    c.descripcion,
    c.fecha_actualizacion
FROM configuraciones c
INNER JOIN empresas e
    ON c.id_empresa = e.id_empresa;


-- =========================
-- 16. NOTIFICACIONES USUARIO
-- =========================

CREATE OR REPLACE VIEW vw_notificaciones_usuario AS
SELECT
    n.id_notificacion,
    n.id_empresa,
    e.nombre AS empresa,
    n.id_usuario,
    u.usuario,
    u.nombre_completo,
    n.titulo,
    n.mensaje,
    n.tipo,
    n.leida,
    n.fecha_creacion
FROM notificaciones n
INNER JOIN empresas e
    ON n.id_empresa = e.id_empresa
LEFT JOIN usuarios u
    ON n.id_usuario = u.id_usuario;


-- =========================
-- 17. MOVIMIENTOS DE INVENTARIO DETALLE
-- =========================

CREATE OR REPLACE VIEW vw_movimientos_inventario_detalle AS
SELECT
    mi.id_movimiento,
    mi.id_empresa,
    e.nombre AS empresa,
    mi.id_sucursal,
    s.nombre AS sucursal,
    mi.id_producto,
    p.codigo,
    p.nombre AS producto,
    mi.id_usuario,
    u.usuario,
    u.nombre_completo,
    mi.tipo_movimiento,
    mi.cantidad,
    mi.stock_anterior,
    mi.stock_nuevo,
    mi.referencia,
    mi.observacion,
    mi.fecha_movimiento
FROM movimientos_inventario mi
INNER JOIN empresas e
    ON mi.id_empresa = e.id_empresa
INNER JOIN sucursales s
    ON mi.id_sucursal = s.id_sucursal
INNER JOIN productos p
    ON mi.id_producto = p.id_producto
INNER JOIN usuarios u
    ON mi.id_usuario = u.id_usuario;


-- =========================
-- 18. VENTAS DETALLE GENERAL
-- =========================

CREATE OR REPLACE VIEW vw_ventas_detalle_general AS
SELECT
    v.id_venta,
    v.id_empresa,
    e.nombre AS empresa,
    v.id_sucursal,
    s.nombre AS sucursal,
    v.id_usuario,
    u.usuario,
    u.nombre_completo AS vendedor,
    v.id_cliente,
    c.nombre AS cliente,
    v.numero_venta,
    v.subtotal,
    v.descuento,
    v.impuesto,
    v.total,
    v.monto_recibido,
    v.cambio,
    v.estado,
    v.fecha_venta
FROM ventas v
INNER JOIN empresas e
    ON v.id_empresa = e.id_empresa
INNER JOIN sucursales s
    ON v.id_sucursal = s.id_sucursal
INNER JOIN usuarios u
    ON v.id_usuario = u.id_usuario
LEFT JOIN clientes c
    ON v.id_cliente = c.id_cliente;


-- =========================
-- 19. DETALLE DE PRODUCTOS VENDIDOS
-- =========================

CREATE OR REPLACE VIEW vw_productos_vendidos_detalle AS
SELECT
    dv.id_detalle_venta,
    v.id_venta,
    v.id_empresa,
    e.nombre AS empresa,
    v.id_sucursal,
    s.nombre AS sucursal,
    v.numero_venta,
    p.id_producto,
    p.codigo,
    p.nombre AS producto,
    c.nombre AS categoria,
    m.nombre AS marca,
    dv.cantidad,
    dv.precio_unitario,
    dv.descuento,
    dv.subtotal,
    v.fecha_venta
FROM detalle_ventas dv
INNER JOIN ventas v
    ON dv.id_venta = v.id_venta
INNER JOIN empresas e
    ON v.id_empresa = e.id_empresa
INNER JOIN sucursales s
    ON v.id_sucursal = s.id_sucursal
INNER JOIN productos p
    ON dv.id_producto = p.id_producto
INNER JOIN categorias c
    ON p.id_categoria = c.id_categoria
LEFT JOIN marcas m
    ON p.id_marca = m.id_marca;


-- =========================
-- 20. COMPRAS DETALLE GENERAL
-- =========================

CREATE OR REPLACE VIEW vw_compras_detalle_general AS
SELECT
    co.id_compra,
    co.id_empresa,
    e.nombre AS empresa,
    co.id_sucursal,
    s.nombre AS sucursal,
    co.id_usuario,
    u.usuario,
    u.nombre_completo AS registrado_por,
    co.id_proveedor,
    p.nombre AS proveedor,
    co.numero_compra,
    co.subtotal,
    co.impuesto,
    co.total,
    co.estado,
    co.fecha_compra
FROM compras co
INNER JOIN empresas e
    ON co.id_empresa = e.id_empresa
INNER JOIN sucursales s
    ON co.id_sucursal = s.id_sucursal
INNER JOIN usuarios u
    ON co.id_usuario = u.id_usuario
INNER JOIN proveedores p
    ON co.id_proveedor = p.id_proveedor;


-- =========================
-- 21. DETALLE DE PRODUCTOS COMPRADOS
-- =========================

CREATE OR REPLACE VIEW vw_productos_comprados_detalle AS
SELECT
    dc.id_detalle_compra,
    co.id_compra,
    co.id_empresa,
    e.nombre AS empresa,
    co.id_sucursal,
    s.nombre AS sucursal,
    co.numero_compra,
    p.id_producto,
    p.codigo,
    p.nombre AS producto,
    c.nombre AS categoria,
    m.nombre AS marca,
    dc.cantidad,
    dc.precio_unitario,
    dc.subtotal,
    co.fecha_compra
FROM detalle_compras dc
INNER JOIN compras co
    ON dc.id_compra = co.id_compra
INNER JOIN empresas e
    ON co.id_empresa = e.id_empresa
INNER JOIN sucursales s
    ON co.id_sucursal = s.id_sucursal
INNER JOIN productos p
    ON dc.id_producto = p.id_producto
INNER JOIN categorias c
    ON p.id_categoria = c.id_categoria
LEFT JOIN marcas m
    ON p.id_marca = m.id_marca;


-- =========================
-- 22. RESUMEN DE VENTAS POR DÍA
-- =========================

CREATE OR REPLACE VIEW vw_resumen_ventas_dia AS
SELECT
    id_empresa,
    empresa,
    id_sucursal,
    sucursal,
    DATE(fecha_venta) AS fecha,
    COUNT(id_venta) AS total_ventas,
    SUM(total) AS monto_total_vendido
FROM vw_ventas_detalle_general
WHERE estado = 'completada'
GROUP BY
    id_empresa,
    empresa,
    id_sucursal,
    sucursal,
    DATE(fecha_venta);


-- =========================
-- 23. PRODUCTOS MÁS VENDIDOS
-- =========================

CREATE OR REPLACE VIEW vw_productos_mas_vendidos AS
SELECT
    id_empresa,
    empresa,
    id_sucursal,
    sucursal,
    id_producto,
    codigo,
    producto,
    categoria,
    marca,
    SUM(cantidad) AS cantidad_vendida,
    SUM(subtotal) AS total_vendido
FROM vw_productos_vendidos_detalle
GROUP BY
    id_empresa,
    empresa,
    id_sucursal,
    sucursal,
    id_producto,
    codigo,
    producto,
    categoria,
    marca
ORDER BY cantidad_vendida DESC;


-- =========================
-- 24. RESUMEN DE COMPRAS POR DÍA
-- =========================

CREATE OR REPLACE VIEW vw_resumen_compras_dia AS
SELECT
    id_empresa,
    empresa,
    id_sucursal,
    sucursal,
    DATE(fecha_compra) AS fecha,
    COUNT(id_compra) AS total_compras,
    SUM(total) AS monto_total_comprado
FROM vw_compras_detalle_general
WHERE estado = 'completada'
GROUP BY
    id_empresa,
    empresa,
    id_sucursal,
    sucursal,
    DATE(fecha_compra);


-- =========================
-- 25. APERTURAS DE CAJA DETALLE
-- =========================

CREATE OR REPLACE VIEW vw_aperturas_caja_detalle AS
SELECT
    ac.id_apertura,
    cj.id_empresa,
    e.nombre AS empresa,
    cj.id_sucursal,
    s.nombre AS sucursal,
    ac.id_caja,
    cj.nombre AS caja,
    ac.id_usuario,
    u.usuario,
    u.nombre_completo,
    ac.monto_inicial,
    ac.estado,
    ac.fecha_apertura
FROM aperturas_caja ac
INNER JOIN cajas cj
    ON ac.id_caja = cj.id_caja
INNER JOIN empresas e
    ON cj.id_empresa = e.id_empresa
INNER JOIN sucursales s
    ON cj.id_sucursal = s.id_sucursal
INNER JOIN usuarios u
    ON ac.id_usuario = u.id_usuario;


-- =========================
-- 26. MOVIMIENTOS DE CAJA DETALLE
-- =========================

CREATE OR REPLACE VIEW vw_movimientos_caja_detalle AS
SELECT
    mc.id_movimiento_caja,
    ac.id_apertura,
    cj.id_empresa,
    e.nombre AS empresa,
    cj.id_sucursal,
    s.nombre AS sucursal,
    cj.id_caja,
    cj.nombre AS caja,
    mc.id_usuario,
    u.usuario,
    u.nombre_completo,
    mc.tipo_movimiento,
    mc.monto,
    mc.descripcion,
    mc.referencia,
    mc.fecha_movimiento
FROM movimientos_caja mc
INNER JOIN aperturas_caja ac
    ON mc.id_apertura = ac.id_apertura
INNER JOIN cajas cj
    ON ac.id_caja = cj.id_caja
INNER JOIN empresas e
    ON cj.id_empresa = e.id_empresa
INNER JOIN sucursales s
    ON cj.id_sucursal = s.id_sucursal
INNER JOIN usuarios u
    ON mc.id_usuario = u.id_usuario;


-- =========================
-- 27. CIERRES DE CAJA DETALLE
-- =========================

CREATE OR REPLACE VIEW vw_cierres_caja_detalle AS
SELECT
    cc.id_cierre,
    ac.id_apertura,
    cj.id_empresa,
    e.nombre AS empresa,
    cj.id_sucursal,
    s.nombre AS sucursal,
    cj.id_caja,
    cj.nombre AS caja,
    cc.id_usuario,
    u.usuario,
    u.nombre_completo,
    cc.monto_inicial,
    cc.total_ingresos,
    cc.total_egresos,
    cc.total_ventas,
    cc.monto_esperado,
    cc.monto_real,
    cc.diferencia,
    cc.observacion,
    cc.fecha_cierre
FROM cierres_caja cc
INNER JOIN aperturas_caja ac
    ON cc.id_apertura = ac.id_apertura
INNER JOIN cajas cj
    ON ac.id_caja = cj.id_caja
INNER JOIN empresas e
    ON cj.id_empresa = e.id_empresa
INNER JOIN sucursales s
    ON cj.id_sucursal = s.id_sucursal
INNER JOIN usuarios u
    ON cc.id_usuario = u.id_usuario;


-- =========================
-- 28. AUDITORÍA DETALLE
-- =========================

CREATE OR REPLACE VIEW vw_auditoria_detalle AS
SELECT
    a.id_auditoria,
    a.id_empresa,
    e.nombre AS empresa,
    a.id_usuario,
    u.usuario,
    u.nombre_completo,
    a.tabla_afectada,
    a.accion,
    a.descripcion,
    a.datos_anteriores,
    a.datos_nuevos,
    a.fecha_accion
FROM auditoria a
INNER JOIN empresas e
    ON a.id_empresa = e.id_empresa
LEFT JOIN usuarios u
    ON a.id_usuario = u.id_usuario;
    
    
    
SELECT * FROM vw_dashboard_general_empresa;
SELECT * FROM vw_inventario_completo;
SELECT * FROM vw_productos_stock_bajo;
SELECT * FROM vw_productos_detalle;
SELECT * FROM vw_usuarios_roles;
    
    