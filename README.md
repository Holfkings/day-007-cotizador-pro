# CotizadorPro

**Motor de cotizaciones comerciales.** Calcula propuestas con cascada de descuentos
por concepto, bonificación de licencias, descuento por cliente, IVA y control de
vigencia — con aritmética exacta, sin errores de redondeo.

Demo funcional: **[holfkings.github.io/day-007-cotizador-pro](https://holfkings.github.io/day-007-cotizador-pro)**

---

## El problema que resuelve

Armar un presupuesto en una hoja de cálculo funciona hasta que aparecen cuatro cosas:

1. **Descuentos encadenados.** Un 8% por producto, una bonificación por licencia
   adicional, un 10% del cliente y un 3% extra "por cerrar rápido". Cuatro
   porcentajes sobre la misma base y ya nadie sabe sobre qué se aplicó cada uno.
   En la mayoría de herramientas esto termina en un error de margen de dos dígitos.
2. **Redondeos que no cuadran.** `float` de coma flotante suma `0,1 + 0,2 =
   0,30000000000000004`. Multiplicado por 10.000 líneas, son miles de pesos de
   diferencia entre lo que dice el presupuesto y lo que factura el sistema.
3. **Consistencia entre pantalla y factura.** El salesperson ve un total, el
   departamento financiero calcula otro, y la confianza en el sistema se cae.
4. **Control de vigencia.** Una propuesta de hace tres meses sigue abierta y nadie
   lo notó porque el total "se ve bien".

CotizadorPro define el **orden de aplicación** como parte del contrato, no como
detalle de implementación, y verifica que ambos motores —el de Python y el de la
demo web— produzcan el mismo centavo.

---

## Contrato de cálculo

El orden es fijo y está documentado:

| # | Concepto | Base de aplicación |
|---|----------|--------------------|
| 1 | Descuento por concepto | Subtotal del ítem (porcentual, o valor fijo acotado) |
| 2 | Bonificación | 25% del subtotal del ítem (licencia adicional) |
| 3 | Descuento del cliente | Base imponible, ya descontada |
| 4 | Descuento de la operación | Se suma al del cliente; el total se acota al 100% |
| 5 | IVA 19% | Subtotal final (cero si la base es cero) |

```
base_imponible = Σ subtotales − descuentos_por_concepto − bonificaciones
descuento_global = min(cliente% + operacion%, 100) × base_imponible
subtotal_final   = base_imponible − descuento_global
total            = subtotal_final × 1.19
```

```python
from cotizador import Cotizador

cz = Cotizador("cotizador.db")
cot = cz.nueva("901444777-2", validez_dias=12)      # reserva el consecutivo
cot = cz.agregar(cot.numero, "SW-LIC-PRO", 15, descuento_pct=8)
cot = cz.agregar(cot.numero, "HW-MN-27", 15, bonificacion=True)
cot = cz.agregar(cot.numero, "SRV-002", 12)
print(cot.total_legible)      # $39.227.517,00
```

---

## Uso

```bash
git clone https://github.com/Holfkings/day-007-cotizador-pro.git
cd day-007-cotizador-pro
```

Sin dependencias externas: la librería usa únicamente la biblioteca estándar.
Para correr las pruebas hace falta `pytest`.

```bash
python -m pytest                                    # 32 pruebas
python tools/check_demo_contract.py                 # paridad Python ↔ demo web
python -m cotizador.cli demo                        # recorrido end-to-end
```

### CLI

```bash
python -m cotizador.cli init                                   # catálogo y clientes
python -m cotizador.cli nueva --cliente 901444777-2 --validez 12
python -m cotizador.cli agregar COT-2026-000001 --sku SW-LIC-PRO --cantidad 15 --descuento 8
python -m cotizador.cli agregar COT-2026-000001 --sku HW-MN-27 --cantidad 15 --bonificacion
python -m cotizador.cli ver COT-2026-000001                   # detalle + totales
python -m cotizador.cli ver COT-2026-000001 --json            # salida para integraciones
python -m cotizador.cli estado COT-2026-000001 enviada
python -m cotizador.cli listar --estado aceptada
python -m cotizador.cli tablero
```

Salida real del comando `ver`:

```
COTIZACION COT-2026-000001
──────────────────────────────────────────────────────────────────────────────
  cliente                   Clinicas Vida S.A.S. (901444777-2)
  estado                    Borrador
  emitida                   2026-10-05 (vence 2026-10-17)

          SKU        CANT           P. UNIT      DESC             TOTAL
  ───────────  ──────────  ────────────────  ────────  ────────────────
   SW-LIC-PRO      15 lic     $1.490.000,00       -8%    $20.562.000,00
     HW-MN-27      15 und       $980.000,00    bonif.    $11.025.000,00
      SRV-002      12 mes       $420.000,00         -     $5.040.000,00

  subtotal lista            $42.090.000,00
  descuentos items          -$5.463.000,00
  descuento cliente         -$3.662.700,00
  subtotal                  $32.964.300,00
  IVA 19%                   $6.263.217,00
  TOTAL                     $39.227.517,00
```

---

## Arquitectura

```
cotizador/
  moneda.py    Aritmética: Decimal cuantizado, redondeo comercial half-up,
               formato regional es-CO/es-MX (1.234.567,89)
  modelo.py    Dominio puro. Producto, Cliente, ItemCotizacion, Cotizacion.
               Aquí vive el contrato de cálculo, sin dependencias de persistencia
  fachada.py   API de alto nivel: nueva/agregar/descuentar/cambiar_estado.
               Traduce excepciones de dominio a errores de negocio
  db.py        Persistencia SQLite (solo stdlib). Montos en centavos enteros,
               FK activas, índices por cotización y por estado
  cli.py       Interfaz de línea de comandos
  catalogo.py  Catálogo y clientes iniciales
tests/         32 pruebas: aritmética, cascada, ciclo de vida, persistencia
tools/         Verificador de paridad entre el motor Python y el de la demo
docs/          Demo web servida por GitHub Pages
```

Tres decisiones que sostienen el resto:

- **El dominio no importa la base de datos.** `modelo.py` es testeable sin disco y
  el motor se puede montar sobre otra persistencia sin tocar el cálculo.
- **Los montos se guardan como enteros en centavos.** SQLite no tiene decimal
  exacto; guardar texto flotante reintroduciría el error que el motor evita.
- **El tablero se calcula con el motor real**, no sumando una columna almacenada.
  El indicador y el detalle no pueden discrepar.

---

## La demo web

`docs/` es una demo navegable del motor, sin backend: mismo contrato de cálculo en
centavos enteros, con datos persistidos en `localStorage`. Incluye catálogo
buscable, ciclo de vida de la cotización (borrador → enviada → aceptada),
duplicado, tablero y pipeline por estado.

Como la demo reimplementa el cálculo, se añade un verificador que corre un banco de
casos por ambos motores y compara centavo a centavo:

```
$ python tools/check_demo_contract.py
OK    licencias + bonificacion + cliente 10%       total $39.227.517,00
OK    hardware sin descuento                       total $11.794.175,68
OK    cantidad grande + cliente 0%                 total $5.712.000,00
OK    desarrollo por usuario-mes                   total $17.268.568,38
OK    cotizacion vacia                             total $0,00
OK    descuentos al 100%                           total $0,00

OK  6 casos identicos en Python y en la demo web.
```

El paso corre en CI. Si la demo y la librería divergen, el pipeline falla.

---

## Pruebas

```
$ python -m pytest
32 passed
```

Cubren formato y redondeo, que un `float` no contamine los resultados, la cascada
completa de descuentos, bonificaciones, el IVA, el acoplamiento del descuento
global al 100%, el ciclo de vida (una cotización enviada no admite cambios; una
vacía no se puede aceptar), la numeración incremental, el error ante cliente o SKU
inexistente, la persistencia con recomputación idéntica y la consolidación del
tablero.

---

## Integración

La fachada es una API estable; `Cotizador` funciona como contexto y se cierra
limpio:

```python
with Cotizador("cotizador.db") as cz:
    ...
    cz.cotizacion("COT-2026-000001").to_dict()   # listo para JSON
```

`to_dict()` devuelve montos como cadenas decimales, no como `float`, para que el
consumidor no reintroduzca el error de redondeo al serializar.

---

## Licencia

MIT.