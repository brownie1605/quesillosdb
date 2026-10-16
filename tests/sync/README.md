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

## Restaurante <-> nube de punta a punta

```bash
python tests/sync/nodo_local_nube_real_mysql.py            # borra sus bases al final
python tests/sync/nodo_local_nube_real_mysql.py --conservar  # las deja para revisarlas
```

Crea `qpos_prueba_nube` y `qpos_prueba_rest` en el MySQL de **esta**
maquina (se niega a correr si `DB_LOCAL_HOST` no es localhost) y sincroniza
de verdad entre ellas: venta sin internet, ventas a la vez en los dos lados,
anulaciones con opciones, receta editada en la web, usuarios, compra mientras
se vende, borrados, conflictos de "ultima unidad" en los dos sentidos y una
resincronizacion completa. Despues de cada escenario las dos bases deben
tener las mismas filas en las 23 tablas sincronizadas y el mismo stock.
