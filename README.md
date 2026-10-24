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

### 2.0 PC del restaurante (instalador)

La PC del restaurante es el **servidor local**: guarda su propia base MySQL y
a ella se conectan caja, meseros (celulares) y cocina por el Wi-Fi del local.
Funciona **con o sin internet**; cuando hay señal se sincroniza sola con la
nube cada 2 minutos y al reconectar.

Requisitos en esa PC: Windows 10/11, **Python 3.12** (marcar *Add python.exe
to PATH*) y **MySQL Server 8.4 LTS** como servicio automático.

1. Copia la carpeta del sistema a `C:\QuesillosPOS` (sin la carpeta `venv`).
   Si copias también el `.env` de la laptop, el instalador toma de ahí los
   datos de la nube y del correo; si no, los pregunta.
2. Abre PowerShell **como administrador** y corre:

   ```bash
   powershell -ExecutionPolicy Bypass -File C:\QuesillosPOS\scripts\instalar_restaurante.ps1
   ```

El instalador (se puede volver a correr; avisa antes de borrar nada):

- crea el entorno de Python e instala las dependencias;
- crea la base `quesillos_local` y la llena con una **copia completa de la nube**;
- escribe el `.env` de ese equipo (`MODO_NODO=local`, `ID_NODO=2`,
  `DEVICE_ID=restaurante-01`, `SECRET_KEY` propia);
- registra la tarea **"Quesillos POS - Servidor"**: el sistema arranca solo al
  encender la PC, sin ventana, y se reinicia solo si se cae
  (`scripts/servidor.ps1`, salida en `logs\servidor.log`);
- abre el puerto 5000 en el firewall para la red privada del local;
- pone el ícono **Quesillos POS** en el escritorio: abre el sistema en su
  propia ventana, como una app (`scripts/abrir_pos.vbs`), y también se abre
  solo al iniciar sesión;
- muestra la dirección para los celulares, por ejemplo `http://192.168.1.20:5000`.

Recomendado: reservar en el router la IP de esa PC y conectar PC y router a un
UPS. Si la PC servidor se apaga, los celulares no tienen a qué conectarse
(pueden usar la versión web si hay internet).

**Actualizar** el sistema en esa PC: reemplazar los archivos por la versión
nueva (sin tocar `.env`), correr
`venv\Scripts\python.exe -m pip install -r requirements.txt` y reiniciar la
PC (o la tarea "Quesillos POS - Servidor" en el Programador de tareas).

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

> En la laptop de desarrollo puedes saltarte este paso y usar Docker: ver 2.4b.

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

### 2.4a Numeración de IDs por equipo: por qué importa

Si la nube y el restaurante numeraran igual, la próxima venta de los dos lados
tendría el mismo ID y al sincronizar una **sobrescribiría a la otra**
(`INSERT ... ON DUPLICATE KEY UPDATE`).

Cada equipo numera con su propia terminación: cada conexión a MySQL fija
`auto_increment_increment = ID_INCREMENTO` (10) y `auto_increment_offset =`
su número de equipo.

| Equipo | `.env` | IDs que genera |
|---|---|---|
| Nube (Railway) | `MODO_NODO=nube` (usa `ID_NODO_NUBE=1`) | …1, …11, …21 |
| PC del restaurante | `MODO_NODO=local`, `ID_NODO=2` | …2, …12, …22 |
| Otra caja / laptop | `MODO_NODO=local`, `ID_NODO=3` (4, 5…) | …3, …13, …23 |

Nunca se repiten aunque cada base reciba filas del otro lado. Cada equipo
necesita además su propio `DEVICE_ID`.

> El rango fijo anterior (`LOCAL_ID_OFFSET`, `flask aplicar-offset`) no
> alcanzaba: al subir una fila con un ID alto, MySQL adelanta el contador de
> la nube hasta ese ID y los dos lados terminan generando los mismos números.
> Los comandos siguen existiendo pero ya no son lo que protege.

### 2.4b Desarrollo con Docker (en vez de instalar MySQL)

Solo para la laptop de desarrollo; la PC del restaurante no usa Docker (ver 2.0).
Docker corre únicamente la base de datos (MySQL 8.4, la misma versión del
restaurante); la app sigue corriendo en el `venv`.

En el `.env`:

```env
DB_LOCAL_HOST=127.0.0.1
DB_LOCAL_PORT=3307
DB_LOCAL_PASSWORD=quesillos
SYNC_ENABLED=false
```

El puerto es 3307 para no chocar con un MySQL instalado en Windows (3306), y
solo se abre en 127.0.0.1. `SYNC_ENABLED=false` porque en desarrollo no hay nube.

```bash
docker compose up -d                          # MySQL en 127.0.0.1:3307
venv\Scripts\python.exe -m flask init-local   # crea las tablas
venv\Scripts\python.exe -m flask seed         # empresa, sucursal, roles, unidades
venv\Scripts\python.exe -m flask crear-admin  # pide la contraseña del administrador
venv\Scripts\python.exe run.py
```

Los datos quedan en un volumen de Docker: sobreviven a `docker compose stop`
y a reiniciar la PC. Para empezar de cero: `docker compose down -v`.

### 2.5 Actualizar la base de datos en la nube

Aplica **una sola vez** el script de actualización sobre Railway
(agrega recetas, columnas de sincronización, roles y unidades):

```bash
mysql -h HOST -P PUERTO -u USUARIO -p pos_inventario_cloud < bd/02_cloud_upgrade.sql
mysql -h HOST -P PUERTO -u USUARIO -p pos_inventario_cloud < bd/03_opciones_y_categorias.sql
mysql -h HOST -P PUERTO -u USUARIO -p pos_inventario_cloud < bd/04_mesas_y_caja.sql
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
  ┌───────────────┐  1. push (cola local)        ┌────────────────┐
  │  MySQL LOCAL  │ ───────────────────────────► │  MySQL NUBE    │
  │ quesillos_    │ ◄─────────────────────────── │ pos_inventario │
  │   local       │  2. pull (registro de        │   _cloud       │
  └───────────────┘     cambios de la nube)      └────────────────┘
```

- **Monitor de red:** cada 30 s hace `SELECT 1` contra la nube.
- **Sync automático:** cada 2 min si hay conexión, y **de inmediato al reconectar**.
- **Primero sube, después baja:** lo del restaurante sube antes de bajar lo de
  la web, así un cambio local que aún no llegaba no se pisa con la versión
  vieja de la nube.
- **Bajada por registro de cambios:** en la nube, `sync_queue` es el registro
  de todo lo que se hace en la web (también los borrados). El restaurante lo
  lee en orden desde su cursor (`sync_cursor`) y para cada fila tocada trae su
  estado actual: si existe la escribe, si ya no existe la borra. Llegan todas
  las tablas: ventas con su detalle, recetas con ingredientes y opciones,
  mesas, clientes, usuarios (PIN, rol, desactivados), caja…
- **El stock viaja como movimientos:** cada movimiento de inventario nuevo suma
  o resta su diferencia en el otro lado, así una compra en la web y una venta
  en el restaurante al mismo tiempo no se pisan.
- **Si la misma fila cambió en los dos lados:** en ventas, productos y recetas
  gana la versión más reciente; una venta anulada se queda anulada.
- **La nube (`MODO_NODO=nube`) no se sincroniza consigo misma:** su indicador
  dice "En la nube".
- **Retención:** la nube borra su registro de cambios de más de 90 días
  (`RETENCION_COLA_DIAS`). Un restaurante que estuvo desconectado más tiempo
  se resincroniza completo y solo (`flask resync-nube` hace lo mismo a mano).
- **Cambios hechos directo en la base de la nube** (SQL a mano, fuera de la
  app) no pasan por el registro de cambios: después de hacerlos, correr
  `flask resync-nube` en el restaurante.
- **Sync manual:** botón ⟳ en la barra superior o panel `/sincronizacion` (Admin).
- **Indicador:** 🟢 En línea / 🔴 Sin conexión + contador de pendientes.

### Variables de cada equipo

| Variable | Nube (Railway) | PC del restaurante |
|---|---|---|
| `MODO_NODO` | `nube` | `local` |
| `ID_NODO` | (no aplica, usa `ID_NODO_NUBE=1`) | `2` |
| `DEVICE_ID` | `nube` | `restaurante-01` |
| `SYNC_ENABLED` | `true` (los respaldos dependen de que arranquen los jobs) | `true` |

### Resolución de conflictos

Cuando la venta local no cabe en el stock de la nube:

1. Se registra en `conflict_log` con ambas horas.
2. **Gana la hora menor.**
3. El perdedor se anula, se le devuelve el inventario y recibe la notificación
   *"El último producto ha sido vendido"*.
4. Todo queda auditado en `/sincronizacion`.

---

## 5a. Mesas (salón)

El flujo de venta en salón es **Mesas → Pedido → Cobrar**, aparte de la venta
directa de mostrador (`/ventas/pos`, para "Barra" o para llevar sin mesa):

1. `/mesas` — cuadrícula de mesas (13 mesas + Para llevar + 5 puestos de
   barra, sembrados por `bd/04_mesas_y_caja.sql`). Verde = libre, rojo = ocupada.
2. Al tocar una mesa libre se abre una **cuenta** (`ventas.estado = 'pendiente'`,
   ligada a la mesa) y se entra a `/mesas/<id>/pedido`: catálogo con pestañas
   de categoría a la izquierda, cuenta de la mesa a la derecha.
3. Se pueden seguir agregando o quitando productos mientras la mesa está
   ocupada (esto es "editar el pedido en curso"); cada cambio descuenta o
   devuelve inventario al instante.
4. **Cobrar** cierra la cuenta (`estado = 'completada'`), pide método de pago,
   descuento y propina, y libera la mesa.

Administrar las mesas (crear/quitar) es solo de Admin, vía
`POST /mesas/api/crear` y `POST /mesas/api/<id>/desactivar`.

## 5b. Caja y clientes

- **`/caja`** — Admin y Cajero. Abrir turno con un monto inicial, registrar
  gastos/ingresos/retiros durante el día, y cerrar turno: compara el efectivo
  contado contra lo esperado (inicial + ventas en efectivo + ingresos − egresos)
  y guarda la diferencia en `cierres_caja`.
- **`/clientes`** — alta rápida de clientes (nombre, cédula, teléfono,
  dirección) para asociarlos a una venta o cuenta de mesa.

---

## 6. Roles y permisos

| Ruta | Admin | Cocinero | Cajero | Mesero |
|---|:---:|:---:|:---:|:---:|
| `/` Dashboard | ✅ | ❌ | ❌ | ❌ |
| `/mesas` | ✅ | ❌ | ✅ | ✅ |
| `/ventas/pos` | ✅ | ❌ | ✅ | ✅ |
| `/ventas/historial` | ✅ | ❌ | ✅ | ✅ (solo suyas) |
| `/clientes` | ✅ | ❌ | ✅ | ✅ |
| `/caja` | ✅ | ❌ | ✅ | ❌ |
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
flask bootstrap-nube   # copia la nube -> local y fija desde dónde bajar cambios
flask resync-nube      # deja la base local igual a la nube (sube lo pendiente primero)
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
por timestamp, anulaciones que devuelven exactamente lo descontado (opciones
incluidas), modo nube, roles y recuperación de contraseña.

Prueba de punta a punta de la sincronización con **MySQL real** (crea dos
bases de prueba en el MySQL de la máquina, una hace de nube y otra de
restaurante, y las borra al final; no toca la nube real):

```bash
python tests/sync/nodo_local_nube_real_mysql.py
```

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
