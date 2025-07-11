# VTEX
Plan de implementación – Flujo VTEX ↔ Servidor
↔ Dragonfish
0. Esquema de estados (según diagrama)
VTEX → Servidor
Webhook/polling notifica nueva venta.
Servidor → Dragonfish
Consulta stock total por SKU; reserva (stock – n en envío) pero aún no descuenta movimiento
real.
Dragonfish → Servidor
Devuelve stock real sin WOO.
Servidor → VTEX
PUT nuevo stock (stock – n).
Servidor → Persona
Notifica creación de remito manual.
Servidor → Dragonfish
Informa nuevo movimiento (resta n en WOO).
Actualiza stock real (–n) y genera asiento.
Dragonfish → Servidor
Confirmación del movimiento.
Persona → Depósito
Crea remito manual (traslado físico).
1. Módulos a construir
monitor_vtex.py – escucha webhook o hace polling con deduplicación persistente.
dragonfish_client.py – wrapper API/SQL (consulta, reserva, movimiento).
stock_sync.py – orquestación: recibe venta, reserva, actualiza VTEX, descuenta Dragonfish.
notifier.py – abstrae medio de notificación (mail, WhatsApp, etc.).
settings.py/.env – credenciales y parámetros.
2. Roadmap incremental
v0.1 – Core estable
Fix deduplicación (conjunto en memoria + archivo JSON).
Polling cada 60 s, listado últimas 50 ventas.
Logging estructurado.
v0.2 – Consulta Dragonfish
Implementar dragonfish_client.stock_total(sku) vía API.
Implementar reserva lógica (solo informar, sin movimiento).
v0.3 – Sincronización VTEX
Calcular nuevo stock = total – reservas pendientes.
1.
2.
3.
4.
5.
6.
7.
8.
•
•
•
•
•
•
•
•
•
•
•
1
PUT /api/fulfillment/pvt/stock para cada SKU.
v0.4 – Movimiento real Dragonfish
Endpoint MovimientoDeStock (POST).
Parámetros: Depósito=WOO, cantidad=–n, motivo=VENTA_VTEX.
v0.5 – Notificaciones
notifier.send(venta, detalle) .
Plantilla única para persona responsable.
v0.6 – Webhook
Reemplazar polling por webhook OMS → /webhook/vtex.
3. Requerimientos técnicos
Python 3.12, requests , fastapi para webhook, pyodbc para SQL fallback.
Persistencia: SQLite o JSON flat para orders_processed y reservas .
Manejo de errores y reintentos exponenciales (HTTP 429/500).
4. Validación
Ambiente staging con VTEX Sandbox y Dragonfish PRUEBA.
Tests unitarios por módulo + ensayo end‑to‑end (venta ficticia).
5. Pendientes
Definir medio y formato de notificación (WhatsApp vs correo).
Política de seguridad y cifrado de tokens.
Cron limpieza de órdenes antiguas en memoria.
•
•
•
•
•
•
•
•
•
•
•
•
•
•
2



# Diseño módulo `dragonfish_client.py`

Objetivo v0.2

* Consultar stock total por SKU en Dragonfish.
* Devolver mapa {depósito → stock} y el total.
* No descuenta stock real (sólo reserva lógica).

## API Dragonfish

```python
API_STOCK_URL = "http://deposito_2:8009/api.Dragonfish/ConsultaStockYPreciosEntreLocales/"
API_IDCLIENTE = "PRUEBA-WEB"
API_TOKEN     = "<token>"
```

### Función `stock_api(sku:str) -> dict[str,int]`

1. Separar `art, col, tal = sku.split('-')`  (la API sólo acepta ART).
2. GET API\_STOCK\_URL?query=<ART> con headers `IdCliente`, `Authorization`.
3. Filtrar resultados por SKU exacto `ART-COL-TAL`.
4. Construir `stock_map[base]+=qty` excluyendo bases bloqueadas (`MELI, ADMIN, …`).

## SQL de respaldo (código de barras)

```python
CONN_STR = r"DRIVER={ODBC Driver 17 for SQL Server};SERVER=ranchoaspen\zoo2025;DATABASE=master;Trusted_Connection=yes;"
```

### Función `codigo_barra(sku) -> str|None`

* Query `EQUI` (tabla de códigos de barras) para obtener `CCODIGO`.

### Función `stock_sql(codb:str) -> dict[str,int]`

* Para cada base `DRAGONFISH_*` en línea, sumar `COCANT` en `COMB` por `COCODIGO=codb`.
* Aplicar mismos filtros de bases.

## Wrapper alto nivel

```python
def stock_total(sku:str) -> tuple[dict[str,int], int]:
    m = stock_api(sku)
    if not m:                      # si API falla o 0 stock, intentar SQL
        codb = codigo_barra(sku)
        if codb:
            m = stock_sql(codb)
    return m, sum(m.values())
```

## Manejo de errores

* Reintento exponencial para API (configurable).
* `pyodbc.Error` ignorado por base offline.
* Registrar fallos.

---

Este módulo se importará desde el monitor cuando llegue una orden READY.
La reserva lógica se hará restando la cantidad vendida y almacenando en memoria (`reservas.json`) sin enviar movimiento real.
