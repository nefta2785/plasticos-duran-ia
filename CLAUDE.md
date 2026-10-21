# CLAUDE.md — Plásticos Durán

## Qué es
Sistema de gestión del negocio familiar Plásticos Durán (venta de productos de plástico en tianguis):
Odoo 19 Community autohospedado con dos módulos custom. Usuarios finales: los papás de la familia (53–55 años),
desde celular Android con Chrome (página `/captura`) y desde laptop (backend de Odoo).

## Entornos
- **duranDEV**: desarrollo y capacitación. Docker local en la Mac (`docker/docker-compose.yml`):
  imagen `odoo:19.0`, `postgres:15`. Odoo en http://localhost:8071 (→8069), Postgres en localhost:5433 (→5432).
- **duranPROD**: producción en VM de Oracle Cloud (Ubuntu 22.04, ARM64), `docker/prod/` con
  Odoo, PostgreSQL y nginx (80/443) fijados por digest. **No se toca desde aquí** (ver Prohibido).

Levantar duranDEV (todo desde `docker/`):
```bash
cd docker
cp .env.example .env        # solo la primera vez; rellenar POSTGRES_USER y POSTGRES_PASSWORD
docker compose up -d
```
Actualizar módulo, reiniciar y probar (detalle en `docs/pruebas-captura.md`), desde `docker/`:
```bash
# Actualizar (cambió XML, manifest o campos). Cambiar -u según el módulo tocado.
docker compose exec -T odoo sh -c 'odoo -d duranDEV --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" -u duran_captura_tianguis --stop-after-init --no-http'
# Reiniciar (siempre después de actualizar o de cambiar Python)
docker compose restart odoo
# Pruebas de Odoo de los dos módulos
docker compose exec -T odoo sh -c 'odoo -d duranDEV --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" --test-enable --test-tags /duran_captura_tianguis,/duran_peso_variable --stop-after-init --http-port 8070 --max-cron-threads 0'
```
Pruebas de pantalla de `/captura` (Chrome headless, sin Odoo), desde la raíz del repo:
`node custom-addons/duran_captura_tianguis/tests/pantalla/correr.mjs` (opción `--detalle`).
Después de actualizar un módulo: reiniciar Odoo y abrir la pantalla afectada en http://localhost:8071.

## Estructura
- `custom-addons/duran_peso_variable/` — productos que se facturan por peso real: `precio_por_kg`
  en el producto, una línea por rollo, peso real en movimientos y factura; asistente de cambio de producto.
  Depende de: `product`, `stock`, `sale_stock`, `account`.
- `custom-addons/duran_captura_tianguis/` — página `/captura` para celular (PWA) para levantar pedidos
  por zona, Entrega (peso por rollo) y Cobro en efectivo; bitácoras de entregas y cobros, Hoja de carga
  y Pendiente de cobro en el backend. Depende de: `sale_stock`, `duran_peso_variable`.
- `docker/` — compose de DEV; `docker/prod/` — compose, nginx, scripts de respaldo/restauración de PROD.
- `docs/` — setup inicial, configuración y despliegue de producción, guía de operación, pruebas.
- `ai-pipeline/` — carpeta vacía y no versionada; nada la usa. Legado, no desarrollar ahí.

## Reglas del negocio (el código debe respetarlas)
- Sin impuestos: precios netos, 0%. Ningún impuesto de venta por defecto ni en productos.
- Cantidades siempre enteras (mayores a cero).
- Tope de 15 kg por rollo (parámetro `duran_captura_tianguis.peso_bloqueo_max`, valor inicial 15).
- Peso variable: precio por kg en `precio_por_kg`, peso real por rollo, cada rollo es una línea de factura.
- Se factura al cobrar y solo en efectivo (un único diario de tipo Efectivo).
- No se usa la app de Punto de Venta.
- Zonas = etiquetas de contacto (Bosques, Guadalupana, Entrada Heroes, Kinder, Locatarios). No se
  modifican. (Zonas confirmadas por Nefta; el repo solo contiene datos de prueba.)

## Reglas de UI
- Todo debe ser muy intuitivo para personas de 53–55 años en Android con Chrome. Preferir lo más simple.
- No construir mejoras pospuestas: guardado local sin señal, nota libre, cantidades grandes
  por mantener presionado, clientes recientes.

## Reglas de trabajo
- Una tarea por vez. Si hay duda, diagnóstico (solo lectura) antes de implementar.
- No tocar archivos fuera del alcance pedido; si algo extra parece necesario, preguntar primero.
- Probar en duranDEV (pruebas de Odoo + pruebas de pantalla si aplica) antes de proponer commit.
- Al terminar, reportar qué archivos cambiaron y cómo probarlo.
- No hacer commit ni push; Nefta revisa primero y pide el commit.

## Prohibido
- Tocar duranPROD (VM, base, contenedores).
- Borrar o migrar datos de duranPROD. En duranDEV solo si la tarea lo pide expresamente.
- Poner contraseñas, claves, `.env`, `odoo.conf` o datos reales de clientes en el repo.
- Usar IA o WhatsApp para la captura de pedidos (descartado; `ai-pipeline/` es legado).
- El repo es público: nada sensible en archivos ni en el historial de commits (contraseñas, claves, IPs de servidores, datos reales de clientes). Si una tarea parece requerirlo, detenerte y preguntar.

## Mantenimiento
- Si cambia una decisión de negocio o técnica, proponer actualizar este archivo.
