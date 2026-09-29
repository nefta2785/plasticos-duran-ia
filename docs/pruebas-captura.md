# Pruebas de `duran_captura_tianguis` y `duran_peso_variable`

Comandos para actualizar los módulos y correr sus pruebas automatizadas en **duranDEV**.
`duran_captura_tianguis` depende de `duran_peso_variable`: si cambia este último, hay que
correr las pruebas de los dos.
Todos se corren desde la carpeta `docker/` del proyecto:

```bash
cd docker
```

Las credenciales de la base las toma cada comando de las variables del contenedor
(`$HOST`, `$USER`, `$PASSWORD`…), así que **no hace falta abrir ni copiar `docker/.env`**.
Las comillas simples son importantes: hacen que esas variables se lean *dentro* del contenedor.

---

## 1. Qué comando usar según lo que cambió

| Qué cambió | Qué hacer |
|---|---|
| Solo archivos Python (`.py`) de modelos o controladores | Reiniciar Odoo (1a) |
| Archivos XML (vistas, plantillas, seguridad), `__manifest__.py`, campos nuevos en un modelo | Reiniciar Odoo (1a) **y** actualizar el módulo (1b) |
| Solo archivos de `static/` (JS, CSS) | Nada: basta recargar la página. La plantilla agrega `?v=…` con la fecha del archivo, así que el navegador (y el celular) descargan la versión nueva |
| Solo archivos de `tests/` | Nada: correr las pruebas (2) ya carga la versión nueva |

Ante la duda, hacer 1a + 1b + 2: no hace daño.

### 1a. Reiniciar Odoo

```bash
docker compose restart odoo
```

Carga el código Python nuevo. Tarda unos segundos; durante ese tiempo `http://localhost:8071` no responde.

### 1b. Actualizar el módulo

```bash
docker compose exec -T odoo sh -c 'odoo -d duranDEV --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" -u duran_captura_tianguis --stop-after-init --no-http'
```

Si el cambio fue en `duran_peso_variable`, poner `-u duran_peso_variable` (o
`-u duran_peso_variable,duran_captura_tianguis` si cambiaron los dos).

Equivale a darle **Actualizar** al módulo en Aplicaciones. Lanza un segundo proceso de Odoo
dentro del mismo contenedor que aplica los XML y los campos nuevos a duranDEV y **termina solo**
(`--stop-after-init`). No abre ningún puerto (`--no-http`) ni detiene el servicio normal, que se
entera del cambio y se recarga por su cuenta.

Debe terminar sin líneas `ERROR`. Al final aparece `Initiating shutdown`: es normal, es el
proceso auxiliar cerrándose, no el Odoo de siempre.

---

## 2. Correr las pruebas automatizadas

```bash
docker compose exec -T odoo sh -c 'odoo -d duranDEV --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" --test-enable --test-tags /duran_captura_tianguis,/duran_peso_variable --stop-after-init --http-port 8070 --max-cron-threads 0'
```

Cuándo usarlo: **después de cualquier cambio al módulo** (y después de 1a/1b si aplican), y
antes de cada commit.

Qué hace:

- Lanza un segundo proceso de Odoo que corre solo las pruebas de los dos módulos (`--test-tags`).
  Para correr solo uno, dejar solo su nombre en `--test-tags`.
- Las pruebas de páginas y rutas hacen peticiones HTTP reales, así que ese proceso levanta su
  propio servidor en el puerto **8070**. Es un puerto interno del contenedor: no está publicado
  hacia la Mac ni hacia la red, y no choca con el servicio normal (8069 dentro, 8071 fuera).
- Cada prueba crea sus propios usuarios, zonas, clientes y productos, y todo se **revierte** al
  terminar: duranDEV queda igual que antes.
- **Folios:** los números de órdenes (S000xx) y de entregas (WH/OUT/000xx) salen de secuencias
  de PostgreSQL que *no* se revierten. Por eso, mientras corren, las pruebas sustituyen el
  generador de folios por un contador falso: las órdenes y entregas de prueba salen con folios
  9xxxxx y la numeración real de duranDEV no se mueve.
- No usa el usuario Administrator ni contraseñas reales.

Resultado esperado, en las últimas líneas:

```
odoo.tests.result: 0 failed, 0 error(s) of N tests when loading database 'duranDEV'
```

Si algo falla, buscar en la salida las líneas `FAIL:` o `ERROR:`; debajo viene el detalle
(archivo, línea y qué se esperaba contra qué se obtuvo).

Para ver solo el resumen:

```bash
docker compose exec -T odoo sh -c 'odoo -d duranDEV --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" --test-enable --test-tags /duran_captura_tianguis,/duran_peso_variable --stop-after-init --http-port 8070 --max-cron-threads 0' 2>&1 | grep -E "FAIL|ERROR|tests when loading"
```

---

## 3. Correr las pruebas de pantalla (en la Mac)

```bash
node custom-addons/duran_captura_tianguis/tests/pantalla/correr.mjs
```

Se corre **desde la raíz del proyecto** (no desde `docker/`) y **en la Mac**, no dentro del
contenedor: necesita Node y Google Chrome, que están en la Mac. Tarda un par de segundos.

Cuándo usarlo: después de cambiar la plantilla de la página (`views/captura_templates.xml`) o
cualquier archivo de `static/` (JS o CSS), y antes de cada commit.

Qué hace:

- Abre la pantalla en Chrome **sin ventana** (headless), a tamaño de celular (390 × 844).
- **No usa Odoo ni la base de datos**: arma la página con la plantilla, el CSS y el JS reales
  del módulo, y responde a la pantalla con datos simulados (`tests/pantalla/simulacion.js`).
- Recorre la pantalla como quien captura (`tests/pantalla/escenario.js`): inicio (Pedido /
  Entrega), el modo Entrega completo, zonas, zona vacía,
  clientes, productos, sumar/restar/quitar, confirmación al salir, "Lo de siempre", resumen,
  doble toque, envío sin señal y reintento, error del servidor y pantalla de éxito.
- Chrome usa un perfil temporal propio: no toca tu Chrome ni sus pestañas.

Resultado esperado:

```
Pruebas de pantalla: N OK, 0 con falla, de N.
```

Si algo falla, se imprime cada falla con lo esperado y lo obtenido. Para ver todas las
verificaciones, también las que pasan: agregar `--detalle` al final del comando.

Si Chrome no está en la ruta normal de macOS:
`CHROME="/ruta/a/chrome" node custom-addons/duran_captura_tianguis/tests/pantalla/correr.mjs`

---

## 4. Antes de cada commit: las dos pruebas

```bash
cd docker
docker compose exec -T odoo sh -c 'odoo -d duranDEV --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" --test-enable --test-tags /duran_captura_tianguis,/duran_peso_variable --stop-after-init --http-port 8070 --max-cron-threads 0' 2>&1 | grep -E "FAIL|ERROR|tests when loading"
cd ..
node custom-addons/duran_captura_tianguis/tests/pantalla/correr.mjs
```

---

## 5. Qué cubre cada prueba

| Requisito | Pruebas del servidor (`tests/`) | Pruebas de pantalla |
|---|---|---|
| Solo usuarios con sesión y con el grupo "Captura tianguis" (también portal y sin grupo → rechazados) | `test_pagina_y_rutas.py`, `test_enviar.py`, `test_zona_y_seguridad.py` (el grupo incluye "Ventas: solo sus documentos") | — |
| Zonas = etiquetas de contacto, sin nombres fijos; zona vacía no rompe | `test_pagina_y_rutas.py` | Zonas, zona vacía |
| Cliente con varias zonas aparece en cada una | `test_pagina_y_rutas.py` | — |
| Catálogo por categoría, nombre + atributo, precio "$85/kg" / "c/u", sin peso variable sin precio | `test_pagina_y_rutas.py` | Productos |
| Un toque suma 1, restar, quitar, cantidades enteras con su unidad, indicador suma cantidades | — | Productos |
| Confirmar antes de vaciar el pedido (también con "atrás" del celular) | — | Confirmación |
| "Lo de siempre": 90 días, máximo 8, por frecuencia; aparece primero; se comporta como el catálogo | `test_lo_de_siempre.py` (incluye que el costo no crece con el historial) | Lo de siempre |
| Resumen sin precios ni total | — | Resumen |
| Orden siempre nueva, con zona elegida y quien captura como vendedor, confirmada, con entrega, sin impuestos | `test_enviar.py` | Envío |
| Sin duplicados (doble toque, reintento sin señal, token único en la base) | `test_enviar.py`, `test_zona_y_seguridad.py` | Envío |
| Validaciones (cantidades, productos, zona, cliente, token) sin dejar órdenes a medias | `test_enviar.py` | Error del servidor |
| Zona en la orden: vistas, agrupar por Zona, no se copia al duplicar, no se borra si está en uso | `test_zona_y_seguridad.py` | — |
| Inicio con tres modos (Pedido, Entrega y Cobro; Cobro deshabilitado hasta tener sus pantallas); Regresar desde Zonas vuelve al Inicio, también después de enviar pedidos | — | Inicio |
| Pantallas del modo Entrega: solo clientes con pendientes; lista por producto con precio, un campo de peso por rollo con eco "1.250 kg · $106.25", marca "Sin existencia en sistema", «No se lo llevó» en todo renglón (y deshacer), "−" que no baja de 1; peso vacío bloquea y señala el rollo; peso bloqueado regresa a la lista con motivo y sugerencia; advertencias confirmadas una por una; resumen con importes, lo no llevado aparte y total; cliente que no se lleva nada con confirmación extra; doble toque, sin señal y reintento con el mismo token; otra persona cambió algo (recarga sin perder pesos); éxito con "Cobrar"; "El cliente quiere algo más" y regreso | — | Entrega |
| Modo Entrega, rutas de lectura: clientes de la zona con entregas de venta pendientes (sin validadas, canceladas, devoluciones, "Devolución a proveedor" ni salidas sin orden de venta); todas las pendientes sin importar vendedor ni zona de la orden; agrupado por producto de la orden más antigua a la más nueva, rollos uno por uno, marca "sin existencia en sistema", precios (por kg vigente / de la línea de venta); no lee clientes de otra zona ni fuera de zonas | `test_entrega_lectura.py` (sin grupo y sin sesión también en `test_pagina_y_rutas.py`) | — |
| Modo Entrega, vista previa: total igual al de la factura real (rollos y productos mezclados, dos facturas, con y sin IVA) e importe por línea igual al de su línea de factura; precio por kg vigente; rechaza rollos/productos que no son del cliente o no están pendientes, repetidos, cantidades no enteras o mayores a lo pendiente; bloqueos y advertencias de peso con los límites de los parámetros del sistema; sugerencia "1250 → 1.250"; no escribe nada en la base | `test_entrega_vista_previa.py` | — |
| Modo Entrega, confirmación: peso y precio congelado llegan a la factura y su total es el de la vista previa; completa, parcial (lo demás se cancela sin backorder), orden sin nada entregado (se cancela completa), sin existencia (inventario en negativo y nota); reparto de la orden más antigua a la más nueva; cantidad pedida bajada a lo entregado con registro en el historial a nombre de quien captura y sin re-tarifar; "Lo de siempre" ignora líneas en 0; doble envío con el mismo token; rechazo si otra persona validó, canceló o modificó una entrega (y no toca entregas que la pantalla no mostró); falla a la mitad sin dejar nada; peso bloqueado rechazado; Cambio de producto sobre un rollo entregado desde la app; el sudo solo escribe la cantidad de las líneas de esta entrega; fuera de zona o del filtro, sin grupo y sin sesión: nada | `test_entrega_confirmar.py` | — |
| Bitácora de entregas: token único y con formato, quien captura solo crea y ve las suyas y no las modifica ni borra, el gerente ve todas, vendedor sin grupo no la ve, vistas y menú | `test_bitacora.py` | — |
| Bitácora de cobros: token único y con formato, tipo de pago obligatorio; quien captura solo crea y ve los suyos (y sus documentos) y no los modifica ni borra, aunque las facturas y el pago sean de otro vendedor; el gerente ve todos con facturas, pago y documentos, quien cobra no ve esos campos y abre su cobro sin error; vendedor sin grupo no la ve; vistas y menú | `test_cobro_bitacora.py` | — |
| Modo Cobro, rutas de lectura: clientes de la zona con lo entregado sin facturar, saldo pendiente o factura en borrador (no los que solo tienen pedidos sin entregar o saldo a favor; también por una dirección del cliente); detalle con lo entregado sin facturar (de cualquier vendedor, precio por kg congelado), igual línea por línea al de las facturas que hará Odoo (dos por dirección); saldo anterior real (ajustes a mano y pagos parciales) en el orden en que Odoo aplica un pago (comprobado contra Odoo); saldo a favor (notas de crédito y pagos sin aplicar) restado del total, y lo que sobra; saldo igual al "Por cobrar" de Odoo; factura o nota de crédito en borrador: aviso y no se puede cobrar, sin tocarla; devolución sin nota de crédito: fuera del cobro y con aviso; fuera de zona, cliente o zona inexistentes; no escribe nada en la base | `test_cobro_lectura.py` (sin grupo y sin sesión también en `test_pagina_y_rutas.py`) | — |
| Modo Cobro, confirmación con "No pagó hoy": total de la factura = vista previa de la entrega = bitácora de entregas = detalle del cobro; agrupación como Odoo (dos órdenes → una factura, otra dirección → otra); sin el permiso acotado Odoo daría una factura vacía y la ruta produce la completa; el sudo solo factura, publica y concilia lo del cliente (espía), con el usuario de quien cobra, aunque la pantalla mande ids ajenos; "Creado por" y autor del historial = quien cobra; saldo a favor aplicado a la factura más antigua (renglones antes/aplicado/después, saldo = el de Odoo) y mayor que la deuda (factura "Revertida", como la marca Odoo); solo saldo anterior sin crear facturas; devoluciones sin nota de crédito fuera de la factura (misma orden); bloqueo de órdenes, líneas y documentos del cliente, y mensaje si alguien más los tiene; doble toque; factura, borrador o pago hecho desde Odoo entre lectura y confirmación → "cambiaron" sin crear nada; borrador del cliente rechazado; falla a la mitad sin dejar nada; nada que cobrar; tipos de pago aún no disponibles; datos inválidos; fuera de zona; Cambio de producto sobre un rollo cobrado con "No pagó hoy" | `test_cobro_confirmar.py` (sin grupo y sin sesión también en `test_pagina_y_rutas.py`) | — |

Pruebas de `duran_peso_variable` (`custom-addons/duran_peso_variable/tests/`):

| Requisito | Pruebas |
|---|---|
| Un rollo por línea, movimiento de rollo máximo 1, factura por peso real de la entrega, la devolución no arrastra el peso | `test_peso_variable.py` |
| Precio por kg congelado al validar la entrega: la factura lo usa aunque el producto cambie de precio (también al corregir el peso en la factura); entregas antiguas sin precio congelado usan el vigente | `test_precio_congelado.py` |
| Cambio de producto (rollo y producto normal): abono y rollo nuevo al precio vigente, nota de crédito, factura nueva cobrada | `test_precio_congelado.py` |
| Al validar una entrega (desde la app o desde Odoo) el peso y el precio congelado pasan a la línea de venta: la orden muestra el monto de la vista previa, la bitácora y la factura; cambiar el precio después no cambia la línea, y una línea facturada nunca cambia de precio; las devoluciones no tocan la línea; factura y nota de crédito salen igual; el sudo solo escribe peso y precio de los rollos validados (vendedor con orden de otro vendedor, usuario solo de almacén); el campo nuevo no recalcula líneas existentes al actualizar | `test_sincronizar_linea.py` (y `test_entrega_confirmar.py` en la captura) |

## 6. Qué NO cubren las pruebas automáticas

Hay que revisarlo a mano, en el celular:

- Que se lea bien al sol y que los botones se alcancen con una mano.
- El teclado, el zoom y el botón "atrás" físico de cada celular real.
- Una red real que se cae a la mitad del envío (las pruebas lo simulan).
- El inicio de sesión real y cuánto dura la sesión en el celular.
