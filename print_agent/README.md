# Agente de impresión — Quesillos POS

Programa pequeño que corre en **una PC o tablet dentro del local** (no en
la nube) e imprime las comandas en las impresoras físicas (Quesillo /
Cocina / Bebidas) cuando un mesero envía un pedido.

## Por qué existe esto por separado

El sistema (Quesillos POS) va a vivir en Railway, en la nube. Las
impresoras están conectadas a la red del local. La nube no tiene forma de
"ver" una impresora que está en una red distinta — por eso hace falta
este puente: un programa que sí está dentro de la red del local, y que
recibe el aviso del sistema en tiempo real para imprimir.

## Qué falta para que funcione (una vez tengan las impresoras)

1. Averiguar la **IP de cada impresora** en la red del local — casi todas
   las impresoras térmicas de red la muestran al imprimir su página de
   prueba/auto-test (suele ser un botón que se mantiene presionado al
   encenderla; revisa el manual de tu modelo).
2. Abrir `agente.py` y editar solo estas líneas, con la IP real de cada una:

   ```python
   IMPRESORAS = {
       "quesillo": "192.168.1.50",
       "cocina": "192.168.1.51",
       "bebidas": "192.168.1.52",
   }
   ```

3. Cambiar `SERVIDOR_URL` por la URL real del sistema una vez esté en Railway.

Nada más. El resto (qué producto va a cuál impresora, el armado del
ticket, el aviso en tiempo real) ya está funcionando en el sistema.

## Instalación (en la PC/tablet que va a hacer de puente)

```bash
cd print_agent
pip install -r requirements.txt
python agente.py
```

Déjalo corriendo — se reconecta solo si se cae el internet o se reinicia
el servidor. Para que arranque solo cuando prenda la PC, se puede agregar
como tarea programada de Windows (Programador de tareas → "Al iniciar
sesión" → ejecutar `python agente.py`).

## Requisitos de las impresoras

Este agente asume impresoras térmicas **de red (WiFi o Ethernet)** que
hablan el protocolo estándar ESC/POS por el puerto 9100 (RAW/JetDirect) —
es el más común en impresoras de recibos de este rango de precio.

Si terminan comprando impresoras **por USB** en lugar de red, avisa: el
agente necesita un pequeño ajuste (usar la librería `python-escpos` con
su conexión USB en vez de una conexión de red), pero sigue corriendo en
la misma PC/tablet del local sin cambiar nada más del sistema.

## Asignar impresora a un producto

Se hace desde el sistema: **Productos → editar/crear producto → campo
"Impresora de comanda"**. Ahí eliges Quesillo, Cocina o Bebidas (o "Sin
asignar" si ese producto no debe imprimirse en ninguna, ej. un insumo).
