# scripts/seguridad/

Herramientas para **validar las defensas de Quesillos POS** contra tu propio
servidor local. La documentación completa está en
[`docs/SEGURIDAD.md`](../../docs/SEGURIDAD.md).

| Archivo | Para qué |
|---------|----------|
| `validar_defensas.py` | Lanza carga real (flood, slowloris, fuerza bruta) contra el servidor y comprueba, con números, que el límite de peticiones y la disponibilidad responden como deben. Código de salida 0 = todo bien. |
| `servidor_de_prueba.py` | Levanta la app en `http://127.0.0.1:5099` con SQLite en memoria (sin MySQL ni `.env`), para poder correr el validador en cualquier máquina. |

## Uso rápido

```bash
# Terminal 1
python scripts/seguridad/servidor_de_prueba.py

# Terminal 2
python scripts/seguridad/validar_defensas.py --url http://127.0.0.1:5099
```

> Estas herramientas son **defensivas**: solo apuntan a tu red local. No
> sirven para atacar sistemas ajenos y se niegan a apuntar fuera de la red
> privada salvo que se les pase `--permitir-remoto` con autorización.
