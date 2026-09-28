# Pruebas del módulo `duran_captura_tianguis`

Comandos para actualizar el módulo y correr sus pruebas automatizadas en **duranDEV**.
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

Equivale a darle **Actualizar** al módulo en Aplicaciones. Lanza un segundo proceso de Odoo
dentro del mismo contenedor que aplica los XML y los campos nuevos a duranDEV y **termina solo**
(`--stop-after-init`). No abre ningún puerto (`--no-http`) ni detiene el servicio normal, que se
entera del cambio y se recarga por su cuenta.

Debe terminar sin líneas `ERROR`. Al final aparece `Initiating shutdown`: es normal, es el
proceso auxiliar cerrándose, no el Odoo de siempre.

---

## 2. Correr las pruebas automatizadas

```bash
docker compose exec -T odoo sh -c 'odoo -d duranDEV --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" --test-enable --test-tags /duran_captura_tianguis --stop-after-init --http-port 8070 --max-cron-threads 0'
```

Cuándo usarlo: **después de cualquier cambio al módulo** (y después de 1a/1b si aplican), y
antes de cada commit.

Qué hace:

- Lanza un segundo proceso de Odoo que corre solo las pruebas de este módulo (`--test-tags`).
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
docker compose exec -T odoo sh -c 'odoo -d duranDEV --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" --test-enable --test-tags /duran_captura_tianguis --stop-after-init --http-port 8070 --max-cron-threads 0' 2>&1 | grep -E "FAIL|ERROR|tests when loading"
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
- Recorre la pantalla como quien captura (`tests/pantalla/escenario.js`): zonas, zona vacía,
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
docker compose exec -T odoo sh -c 'odoo -d duranDEV --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" --test-enable --test-tags /duran_captura_tianguis --stop-after-init --http-port 8070 --max-cron-threads 0' 2>&1 | grep -E "FAIL|ERROR|tests when loading"
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

## 6. Qué NO cubren las pruebas automáticas

Hay que revisarlo a mano, en el celular:

- Que se lea bien al sol y que los botones se alcancen con una mano.
- El teclado, el zoom y el botón "atrás" físico de cada celular real.
- Una red real que se cae a la mitad del envío (las pruebas lo simulan).
- El inicio de sesión real y cuánto dura la sesión en el celular.
