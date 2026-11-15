"""Prueba las impresoras sin necesidad del sistema.

    python probar_impresoras.py listar      -> muestra las impresoras de Windows
                                               y los puertos COM (Bluetooth)
    python probar_impresoras.py             -> imprime un ticket de prueba en
                                               TODAS las impresoras configuradas
    python probar_impresoras.py caja        -> solo en esa (quesillo, cocina,
                                               bebidas o caja)

Las impresoras se configuran en agente.py (diccionario IMPRESORAS).
"""
import sys

import agente


def listar():
    print("== Impresoras instaladas en Windows (usa este nombre EXACTO en 'nombre'):")
    try:
        nombres = agente.listar_impresoras_windows()
        for n in nombres:
            print("   -", n)
        if not nombres:
            print("   (ninguna: instala primero el driver de la impresora)")
    except Exception as e:  # noqa: BLE001
        print("   (no se pudo listar:", e, ")")
    print()
    print("== Puertos COM (las impresoras Bluetooth emparejadas aparecen aqui):")
    try:
        from serial.tools import list_ports
        puertos = list(list_ports.comports())
        for p in puertos:
            print(f"   - {p.device}   {p.description}")
        if not puertos:
            print("   (ninguno: empareja primero la impresora en Configuracion -> Bluetooth)")
    except ImportError:
        print("   (falta pyserial: pip install pyserial)")


COMANDA = {
    "etiqueta": "PRUEBA DE COMANDA", "mesa": "Mesa 1", "mesero": "Prueba",
    "hora": "00/00/0000 00:00",
    "items": [
        {"cantidad": 2, "nombre": "Quesillo con tortilla", "comentario": "bien cocido"},
        {"cantidad": 1, "nombre": "Desayuno tipico con gallopinto y huevo frito"},
    ],
}

CAJA = {
    "tipo": "precuenta", "empresa": "QUESILLOS LO NUESTRO", "titulo": "PRECUENTA",
    "mesa": "Mesa 1", "cuenta": None, "fecha": "00/00/0000 00:00", "atendio": "Prueba",
    "cliente": "Publico General",
    "items": [
        {"cantidad": "2", "nombre": "Quesillo con tortilla", "precio_unitario": 60, "subtotal": 120, "comentario": "bien cocido"},
        {"cantidad": "1", "nombre": "Desayuno tipico con gallopinto y huevo frito", "precio_unitario": 180, "subtotal": 180},
    ],
    "subtotal": 300, "descuento": 30, "descuento_pct": 10, "total": 270,
    "propina_sugerida": 27, "total_con_propina": 297,
}


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "listar":
        listar()
        return
    nombres = [arg] if arg else ["quesillo", "cocina", "bebidas", "caja"]
    for nombre in nombres:
        print(f"-- {nombre}")
        if nombre == "caja":
            agente.imprimir("caja", agente.armar_ticket_caja, CAJA)
        else:
            payload = dict(COMANDA, impresora=nombre, etiqueta=f"PRUEBA {nombre.upper()}")
            agente.imprimir(nombre, agente.armar_comanda, payload)


if __name__ == "__main__":
    main()
