# Pruebas de sincronización (MySQL real)

`_upsert_local()` usa `INSERT ... ON DUPLICATE KEY UPDATE` (sintaxis de
MySQL), que no existe en SQLite — por eso este script no se llama
`test_*.py` (para que `pytest tests/` no lo recolecte junto con el resto
de la suite, que corre sobre SQLite en memoria).

Correr a mano:

```bash
python tests/sync/h04_h05_conflicto_anulacion_real_mysql.py
```

Crea su propia venta desechable y la borra al final, incluso si la
prueba falla a medio camino.
