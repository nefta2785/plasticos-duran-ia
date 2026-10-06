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
| Archivos XML (vistas, plantillas, seguridad), `__manifest__.py`, campos nuevos en un modelo | Actualizar el módulo (1b) **y después** reiniciar Odoo (1a) |
| Solo archivos de `static/` (JS, CSS) | Nada: basta recargar la página. La plantilla agrega `?v=…` con la fecha del archivo, así que el navegador (y el celular) descargan la versión nueva |
| Solo archivos de `tests/` | Nada: correr las pruebas (2) ya carga la versión nueva |

Ante la duda, hacer 1b + 1a + 2: no hace daño.

**Regla: después de actualizar un módulo, SIEMPRE reiniciar Odoo (1a) y abrir en
`http://localhost:8071` la pantalla afectada, antes de dar el cambio por terminado.** También
cuando el módulo se actualizó al correr pruebas con `-u`. Actualizar el módulo guarda las vistas
nuevas en la base, pero el servicio de 8071 sigue con el código Python con el que arrancó: si la
vista usa un campo nuevo, la pantalla falla con `"modelo"."campo" field is undefined` hasta
reiniciar. Así pasó con la Hoja de carga (campo `unidad_producto_id`).

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
(`--stop-after-init`). No abre ningún puerto (`--no-http`) ni detiene el servicio normal. El
servicio normal toma los datos nuevos de la base (vistas, menús), pero **no** el código Python
nuevo (modelos, campos, controladores): por eso después hay que reiniciarlo (1a).

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

- Abre la pantalla en Chrome **sin ventana** (headless) al tamaño del iPhone 16 (393 × 852).
  Chrome sin ventana no dibuja a menos de 500 px de ancho aunque se le pida, así que la página
  se carga dentro de un marco (iframe) de 393 × 852. En cada pantalla revisa que el ancho sea
  el del celular y que nada se salga por los lados.
- **No usa Odoo ni la base de datos**: arma la página con la plantilla, el CSS y el JS reales
  del módulo, y responde a la pantalla con datos simulados (`tests/pantalla/simulacion.js`).
- Recorre la pantalla como quien captura (`tests/pantalla/escenario.js`): inicio (Pedido /
  Entrega / Cobro), los modos Entrega y Cobro completos, zonas, zona vacía,
  clientes, productos, sumar/restar/quitar, confirmación al salir, "Lo de siempre", resumen,
  doble toque, envío sin señal y reintento, error del servidor y pantalla de éxito; la franja
  de abajo con su aviso "Falta un paso", la pregunta al salir con "hacerlo ahora", los
  recordatorios de Inicio y "Continuar". Algunas pantallas se revisan también a 393 × 780
  (el marco se achica un momento) para comprobar que la franja de abajo no tape nada.
- La página se prueba dos veces, una después de la otra: como la ve un administrador o gerente
  (con botón "Salir") y como la ve el usuario de tianguis (sin "Salir" en Inicio).
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
| Salir con algo sin enviar, confirmar o registrar (INICIO, Regresar, "atrás" del celular, abrir el cobro de otro cliente): pregunta "Este pedido NO se ha enviado" / "Esta entrega NO se ha confirmado" / "Este cobro NO se ha registrado"; verde arriba "✓ … ahora" en la pantalla final o "Revisar y …" antes de ella; "Salir sin …" vacía el pedido y conserva entrega y cobro; tocar el fondo o "atrás" con la pregunta abierta = quedarse (el historial queda igual); "ahora" con éxito se queda en el éxito, sin señal o con error se queda con el mensaje rojo, doble toque sin duplicar; Regresar a la pantalla anterior no pregunta | — | Confirmación, Inicio con pedido, Entrega: pendientes, Cobro |
| Qué cuenta como pendiente (`pendientes()`, también para el aviso de recarga): pedido con productos; entrega con algo capturado o ya revisada aunque no cambie nada; cobro con "Pagó todo", "Pagó una parte" o "No pagó hoy" elegido o monto escrito; lo capturado de movimientos que ya no están pendientes se poda (no cuenta) | — | Entrega: pendientes, Cobro |
| Franja de abajo igual en las tres operaciones: blanca con raya arriba, botón verde ≥72px redondeado con borde, sombra y 16px a los lados, verbo arriba (26px) y conteo o total abajo (17px); aviso ámbar "Falta un paso…" solo en la pantalla final; "Registrar cobro" en la franja; nada del contenido tapado a 393 × 852 ni a 393 × 780; títulos "Falta enviar el pedido" / "Falta confirmar la entrega" / "Falta registrar el cobro" | — | Resumen, Entrega, Cobro |
| Recordatorios en Inicio (entregas y cobros sin confirmar): máximo 2 renglones y "y N más"; "Continuar" abre esa pantalla con el historial armado (Regresar funciona igual); con 2 y "y 1 más" los 4 botones caben sin deslizar para el usuario de tianguis | — | Entrega: pendientes, Cobro, Inicio de tianguis |
| "+ Cliente nuevo" (solo Pedido, también con zona vacía; nunca en Entrega ni Cobro): pantalla con la barra de PEDIDO, "Zona: …" automática, campo dentro de un formulario (mayúscula en cada palabra, sin autocompletar ni corrector, Enter guarda) y "Guardar y levantar pedido" justo debajo, visibles con el teclado (393 × 480); alta con nombre, la zona de la pantalla y nada más (empresa, rango de cliente 1, nota "Creado desde la app el … por …"), lo demás que mande la pantalla se ignora; sudo solo en el `create` y quien captura sigue sin poder crear contactos ni zonas; nombre: espacios, 2 letras a 60 caracteres, sin emojis ni caracteres de control, mayúsculas como se escribieron; parecidos (acentos, mayúsculas, espacios, "contiene" con 4 o más, otra zona, archivados; máximo 5, primero idénticos y de la misma zona) en la misma pantalla sin entrada nueva en el historial; idéntico activo en la misma zona: solo "Es este"; token sin duplicar (doble toque, sin señal y reintento); dos personas con el mismo nombre a la vez (reintento de Odoo); al guardar, directo a Productos y Regresar a Clientes ya con el nuevo; texto sin guardar no cuenta como pendiente; flujo completo pedido → entrega → cobro "Pagó todo" con factura publicada, y aparece en Entrega, Cobro, Acomodo y Pendiente de cobro | `test_cliente_nuevo.py` (sin grupo y sin sesión también en `test_pagina_y_rutas.py`) | Cliente nuevo, Zonas, Clientes, Entrega, Cobro |
| Pantallas de éxito: bloque verde claro con borde verde, palomeo de 140px, "PEDIDO ENVIADO" / "ENTREGA CONFIRMADA" / "COBRO REGISTRADO" a 34px; también sin datos (atrás o adelante) | — | Envío, Entrega, Cobro |
| "Lo de siempre": 90 días, máximo 8, por frecuencia; aparece primero; se comporta como el catálogo | `test_lo_de_siempre.py` (incluye que el costo no crece con el historial) | Lo de siempre |
| Resumen sin precios ni total | — | Resumen |
| Orden siempre nueva, con zona elegida y quien captura como vendedor, confirmada, con entrega, sin impuestos | `test_enviar.py` | Envío |
| Sin duplicados (doble toque, reintento sin señal, token único en la base) | `test_enviar.py`, `test_zona_y_seguridad.py` | Envío |
| Validaciones (cantidades, productos, zona, cliente, token) sin dejar órdenes a medias | `test_enviar.py` | Error del servidor |
| Zona en la orden: vistas, agrupar por Zona, no se copia al duplicar, no se borra si está en uso | `test_zona_y_seguridad.py` | — |
| Inicio con tres modos (Pedido, Entrega y Cobro); Regresar desde Zonas vuelve al Inicio, también después de enviar pedidos | — | Inicio |
| Pantallas del modo Cobro: solo clientes con algo por cobrar; detalle con lo entregado sin facturar (peso de los rollos, precios e importes), saldo anterior (fecha y saldo), saldo a favor restado y TOTAL A COBRAR grande, montos siempre "$1,234.50"; borrador: aviso rojo arriba y repetido debajo del total, sin botones de pago (también con líneas entregadas repetidas y saldo anterior, como Mario fruta); devolución sin nota de crédito: aviso informativo; «Pagó todo» principal y las otras dos secundarias; «Pagó una parte» con teclado decimal, coma o punto, eco en vivo "Recibe … · Queda debiendo …" y sin continuar con vacío, 0, más del total o 3 decimales; «No pagó hoy» con confirmación extra; doble toque, sin señal y reintento con el mismo token; "cambiaron": mensaje y detalle recargado (token nuevo); aviso antes de recargar con un monto escrito; éxito "Cobrado" y "Queda debiendo", siguiente cliente y cambiar de zona | — | Cobro |
| Pantallas del modo Entrega: solo clientes con pendientes; lista por producto con precio, un campo de peso por rollo con eco "1.250 kg · $106.25", marca "Sin existencia en sistema", «No se lo llevó» en todo renglón (y deshacer), "−" que no baja de 1; peso vacío bloquea y señala el rollo; peso bloqueado regresa a la lista con motivo y sugerencia; advertencias confirmadas una por una; resumen con importes, lo no llevado aparte y total; cliente que no se lleva nada con confirmación extra; doble toque, sin señal y reintento con el mismo token; otra persona cambió algo (recarga sin perder pesos); éxito con "Cobrar"; "El cliente quiere algo más" y regreso | — | Entrega |
| Modo Entrega, rutas de lectura: clientes de la zona con entregas de venta pendientes (sin validadas, canceladas, devoluciones, "Devolución a proveedor" ni salidas sin orden de venta); todas las pendientes sin importar vendedor ni zona de la orden; agrupado por producto de la orden más antigua a la más nueva, rollos uno por uno, marca "sin existencia en sistema", precios (por kg vigente / de la línea de venta); no lee clientes de otra zona ni fuera de zonas | `test_entrega_lectura.py` (sin grupo y sin sesión también en `test_pagina_y_rutas.py`) | — |
| Modo Entrega, vista previa: total igual al de la factura real (rollos y productos mezclados, dos facturas, con y sin IVA) e importe por línea igual al de su línea de factura; precio por kg vigente; rechaza rollos/productos que no son del cliente o no están pendientes, repetidos, cantidades no enteras o mayores a lo pendiente; bloqueos y advertencias de peso con los límites de los parámetros del sistema; sugerencia "1250 → 1.250"; no escribe nada en la base | `test_entrega_vista_previa.py` | — |
| Modo Entrega, confirmación: peso y precio congelado llegan a la factura y su total es el de la vista previa; completa, parcial (lo demás se cancela sin backorder), orden sin nada entregado (se cancela completa), sin existencia (inventario en negativo y nota); reparto de la orden más antigua a la más nueva; cantidad pedida bajada a lo entregado con registro en el historial a nombre de quien captura y sin re-tarifar; "Lo de siempre" ignora líneas en 0; doble envío con el mismo token; rechazo si otra persona validó, canceló o modificó una entrega (y no toca entregas que la pantalla no mostró); falla a la mitad sin dejar nada; peso bloqueado rechazado; Cambio de producto sobre un rollo entregado desde la app; el sudo solo escribe la cantidad de las líneas de esta entrega; fuera de zona o del filtro, sin grupo y sin sesión: nada | `test_entrega_confirmar.py` | — |
| Bitácora de entregas: token único y con formato, quien captura solo crea y ve las suyas y no las modifica ni borra, el gerente ve todas, vendedor sin grupo no la ve, vistas y menú | `test_bitacora.py` | — |
| Bitácora de cobros: token único y con formato, tipo de pago obligatorio; quien captura solo crea y ve los suyos (y sus documentos) y no los modifica ni borra, aunque las facturas y el pago sean de otro vendedor; el gerente ve todos con facturas, pago y documentos, quien cobra no ve esos campos y abre su cobro sin error; vendedor sin grupo no la ve; vistas y menú | `test_cobro_bitacora.py` | — |
| Modo Cobro, rutas de lectura: clientes de la zona con lo entregado sin facturar, saldo pendiente o factura en borrador (no los que solo tienen pedidos sin entregar o saldo a favor; también por una dirección del cliente); detalle con lo entregado sin facturar (de cualquier vendedor, precio por kg congelado), igual línea por línea al de las facturas que hará Odoo (dos por dirección); saldo anterior real (ajustes a mano y pagos parciales) en el orden en que Odoo aplica un pago (comprobado contra Odoo); saldo a favor (notas de crédito y pagos sin aplicar) restado del total, y lo que sobra; saldo igual al "Por cobrar" de Odoo; factura o nota de crédito en borrador: aviso y no se puede cobrar, sin tocarla; devolución sin nota de crédito: fuera del cobro y con aviso; fuera de zona, cliente o zona inexistentes; no escribe nada en la base | `test_cobro_lectura.py` (sin grupo y sin sesión también en `test_pagina_y_rutas.py`) | — |
| Modo Cobro, confirmación con "No pagó hoy": total de la factura = vista previa de la entrega = bitácora de entregas = detalle del cobro; agrupación como Odoo (dos órdenes → una factura, otra dirección → otra); sin el permiso acotado Odoo daría una factura vacía y la ruta produce la completa; el sudo solo factura, publica y concilia lo del cliente (espía), con el usuario de quien cobra, aunque la pantalla mande ids ajenos; "Creado por" y autor del historial = quien cobra; saldo a favor aplicado a la factura más antigua (renglones antes/aplicado/después, saldo = el de Odoo) y mayor que la deuda (factura "Revertida", como la marca Odoo); solo saldo anterior sin crear facturas; devoluciones sin nota de crédito fuera de la factura (misma orden); bloqueo de órdenes, líneas y documentos del cliente, y mensaje si alguien más los tiene; doble toque; factura, borrador o pago hecho desde Odoo entre lectura y confirmación → "cambiaron" sin crear nada; borrador del cliente rechazado; falla a la mitad sin dejar nada; nada que cobrar; tipo de pago inválido; datos inválidos; fuera de zona; Cambio de producto sobre un rollo cobrado con "No pagó hoy" | `test_cobro_confirmar.py` (sin grupo y sin sesión también en `test_pagina_y_rutas.py`) | — |
| Modo Cobro, "Pagó todo" y "Pagó una parte": estados por factura con saldo anterior de $100 y $300 de hoy (pagó $400: ambas pagadas; $250: la primera pagada y la segunda parcial con $150; $50: la primera parcial con $50 y la segunda sin pagar), con renglones antes/aplicado/después y saldo igual al de Odoo; lo pendiente aparece como saldo anterior en el siguiente cobro y se puede cobrar; "Pagó todo" con saldo a favor; montos de más, 0, negativos, con 3 decimales o que no son número: rechazo sin crear nada (justo el total sí); cero o dos diarios de efectivo: rechazo sin crear nada ("No pagó hoy" no lo necesita); el pago solo usa el diario de efectivo y las líneas por cobrar del cliente, un solo pago con la diferencia abierta, aunque la pantalla mande otros ids (espía); "Creado por" = quien cobra, fecha de hoy y referencia "Cobro en tianguis #número"; pago desde Odoo entre lectura y confirmación → "cambiaron" sin crear nada; doble toque: un solo pago; falla después de crear el pago sin dejar nada; arqueo: efectivo recibido de la bitácora del día = pagos en el diario de efectivo creados por quien cobra ese día | `test_cobro_pago.py` | — |
| Modo Cobro, arqueo en "Resumen de ventas": abre con el filtro "Hoy" (el día de hoy en la zona horaria de quien consulta), agrupado por día y luego por quién cobró; columnas fecha y hora, quién cobró, cliente, zona, cómo pagó, total a cobrar, efectivo recibido y queda pendiente, con sumas; la suma de efectivo del grupo de hoy de cada persona = los pagos en el diario de efectivo creados por ella hoy (sin el cobro de ayer ni un pago hecho desde Odoo por otra persona); quien captura solo ve su grupo y el gerente de Ventas ve el de todos | `test_cobro_arqueo.py` | — |
| /captura como inicio: el usuario de tianguis (grupo Captura, sin ser gerente de Ventas ni administrador) llega a /captura después de iniciar sesión, aunque el login traiga otro destino (/odoo, Discuss, una acción); gerente de Ventas, Ajustes y Permisos de acceso entran a Odoo como siempre, con o sin destino; sin el grupo no cambia; el servidor decide el botón "Salir" (`data-salir` solo para gerentes y administradores); app "Captura" en el menú de Odoo (abre /captura en la misma pestaña) para todo el grupo, que no es la primera app; cambiar la contraseña cierra las sesiones abiertas | `test_inicio.py` | Inicio de tianguis |
| Hoja de carga (Ventas › Órdenes › Hoja de carga): vista SQL con un renglón por producto y zona y el total pendiente desde los movimientos de entrega abiertos (misma regla que el modo Entrega): cuenta lo reservado, lo "sin existencia", lo parcialmente disponible, lo que falta de un parcial con backorder y lo atrasado; no cuenta lo parcial sin backorder, lo bajado por el modo Entrega, devoluciones ni órdenes canceladas; pedido nuevo del modo Pedido aparece al volver a consultar; zona de la orden o, si no tiene, la única del cliente (si no, sin zona); total en la unidad del producto (500 g + 2 kg = 2.5 kg; rollos en piezas). Marcas de "Acomodado": guarda la cantidad que se veía en pantalla; doble toque; "Se agregó 1" / "Se agregaron X" (con decimales en kg) / "Ahora son N"; volver a marcar deja verde; "Quitar" idempotente; día nuevo sin marcas; producto nuevo después de otras marcas; pendiente 0 deja de aparecer; mismo producto en dos zonas con marcas independientes (un pedido en otra zona no cambia el aviso); sin zona también se marca; otro gerente reescribe la misma marca; marca única por producto + zona + fecha (también sin zona); cantidad inválida no marca. Columna de cantidad ("4 pz", "2,5 kg", coma de es_419) y aviso con el separador del idioma. Lista: sin columna Zona, abre agrupada por zona con las zonas abiertas (expand), recarga automática (js_class), colores, cuadro de marcar ☐ / ☑ (fa-square-o / fa-check-square-o) con su nombre, condición y contexto, sin suma, búsqueda solo por zona; menú, acción y datos solo para gerente de Ventas (la mamá y un vendedor no leen ni marcan) | `test_hoja_carga.py` | — |
| Pendiente de cobro (Ventas › Órdenes › Pendiente de cobro): vista SQL con dos tipos de renglón, "Entregado hoy" (movimientos validados hoy, día de calendario en México, sin facturar) y "Saldo anterior" (facturas publicadas con saldo, saldos a favor en negativo y entregas de días anteriores sin facturar). Cliente con entrega hoy sin deuda; cliente con deuda y sin entrega hoy (aparece igual); pago parcial hoy (lo de hoy pasa a saldo de su factura, 0 días); entrega anterior sin cobrar y línea entregada en partes; saldo a favor (nota de crédito y pago sin aplicar); dirección hija agrupada en su cliente principal; Total a cobrar igual al de la app de Cobro (rollo, descuento, kg con centavos, pago parcial, nota de crédito y devolución de hoy); "hoy" con la hora de México cerca de medianoche; zona de la orden o, si no tiene, la única del cliente (si no, sin zona), también en lo entregado hoy; rojo con más de 7 días (7 no, 8 sí; nunca lo de hoy); "Días de antigüedad" con el máximo en el encabezado del cliente; sumas por Zona › Cliente; columnas, orden (hoy por pedido, saldos del más antiguo al más reciente), filtro "Solo con saldo anterior" (sin "Hoy"); importe del movimiento como lo factura Odoo y recalculado si cambia el precio o el descuento; menú, acción y datos solo para gerente de Ventas | `test_pendiente_cobro.py` | — |
| Vistas de cada acción del módulo: cada acción de ventana abre vistas de su propio modelo (`res_model`) y con campos que ese modelo tiene (detecta, por ejemplo, `"stock.move"."estado" field is undefined`) | `test_vistas_acciones.py` | — |

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
- Que la Hoja de carga (backend de Odoo) quepa a lo ancho del celular: ver la sección 8.

## 7. Lista de verificación en el celular: modo Cobro

Con entregas reales hechas desde el modo Entrega, en duranDEV. Hace falta una zona con dos
clientes de prueba (A y B) y un usuario del grupo "Captura tianguis".

0. **Preparar.** Reiniciar Odoo para que tome el código nuevo (`cd docker`,
   `docker compose restart odoo`) y abrir `/captura` en el celular.
1. **Entrega a A.** Modo Entrega › zona › A: entregar un rollo (por ejemplo 1.250 kg) y un
   producto. Anotar el "Cobrar: $X" de la pantalla final.
2. **Cobro de A, "Pagó una parte".** Inicio › Cobro › zona › A.
   - Revisar: los productos, el peso del rollo, los importes y que el TOTAL A COBRAR sea $X.
   - Tocar "Pagó una parte". Probar vacío, `0`, más que el total y `12.345`: cada uno muestra
     un mensaje y no deja registrar. Sin comas de miles: `1,300` es 1.3 con 3 decimales y se
     rechaza; se escribe `1300`.
   - Escribir un monto menor, con coma (por ejemplo `100,50`): el eco dice
     "Recibe $100.50 · Queda debiendo $…".
   - Intentar recargar la página: debe preguntar antes.
   - "✓ REGISTRAR COBRO" (botón verde de abajo): pantalla "COBRO REGISTRADO" con
     "Cobrado: $100.50" y "Queda debiendo: $…".
   - En Odoo, Facturación › Clientes › Facturas: una factura de A, publicada, por $X y
     "Parcialmente pagado" con el saldo que dijo la pantalla.
3. **Saldo anterior.** Hacer otra entrega a A. Cobro › A: se ven lo entregado nuevo y, en
   "Saldo anterior", la factura del paso 2 con su fecha y su saldo; el total es la suma.
   "Pagó todo" › Registrar: "Cobrado" por el total y sin "Queda debiendo". En Odoo, las dos
   facturas de A quedan "Pagado".
4. **"No pagó hoy".** Hacer una entrega a B. Cobro › B › "No pagó hoy" › Registrar: sale
   "La deuda de $Y quedará pendiente". Tocar "No" (no pasa nada), otra vez Registrar y "Sí".
   En Odoo, la factura de B queda publicada y "No pagado". Al volver a Cobro › B aparece
   como saldo anterior.
5. **Factura en borrador.** En Odoo, crear para B una factura sin confirmarla. Cobro › B:
   aviso rojo "Este cliente tiene una factura en borrador…" arriba y otra vez debajo del
   total, y sin botones de pago. Publicarla
   o cancelarla en Odoo y volver a abrir a B: ya se puede cobrar.
6. **Otra persona cobra a la vez.** Abrir Cobro › B en el celular y quedarse en el detalle.
   En Odoo, registrar un pago de $10 a una factura de B. En el celular, "Pagó todo" ›
   Registrar: sale "Otra persona facturó o cobró…" y el total baja $10.
7. **Sin señal** (opcional). Poner el modo avión justo antes de "Registrar cobro": sale el
   mensaje de que no se sabe si llegó. Quitar el modo avión y registrar otra vez: queda un
   solo cobro en "Resumen de ventas".
8. **Arqueo del día.**
   - Ventas › Órdenes › Resumen de ventas, filtro Fecha = hoy y agrupar por "Cobró": la suma
     de "Efectivo recibido" del usuario.
   - Facturación › Clientes › Pagos, filtrar Diario = Efectivo y fecha de hoy, agrupar por
     "Creado por" (agrupación personalizada): la suma del mismo usuario debe ser igual.
   - Cada pago tiene la referencia "Cobro en tianguis #N", igual al número del cobro.
9. **Al sol y con una mano.** Que el total, "Pagó todo" y el campo del monto se lean y se
   alcancen bien. Con un total de más de $1,000, revisar que se vea como "$1,234.50".

## 7b. Lista de verificación en el celular: "Falta un paso"

En duranDEV, con el usuario de tianguis, en el celular (vertical). Hace falta un cliente con
entregas pendientes y otro con algo por cobrar.

1. **Pedido.** Pedido › zona › cliente › agregar 2 productos › "REVISAR PEDIDO ›".
   - Arriba dice "Falta enviar el pedido"; abajo, el aviso amarillo "Falta un paso: este pedido
     todavía NO se ha enviado" y el botón verde "✓ ENVIAR PEDIDO" con "2 productos en el pedido"
     en chico. Deslizar hasta abajo: "Para cambiar algo, toca Regresar." se ve completo, sin que
     la franja lo tape.
   - Tocar INICIO: sale "Este pedido NO se ha enviado" con "✓ Enviar pedido ahora" (verde) y
     "Salir sin enviar". Tocar fuera de la ventana: se queda en el resumen.
   - Poner el modo avión, INICIO › "✓ Enviar pedido ahora": se queda en el resumen con el
     mensaje rojo. Quitar el modo avión, INICIO › "✓ Enviar pedido ahora": "PEDIDO ENVIADO"
     con el palomeo grande. En Odoo hay **una sola** orden.
2. **Entrega.** Entrega › zona › cliente › capturar un peso › INICIO: "Esta entrega NO se ha
   confirmado" con "Revisar y confirmar". Tocar "Salir sin confirmar".
   - En Inicio, arriba de los 4 botones: "⚠ Entrega sin confirmar: [cliente] · Continuar ›" y
     los 4 botones se ven sin deslizar. Tocarlo: regresa a la entrega con el peso.
   - "REVISAR ENTREGA ›" › resumen con "Falta confirmar la entrega" y el aviso amarillo ›
     "✓ CONFIRMAR ENTREGA": "ENTREGA CONFIRMADA". El aviso de Inicio desaparece.
3. **Cobro.** Cobro › zona › cliente › "Pagó todo": "Falta registrar el cobro", el aviso
   amarillo y "✓ REGISTRAR COBRO" en la franja de abajo (ya no en medio de la pantalla).
   - Regresar dos veces (al detalle no pregunta; a los clientes sí) › "Salir sin registrar".
   - Tocar otro cliente: sale "Este cobro NO se ha registrado" del primero. "Revisar y
     registrar" lleva a su confirmación; registrar: "COBRO REGISTRADO".
4. **"Atrás" del celular** en cada caso: pregunta igual que Regresar; con la pregunta abierta,
   "atrás" la cierra y se queda en la pantalla.
5. **Al sol y con una mano:** que el aviso amarillo se lea, que el botón verde se distinga de la
   barra verde de Entrega (arriba) y que se alcance con el pulgar.

## 8. Revisión a mano: hoja de carga en el celular

Las pruebas automáticas revisan columnas, colores, botones y marcas, pero **no** dibujan la lista.
Las pruebas de pantalla (`tests/pantalla/correr.mjs`) no abren el backend, y las de navegador de
Odoo necesitan Chrome **dentro** del contenedor, que no lo tiene. Por eso esto se revisa a mano:

1. Con el usuario del papá (o uno de gerente de Ventas), abrir en el celular Ventas › Órdenes ›
   Hoja de carga. Abre agrupada por zona, con las zonas **abiertas**.
2. Columnas Producto (en 2 o 3 líneas si hace falta), Cantidad ("4 pz", "2,5 kg") y Aviso
   completo, y el cuadro de marcar: todo se ve **sin deslizar a los lados** (medido: 393 de 393
   px; a 360 px solo queda fuera el engrane del encabezado de zona).
3. Tocar el **cuadro vacío ☐** de un producto: queda en verde con "Acomodado" y el cuadro
   **palomeado ☑**; tocarlo otra vez quita la marca. Que el cuadro (44 × 44 px) se pueda tocar
   con el dedo sin atinarle al renglón de al lado.
4. Con un pedido nuevo de ese producto en la misma zona (desde la app), **sin recargar**: en
   menos de 30 segundos sale en naranja, "Se agregó 1", y las zonas siguen abiertas; tocar otra
   vez el cuadro: verde. En otra zona, el aviso no cambia.
5. Sin señal un rato: la hoja no muestra avisos de error; al volver la señal se actualiza sola.
6. Al sol: que se distingan el verde, el naranja y el azul.

## 9. Verificar una pantalla del backend en 8071 con una sesión temporal (SOLO PARA DESARROLLO)

> **Solo duranDEV.** Este procedimiento **nunca** se usa en duranPROD ni en el servidor de
> Oracle. Crea una sesión del administrador sin contraseña: en producción sería un riesgo.

Sirve para que, después de actualizar un módulo y reiniciar Odoo (sección 1), se pueda abrir una
pantalla del backend en `http://localhost:8071` con el Chrome de la Mac, sin escribir ni leer
ninguna contraseña.

1. **Crear la sesión** con `odoo shell` (no escribe en la base; solo crea un archivo de sesión
   de Odoo, igual que el login en `odoo/http.py`, `Session.finalize`):

   ```python
   from odoo import http
   assert env.cr.dbname == "duranDEV"
   store = http.root.session_store
   admin = env.ref("base.user_admin")
   sesion = store.new()
   sesion.update(http.get_default_session(), db=env.cr.dbname)
   sesion.update({"login": admin.login, "uid": admin.id, "context": dict(admin.context_get()),
                  "session_token": admin._compute_session_token(sesion.sid)})
   store.save(sesion)
   ```

   El identificador (`sesion.sid`) funciona como una contraseña mientras exista: guardarlo en un
   archivo temporal fuera del repositorio, **sin mostrarlo** ni subirlo a git.
2. **Abrir la pantalla** con Chrome sin ventana, controlado por DevTools: poner la cookie
   `session_id` con ese identificador y ajustar el tamaño con `Emulation.setDeviceMetricsOverride`
   (1366 x 768 para computadora y 393 x 852 para celular; así sí se dibuja a 393 px). Revisar que
   no haya errores de consola ni ventana de error, que se vean las filas y que ni la página ni la
   lista se deslicen a los lados.
3. **Borrar la sesión** al terminar, en `odoo shell`:
   `store.delete(store.get(sid))`, y comprobar que el archivo de
   `store.get_session_filename(sid)` ya no existe y que la misma cookie manda al login. Borrar
   también el archivo temporal con el identificador.

## 10. Revisión a mano: pendiente de cobro

1. Con el usuario del papá (o gerente), abrir Ventas › Órdenes › Pendiente de cobro: abre
   agrupado por **Zona › Cliente**, con lo entregado hoy y el saldo anterior de cada cliente.
   Aparecen también los clientes con deuda que hoy no tuvieron entrega.
2. Abrir un cliente: renglones de "Entregado hoy" (Pedido, Producto, Cantidad, Peso del rollo
   solo en rollos, Pendiente de hoy) y de saldo (factura, saldo a favor en negativo o entrega
   anterior, con su Fecha del saldo y Días de antigüedad).
3. El encabezado del cliente muestra el **máximo** de Días de antigüedad; los saldos de más de
   7 días se ven en **rojo**.
4. Filtro **Solo con saldo anterior**: quedan solo los renglones de saldo.
5. Comparar el **Total a cobrar** de un cliente con la pantalla de Cobro de la app: debe ser el
   mismo (si su saldo a favor es mayor, la app muestra $0 y aquí sale en negativo).
6. Con el usuario de la mamá (solo Captura): el menú no aparece.

## 11. Pendientes conocidos

- **Hoja de carga:** resuelto. La acción tiene `group_ids` de gerente y, como `group_ids` en una
  acción no impide abrirla por su dirección (Odoo la carga con sudo sin revisar grupos,
  `web/controllers/action.py:41-44`), lo que protege el dato es el acceso a los modelos
  `duran.hoja.carga` y `duran.hoja.carga.marca`: solo gerente de Ventas.