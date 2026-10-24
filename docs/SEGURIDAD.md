# Seguridad de Quesillos POS

Este documento explica **qué ataques resiste el sistema, dónde está el código
que lo defiende, y cómo comprobarlo**. Está pensado para que cualquiera
(un maestro, un evaluador, un compañero) pueda verificar las defensas sin
tener que leer todo el proyecto.

El sistema corre **en local** (la PC del restaurante), con los celulares de
los meseros conectados por la Wi-Fi del local. Todo lo de abajo aplica a esa
instalación local; la parte de nube (Railway) comparte el mismo código.

---

## 1. Resumen: qué se defiende y dónde está el código

| # | Ataque | Defensa | Archivo |
|---|--------|---------|---------|
| 1 | Fuerza bruta de contraseñas | Límite por IP + límite por usuario + bloqueo temporal de la cuenta | `app/routes/auth_routes.py`, `app/extensions.py` |
| 2 | Adivinar el código de recuperación (6 dígitos) | Código con CSPRNG + tope de 5 intentos + expira en 15 min | `app/routes/auth_routes.py` |
| 3 | Enumerar usuarios/correos válidos | Respuestas y mensajes idénticos existan o no la cuenta | `app/routes/auth_routes.py` |
| 4 | Fuerza bruta del segundo factor (2FA) | Bloqueo de la cuenta a los 5 códigos malos (aunque cambie de IP) | `app/routes/auth_routes.py` |
| 5 | Inyección SQL | SQLAlchemy con parámetros enlazados (nunca se concatena texto del usuario) | todo `app/routes/`, `app/services/` |
| 6 | XSS (scripts guardados o reflejados) | Autoescape de Jinja2 + CSP; ninguna plantilla usa `\|safe` sobre datos | plantillas + `app/__init__.py` |
| 7 | CSRF (acciones forzadas desde otra web) | Token CSRF obligatorio en todo formulario/POST (Flask-WTF) | `app/__init__.py`, `app/extensions.py` |
| 8 | Robo de la cookie de sesión | Cookie `HttpOnly`, `SameSite=Lax`, `Secure` bajo HTTPS; firmada con `SECRET_KEY` | `app/config/config.py` |
| 9 | WebSocket abierto sin sesión / desde otra web | El socket exige sesión y solo acepta el mismo origen | `app/__init__.py`, `app/extensions.py` |
| 10 | Acceso a funciones sin permiso | Login obligatorio + control por rol en cada ruta | `app/utils/decorators.py` |
| 11 | DoS: inundación de peticiones (flood / DDoS) | Límite global de peticiones por IP | `app/extensions.py` |
| 12 | DoS: cuerpos/subidas gigantes | `MAX_CONTENT_LENGTH` de 8 MB → responde 413 sin leer | `app/config/config.py` |
| 13 | Subir un archivo malicioso disfrazado de imagen | Lista blanca de extensiones + validación de la firma de bytes real | `app/utils/imagenes.py` |
| 14 | Path traversal (`/static/../.env`) | Werkzeug normaliza la ruta; `.env` fuera de carpetas servidas | Flask/Werkzeug |
| 15 | Fuga de información en errores | Mensaje genérico al cliente; el detalle y la traza van solo al log | `app/utils/errores.py`, `app/__init__.py` |
| 16 | Clave de firma adivinable | Si falta `SECRET_KEY`, se genera una aleatoria por arranque | `app/config/config.py` |

> **Importante sobre "aguantar un DDoS".** Un DDoS real (miles de equipos de
> una botnet a la vez) **no se detiene desde la aplicación**: ninguna app de
> un solo servidor puede, porque el tubo de internet y el CPU se saturan
> antes. Lo que SÍ hace este sistema, y es lo que corresponde a su nivel, es:
> (a) frenar el abuso de **un** origen con el límite por IP, (b) responder
> barato (429) sin tocar la base de datos cuando alguien inunda, y (c) seguir
> atendiendo a los demás. Para un DDoS masivo real, la defensa vive **antes**
> del servidor (ver §5: Cloudflare / firewall). Esto está documentado a
> propósito para no prometer algo que ningún sistema de este tipo cumple.

---

## 2. Cómo comprobar las defensas (pruebas automáticas)

Toda la suite de seguridad vive en `tests/security/` y corre con los
controles **encendidos** (CSRF y límite de peticiones reales), igual que en
producción.

```bash
# 1) Preparar el entorno (una sola vez)
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt pytest

# 2) Correr SOLO las pruebas de seguridad
venv\Scripts\python -m pytest tests/security -v

# 3) Correr TODA la suite (negocio + seguridad)
venv\Scripts\python -m pytest -q
```

Qué prueba cada archivo:

| Archivo | Qué ataca / demuestra |
|---------|----------------------|
| `tests/security/test_control_acceso.py` | Barre **todas** las rutas y confirma que ninguna privada responde sin sesión; que todo POST exige CSRF; que la cookie es `HttpOnly`; que una cookie falsificada no entra. |
| `tests/security/test_fuerza_bruta.py` | Límite por IP y por usuario; bloqueo de cuenta; que no se puede distinguir "usuario no existe" de "clave mala"; invalidación del código de recuperación; bloqueo del 2FA. |
| `tests/security/test_inyeccion.py` | 8 payloads de SQL injection en login y en filtros; XSS guardado y reflejado; path traversal; que los errores no filtran trazas ni datos de la base. |
| `tests/security/test_denegacion_servicio.py` | Flood (aparece 429); que falsear `X-Forwarded-For` no esquiva el límite; cuerpo de 20 MB → 413; JSON anidado 100.000 niveles; archivos disfrazados de imagen. |

---

## 3. Cómo comprobar las defensas bajo carga real (sockets de verdad)

Las pruebas de arriba corren dentro del proceso. Para ver el servidor
**real** aguantando una inundación, hay un validador aparte que abre
conexiones de verdad:

```bash
# Terminal 1: levanta un servidor de prueba (SQLite en memoria, sin MySQL)
venv\Scripts\python scripts/seguridad/servidor_de_prueba.py

# Terminal 2: lánzale la carga y mide las defensas
venv\Scripts\python scripts/seguridad/validar_defensas.py --url http://127.0.0.1:5099
```

El validador (`scripts/seguridad/validar_defensas.py`) comprueba, con números:

1. **Flood** a `/healthz`: aparecen respuestas **429** (el límite actúa) y
   ninguna petición queda sin respuesta.
2. **Disponibilidad**: mientras un hilo bombardea, un cliente normal sigue
   recibiendo respuesta rápida.
3. **Conexión lenta (slowloris)**: 10 conexiones que nunca terminan de
   enviar no dejan colgado al servidor.
4. **Fuerza bruta de login**: `/login` corta con 429.

Devuelve código de salida **0** si todo pasó, **1** si algo falló. Por
seguridad **solo apunta a tu red local**; para otra URL hay que pasar
`--permitir-remoto` a conciencia (probar un sistema ajeno sin permiso puede
ser ilegal).

> También funciona contra el servidor real del negocio:
> `python run.py` en una terminal y
> `python scripts/seguridad/validar_defensas.py` en otra (apunta a
> `http://127.0.0.1:5000` por defecto).

---

## 4. Detalle de cada defensa (para la revisión)

### 4.1 Autenticación y fuerza bruta
- **Límite por IP** en `/login`: 15 intentos/min (`@limiter.limit("15 per minute")`).
- **Límite por usuario**: 5 intentos / 15 min sobre el nombre enviado, exista
  o no — esto cierra el hueco de que un atacante repartiera los intentos
  entre muchas IPs contra una sola cuenta.
- **Bloqueo de la cuenta**: a los 5 fallos, la cuenta queda bloqueada 15 min;
  durante ese rato ni siquiera la contraseña correcta entra.
- **2FA (TOTP)**: el segundo factor también cuenta fallos y bloquea la cuenta
  a los 5 intentos, porque un código de 6 dígitos sería adivinable por quien
  ya tenga la contraseña.

### 4.2 Recuperación de contraseña
- El código de 6 dígitos se genera con `secrets` (CSPRNG), no con `random`
  (que es predecible).
- Máximo 5 intentos; al pasarse, el código se invalida y hay que pedir otro.
  Esto aplica tanto a la vía web como a la API JSON.
- Las respuestas son **idénticas** exista o no el correo, para no delatar qué
  cuentas son válidas.

### 4.3 Inyección SQL
- **Todas** las consultas usan SQLAlchemy ORM o `text()` con **parámetros
  enlazados** (`:empresa`, `:inicio`...). El texto que manda el usuario nunca
  se concatena dentro del SQL. Las partes dinámicas que sí se arman por
  `f-string` son **nombres de columnas/cláusulas fijas del propio código**
  (p. ej. `LIMIT 7`), nunca datos del usuario.
- Las pruebas lanzan `' OR '1'='1`, `UNION SELECT ... password_hash`,
  `DROP TABLE`, etc., y verifican que no se entra ni se altera la base.

### 4.4 XSS y cabeceras
- Jinja2 **autoescapa** todo por defecto. Una revisión estática
  (`test_plantillas_no_desactivan_el_autoescape`) confirma que ninguna
  plantilla usa `|safe` sobre datos (solo `|tojson|safe`, que ya viene
  escapado).
- `app/__init__.py` añade en cada respuesta: `Content-Security-Policy`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, `Permissions-Policy`, y `HSTS` cuando se sirve por HTTPS.

### 4.5 CSRF y sesión
- Flask-WTF exige token CSRF en todo POST/PUT/DELETE/PATCH.
- Cookie de sesión `HttpOnly` (JS no la lee), `SameSite=Lax` (no viaja desde
  otra web), y `Secure` cuando hay HTTPS. Firmada con `SECRET_KEY`: sin esa
  clave nadie puede fabricar una sesión de Admin.

### 4.6 WebSocket
- El handler `connect` rechaza la conexión si no hay sesión válida.
- El socket solo acepta conexiones del **mismo origen** (antes aceptaba
  `*`, lo que permitía que otra web abriera un socket con la sesión del
  empleado — *Cross-Site WebSocket Hijacking*).

### 4.7 Denegación de servicio
- Límite global por IP (`200 per hour` + los límites por ruta).
- `MAX_CONTENT_LENGTH = 8 MB`: un cuerpo más grande se rechaza con **413**
  sin cargarse en memoria.
- Validación de imágenes por **firma de bytes** (no por el nombre): un
  `.php` o `.svg` renombrado a `.png` se rechaza.

### 4.8 Manejo de errores
- `app/utils/errores.py`: las rutas de API ya **no** devuelven `str(e)` al
  cliente (antes eso filtraba la consulta SQL, nombres de tablas y a veces el
  host de MySQL). Ahora el detalle va al log y el cliente recibe un mensaje
  genérico. Un `ValueError` (dato mal formado o regla de negocio) sí conserva
  su mensaje, porque está escrito para el usuario y no trae SQL.

---

## 5. Qué NO cubre la aplicación (honestidad sobre los límites)

- **DDoS volumétrico masivo** (una botnet saturando el ancho de banda): se
  mitiga **antes** del servidor, no dentro. Opciones para el local:
  poner el sistema detrás de **Cloudflare** (plan gratis ya trae mitigación
  de DDoS), o limitar conexiones en el router. El proyecto ya trae pistas de
  esto en el `.env.example` (Cloudflare R2) y el firewall de Windows se
  configura en `scripts/instalar_restaurante.ps1` (solo red privada del
  local).
- **Seguridad física** de la PC del restaurante (quien se siente frente a
  una sesión abierta). Mitigación: cerrar sesión, `PERMANENT_SESSION_LIFETIME`
  de 8 h, y 2FA para las cuentas de Admin.
- **HTTPS en la red local**: por defecto el tráfico en la Wi-Fi del local va
  por HTTP. Para cifrarlo haría falta un certificado; mientras tanto, la red
  del local debe tener contraseña WPA2 y estar separada de la Wi-Fi de
  clientes.

Estos puntos están listados a propósito: un sistema que dice defenderse de
"todo" es menos confiable que uno que sabe exactamente dónde termina su
alcance.
