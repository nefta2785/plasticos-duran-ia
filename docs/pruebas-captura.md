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
  terminar: duranDEV queda igual que antes. Las órdenes de prueba usan nombre fijo para no
  consumir folios reales de la numeración de órdenes.
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
