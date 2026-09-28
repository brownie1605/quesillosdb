# Pruebas de concurrencia (MySQL real)

Estos scripts **no** se llaman `test_*.py` a propósito: `pytest tests/`
usa SQLite en memoria (ver `tests/conftest.py`), que serializa todas las
escrituras a nivel de archivo y por lo tanto **nunca podría reproducir**
una carrera real entre dos transacciones. Necesitan la base MySQL real
(local o cloud, vía las mismas variables `DB_REMOTE_*`/`DB_LOCAL_*` que usa
la app) y usan hilos reales, así que si `pytest` los recolectara junto con
el resto de la suite, su `create_app()` a nivel de módulo interferiría con
las fixtures SQLite de los demás tests (ya pasó — por eso quedaron
renombrados así).

Correr cada uno a mano:

```bash
python tests/concurrency/h02_inventario_concurrencia_real_mysql.py
python tests/concurrency/h03_caja_concurrencia_real_mysql.py
```

Ambos crean sus propios datos desechables y los borran al final, incluso
si la prueba falla a medio camino. No dejan datos de prueba en la base.
