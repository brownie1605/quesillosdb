# 🫓 Quesillos Lo Nuestro — POS Híbrido (Local + Nube)

Sistema de punto de venta con **recetas**, **insumos** y **funcionamiento offline**.
La aplicación trabaja siempre contra una base de datos **MySQL local**; cuando hay
internet sincroniza automáticamente con la base **MySQL en la nube (Railway)**.

Fusiona el diseño de *quesillosdb-main* con el backend de *sistema-pos-pymes*.

---

## 1. Qué resuelve

| Necesidad | Solución |
|---|---|
| El local pierde internet seguido | Todo se guarda en MySQL local. El POS nunca se detiene. |
| Los datos deben llegar a la nube | Cola `sync_queue` + *push/pull* automático cada 2 min y al reconectar. |
| Dos cajas venden la última unidad | Gana la venta con **hora menor**; la otra se anula y su usuario recibe la alerta *"El último producto ha sido vendido"*. |
| Un quesillo consume varios insumos | Módulo de **recetas**: al vender se descuentan tortillas, crema, cebolla y quesillo del inventario. |
| Los insumos también se venden | Los productos tipo `insumo` se venden solos **y** se usan en recetas. |
| Recuperar contraseña | Código aleatorio de **6 dígitos** al correo del usuario (se pide correo + rol). |

---

## 2. Instalación

### 2.1 Requisitos

- Python 3.12
- MySQL 8+ instalado y corriendo en la máquina del negocio
- Acceso a la base en la nube (Railway)

### 2.2 Preparar el entorno

```bash
cd quesillos-pos
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2.3 Configurar `.env`

Copia `.env.example` a `.env` y completa:

```env
DB_LOCAL_HOST=localhost
DB_LOCAL_USER=root
DB_LOCAL_PASSWORD=tu_password_de_mysql_local
DB_LOCAL_NAME=quesillos_local

DB_REMOTE_HOST=xxxx.proxy.rlwy.net
DB_REMOTE_PORT=58542
DB_REMOTE_USER=root
DB_REMOTE_PASSWORD=...
DB_REMOTE_NAME=pos_inventario_cloud

SMTP_USER=quesilloslonuestro26@gmail.com
SMTP_PASS=contrasena_de_aplicacion_de_google
```

### 2.4 Crear la base de datos local

```bash
mysql -u root -p -e "CREATE DATABASE quesillos_local CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

Luego, con el entorno activo:

```bash
set FLASK_APP=run.py
flask init-local       # crea todas las tablas
flask bootstrap-nube   # copia el catálogo y el historial desde la nube
flask crear-admin      # pide la contraseña del administrador
```

> Si es una instalación nueva sin datos en la nube, usa `flask seed` en lugar
> de `flask bootstrap-nube`.

### 2.4a Rangos de ID: por qué importa

`bootstrap-nube` termina reservando un **rango de IDs para esta máquina**
(desde `LOCAL_ID_OFFSET`, por defecto **1 000 000**).

Sin eso, la caja local crearía un producto con `id_producto = 1` mientras en la
nube el `id_producto = 1` es otro producto distinto. Al sincronizar, el
`INSERT ... ON DUPLICATE KEY UPDATE` **sobrescribiría el producto de la nube**.

Con el offset:

| | Rango de IDs |
|---|---|
| Registros creados en la nube | 1 – 999 999 |
| Registros creados en esta caja | 1 000 000 en adelante |

Comprueba en cualquier momento que no haya riesgo:

```bash
flask verificar-ids     # avisa si alguna tabla quedó fuera de rango
flask aplicar-offset    # lo corrige
```

Si algún día se instala una **segunda caja**, dale otro rango en su `.env`
(por ejemplo `LOCAL_ID_OFFSET=2000000`) y un `DEVICE_ID` distinto.

### 2.5 Actualizar la base de datos en la nube

Aplica **una sola vez** el script de actualización sobre Railway
(agrega recetas, columnas de sincronización, roles y unidades):

```bash
mysql -h HOST -P PUERTO -u USUARIO -p pos_inventario_cloud < bd/02_cloud_upgrade.sql
mysql -h HOST -P PUERTO -u USUARIO -p pos_inventario_cloud < bd/03_opciones_y_categorias.sql
```

Ambos scripts son idempotentes: pueden ejecutarse varias veces sin dañar los
datos. Solo agregan tablas y columnas; no borran nada. `03_opciones_y_categorias.sql`
agrega los ingredientes "quitables" y los grupos de opciones del punto 4.1.

Para respaldar la nube antes de tocarla:

```bash
mysqldump -h HOST -P PUERTO -u USUARIO -p --single-transaction --routines --triggers pos_inventario_cloud > bd/respaldos/nube.sql
```

### 2.6 Arrancar

```bash
python run.py
```

Abre <http://localhost:5000>.

---

## 3. Configurar el correo de recuperación

El envío usa **quesilloslonuestro26@gmail.com** por SMTP. Gmail no acepta la
contraseña normal: hay que generar una *contraseña de aplicación*.

1. Entra a <https://myaccount.google.com/security> con esa cuenta.
2. Activa **Verificación en dos pasos** (obligatorio para el paso siguiente).
3. Entra a <https://myaccount.google.com/apppasswords>.
4. Crea una contraseña de aplicación (nombre sugerido: `Quesillos POS`).
5. Google muestra 16 caracteres. Cópialos **sin espacios** en el `.env`:

```env
SMTP_PASS=abcdefghijklmnop
```

6. Reinicia la aplicación.

> Si `SMTP_PASS` queda vacío, el sistema sigue funcionando: registra el código
> en el log del servidor en lugar de enviarlo, para no bloquear al usuario.

### Flujo de recuperación

1. En el login → **¿Olvidaste tu contraseña?** → `/forgot-password`
2. El usuario escribe su **correo** y elige su **rol**.
3. Recibe un código de **6 dígitos**, válido 15 minutos.
4. Lo escribe en `/verify-code/...` (se envía solo al completar los 6 dígitos).
5. Define su nueva contraseña y vuelve al login.

---

## 4. Recetas e insumos

### Tipos de producto

| Tipo | ¿Se vende? | ¿Va en recetas? | Ejemplo |
|---|---|---|---|
| `final` | Sí | No (las usa) | Quesillo Lo Nuestro |
| `insumo` | **Sí** | Sí | Tortilla, Crema, Cebolla |
| `material` | No | Sí | Bolsas, servilletas |

### Ejemplo real cargado por `flask demo-quesillo`

```
Quesillo Lo Nuestro (final, C$60)
  ├─ 2      Tortilla        (und)
  ├─ 0.25   Crema           (L)
  ├─ 6      Cebolla         (oz)
  └─ 1      Quesillo insumo (und)
Costo de la receta: C$55.00 · Margen: C$5.00
```

Al vender **3 quesillos**, el sistema descuenta automáticamente 6 tortillas,
0.75 L de crema, 18 oz de cebolla y 3 quesillos-insumo. Si algún insumo no
alcanza, la venta se rechaza indicando cuál falta.

Vender una **docena de tortillas** por separado descuenta solo las tortillas.

### 4.1 Personalización en el punto de venta

Al crear o editar una receta (Admin o Cocinero, todo en el mismo formulario
de `/recetas`) se puede marcar:

- **Ingredientes "quitables"**: se descuentan normalmente, pero el cajero o
  mesero puede pedir quitarlos en una venta puntual (ej. *"quesillo sin
  cebolla"*) sin tocar la receta ni cambiar el precio.
- **Grupos de opciones**: una elección de una sola opción por grupo (ej.
  *"Proteína: salsa ranchera / jamón / chorizo criollo"*, o *"Acompañante:
  gallopinto o frijoles"*). Cada opción puede descontar su propio insumo del
  inventario si aplica.

Si un producto tiene algo que preguntar, al hacer clic en él dentro del POS
se abre un modal antes de agregarlo al carrito. Lo elegido queda visible como
un comentario bajo la línea del producto — en el carrito, en el historial de
ventas y en la factura impresa.

### 4.2 Categorías en el catálogo

Los productos se agrupan por categoría (ej. *Asados, Extras, Quesillos,
Insumos*) desde `/productos` → **+ Nueva Categoría**. En el punto de venta
aparecen como pestañas sobre la cuadrícula de productos para filtrar rápido.

### 4.3 Crear un producto y su receta en un solo paso

Ya no hace falta crear el producto en `/productos` y luego ir a `/recetas` a
enlazarlo: el formulario de "Nueva receta" tiene un botón **+ Crear producto
nuevo** que da de alta el producto (nombre, categoría, precio) y la receta —
ingredientes, quitables y grupos de opciones — en un solo guardado.

---

## 5. Sincronización

```
  ┌───────────────┐   push (cola)   ┌────────────────┐
  │  MySQL LOCAL  │ ──────────────► │  MySQL NUBE    │
  │ quesillos_    │ ◄────────────── │ pos_inventario │
  │   local       │   pull (fecha)  │   _cloud       │
  └───────────────┘                 └────────────────┘
```

- **Monitor de red:** cada 30 s hace `SELECT 1` contra la nube.
- **Sync automático:** cada 2 min si hay conexión, y **de inmediato al reconectar**.
- **Sync manual:** botón ⟳ en la barra superior o panel `/sincronizacion` (Admin).
- **Indicador:** 🟢 En línea / 🔴 Sin conexión + contador de pendientes.

### Resolución de conflictos

Cuando la venta local no cabe en el stock de la nube:

1. Se registra en `conflict_log` con ambas horas.
2. **Gana la hora menor.**
3. El perdedor se anula, se le devuelve el inventario y recibe la notificación
   *"El último producto ha sido vendido"*.
4. Todo queda auditado en `/sincronizacion`.

---

## 6. Roles y permisos

| Ruta | Admin | Cocinero | Cajero | Mesero |
|---|:---:|:---:|:---:|:---:|
| `/` Dashboard | ✅ | ❌ | ❌ | ❌ |
| `/ventas/pos` | ✅ | ❌ | ✅ | ✅ |
| `/ventas/historial` | ✅ | ❌ | ✅ | ✅ (solo suyas) |
| `/recetas` | ✅ CRUD | ✅ CRUD | ❌ | ❌ |
| `/insumos` | ✅ CRUD | ✅ CRUD | 👁 lectura | 👁 lectura |
| `/cocina` | ✅ | ✅ | ❌ | ❌ |
| `/productos` | ✅ | 👁 | 👁 | ❌ |
| `/inventario`, `/compras` | ✅ | ❌ | ✅ | ❌ |
| `/usuarios`, `/reportes`, `/sincronizacion` | ✅ | ❌ | ❌ | ❌ |

El rol **Admin** pasa cualquier verificación.

---

## 7. Comandos disponibles

```bash
flask init-local       # crea las tablas locales desde los modelos
flask bootstrap-nube   # copia la nube -> local y reserva el rango de IDs
flask seed             # empresa, sucursal, 4 roles, unidades, categorías
flask crear-admin      # crea/actualiza el usuario administrador
flask demo-quesillo    # carga el ejemplo Quesillo + 4 insumos
flask sync-now         # fuerza una sincronización completa
flask sync-status      # muestra el estado de la conexión y pendientes
flask verificar-ids    # revisa que los IDs locales no choquen con la nube
flask aplicar-offset   # reserva/corrige el rango de IDs local
```

---

## 8. Pruebas

```bash
python -m pytest tests/ -q
```

Cubren: recetas y descuento de insumos, venta de insumo suelto, stock
insuficiente, cola de sincronización, modo offline, resolución de conflictos
por timestamp, roles y recuperación de contraseña.

---

## 9. Estructura

```
quesillos-pos/
├─ app/
│  ├─ models/         receta.py · sync.py · producto.py · venta.py · …
│  ├─ services/       sync_service · conflict_service · receta_service
│  │                  inventario_service · venta_service · network_service
│  │                  scheduler_service · email_service
│  ├─ routes/         receta · insumo · cocina · sync · venta · auth · …
│  ├─ templates/      recetas/ · insumos/ · cocina/ · sync/ · auth/
│  ├─ static/         css/quesillos.css · js/sync.js · js/network-monitor.js
│  ├─ cli.py          comandos flask
│  └─ config/         config.py (local + bind "cloud")
├─ bd/02_cloud_upgrade.sql
├─ tests/
└─ run.py
```
