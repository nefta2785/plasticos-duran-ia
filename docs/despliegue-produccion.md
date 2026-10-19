# Desplegar cambios del repo en duranPROD

Cómo llevar a **duranPROD** (la VM de Oracle) lo que ya está en `origin/main`, sin perder datos y
con forma de regresar si algo sale mal. La instalación inicial está en
[guia-despliegue.md](guia-despliegue.md); este documento es solo para **actualizar**.

> **Cómo leer este documento.** Igual que la guía de despliegue:
> - **Dónde:** **Mac**, **VM** (después de entrar por SSH) o **Navegador**.
> - El **comando** exacto. Lo que va entre `<ángulos>` lo cambias tú.
> - **Fuente:** de dónde sale el comando (un archivo del repo o documentación oficial). Lo que no
>   está comprobado dice **SUPUESTO**.
> - **Salió bien si…** y **Si no…**: qué hacer cuando el resultado no es el esperado.
>
> **Nunca** pegues el contenido de `.env` ni de `odoo.conf` en un chat, un issue o un commit.

**Orden obligatorio:** respaldo → detener Odoo → traer el código → actualizar los módulos →
encender → verificar. No te saltes ni cambies el orden.

**Cuándo:** cuando nadie use la app (nunca en día de tianguis) y lejos de las 03:30, que es la hora
del respaldo automático ([guia-despliegue.md §13.3](guia-despliegue.md#133-programarlo-con-cron)).
Durante los pasos 3 a 5, Odoo está apagado y la página no abre.

**`sudo` en todo `docker compose`:** en la VM, el usuario `ubuntu` no está en el grupo `docker`
(decisión tomada; ver [guia-despliegue.md §13.2](guia-despliegue.md#132-primer-respaldo-a-mano)).
Sin `sudo`, Docker responde *permission denied*.

---

## Primer uso (ejemplo)

El primer despliegue con este documento fue:

| | Commit |
|---|---|
| `<COMMIT_ANTERIOR>` (lo que tenía la VM) | `eff9777` |
| `<COMMIT_NUEVO>` (`origin/main`) | `4c8d22f` |

Qué llevó:
- `duran_captura_tianguis`: Hoja de carga con pie "Productos totales: N" y un botón con texto por
  renglón (Acomodar / Por acomodar / Acomodado). Trae un campo nuevo (`productos_totales`) y
  archivos JS/CSS nuevos: **necesita actualizar el módulo**, no basta con reiniciar.
- `duran_peso_variable`: la regla de "máximo 1 rollo por movimiento" solo aplica a entregas al
  cliente (los ajustes de inventario, transferencias internas y devoluciones a proveedor ya pueden
  llevar varios rollos). Compras (`purchase`) no está instalado en duranPROD: las compras podrán
  llevar varios rollos cuando se instale.

En los siguientes despliegues, cambia los dos commits por los que correspondan.

---

## 0. Antes de empezar

**Dónde:** Mac, en la carpeta del proyecto.

```
git status
git fetch origin
git log --oneline -1 origin/main
```

**Fuente:** comandos estándar de git (solo leen).

**Salió bien si:** `git status` no muestra cambios pendientes y el último commit de `origin/main`
es el que quieres desplegar. Anótalo: es tu `<COMMIT_NUEVO>`.

**También:** las pruebas de los dos módulos pasan en duranDEV
([pruebas-captura.md §4](pruebas-captura.md#4-antes-de-cada-commit-las-dos-pruebas)).

**Si no:** no despliegues. Primero sube lo que falte o arregla las pruebas.

---

## 1. Revisar la VM (solo mira, no cambia nada)

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia
git status --short
git rev-parse --short HEAD
cd docker/prod
sudo docker compose ps
df -h /
```

**Fuente:** git; `docker compose ps` de [guia-despliegue.md §15](guia-despliegue.md#15-operación-del-día-a-día);
`df -h /` de [guia-despliegue.md §16.10](guia-despliegue.md#1610-disco-lleno).

**Salió bien si:**
- `git status --short` no muestra nada (sin cambios locales en la VM).
- `git rev-parse` muestra un commit: **anótalo**, es tu `<COMMIT_ANTERIOR>` (lo necesitas para
  regresar).
- `docker compose ps`: `db`, `odoo` y `nginx` en `Up`, y `db` como `healthy`.
- `df -h /`: espacio libre de sobra para un respaldo más. **SUPUESTO:** más de 5 GB es un margen
  razonable; no está medido.

**Si no:** si hay cambios locales en la VM, **no sigas**: averigua primero de dónde vienen. Si un
servicio no está `Up`, revisa [guia-despliegue.md §16.5](guia-despliegue.md#165-502-bad-gateway-u-odoo-no-responde).

---

## 2. Respaldo, y comprobar que sirve

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
./scripts/respaldo.sh
```

**Fuente:** [docker/prod/scripts/respaldo.sh](../docker/prod/scripts/respaldo.sh). Hace `pg_dump`
de duranPROD y copia el filestore; por dentro ya usa `sudo -n docker compose` (líneas 35-39), y
comprueba que los archivos no estén vacíos, que el dump tenga la firma `PGDMP` y que el `.tar.gz`
no esté dañado (líneas 55-66).

**Salió bien si:** la última línea dice `Respaldo listo: /var/backups/duran/<FECHA> (…)`.
Anota `<FECHA>` (por ejemplo `20261019-140500`).

**Comprobación extra:** leer el índice del respaldo, sin restaurar nada:

```
sudo docker compose exec -T db pg_restore --list < /var/backups/duran/<FECHA>/duranPROD.dump | head
```

**Fuente:** `pg_restore --help` de PostgreSQL 15.19, la misma imagen que fija
`docker/prod/docker-compose.yml`: `-l, --list` imprime el índice del archivo, y sin nombre de
archivo lee de la entrada estándar. Probado el 19-oct-2026 con un dump de duranDEV.

**Salió bien si:** muestra líneas como `; Archive created at …`, `;     dbname: duranPROD` y
`;     TOC Entries: …` (un número grande).

**Si no:** **no sigas.** Sin un respaldo bueno no se toca producción. Si `respaldo.sh` dice
`sudo: a password is required`, ver [guia-despliegue.md §13.2](guia-despliegue.md#132-primer-respaldo-a-mano).

**Después (recomendado):** llévate el respaldo a la Mac
([guia-despliegue.md §13.4](guia-despliegue.md#134-copiarlos-a-la-mac)). La prueba completa de
que el respaldo se puede restaurar es el ensayo en la Mac
([guia-despliegue.md §14](guia-despliegue.md#14-restauración-probada-ensayo-en-la-mac)).

---

## 3. Detener Odoo y traer el código nuevo

**Dónde:** VM

```
cd /home/ubuntu/plasticos-duran-ia/docker/prod
sudo docker compose stop odoo
git -C /home/ubuntu/plasticos-duran-ia pull --ff-only
git -C /home/ubuntu/plasticos-duran-ia log --oneline -1
```

**Fuente:** `docker compose stop odoo` de [guia-despliegue.md §15](guia-despliegue.md#actualizar-tras-un-cambio-en-el-repo-sin-perder-datos);
`git pull --ff-only` de la documentación de git ("abort if fast-forward is not possible").

**Por qué en este orden:** primero se apaga Odoo para que nadie use la app mientras el código
nuevo convive con la base vieja. `--ff-only` solo avanza si la VM no tiene commits propios; si los
tuviera, se detiene en lugar de mezclar.

**Salió bien si:** el `log` muestra `<COMMIT_NUEVO>`.

**Si no:**
- Si `git pull` se detiene (*Not possible to fast-forward*) o pide usuario y contraseña: no
  improvises. Vuelve a encender Odoo con `sudo docker compose up -d` (queda como estaba, con el
  código anterior) y revisa el problema con calma.

---

## 4. Actualizar los módulos

**Dónde:** VM

```
sudo docker compose run --rm odoo odoo -d duranPROD -u duran_peso_variable,duran_captura_tianguis --stop-after-init --no-http
```

**Fuente:** [guia-despliegue.md §15](guia-despliegue.md#actualizar-tras-un-cambio-en-el-repo-sin-perder-datos).
Opciones verificadas en la documentación oficial de la CLI de Odoo 19
(https://www.odoo.com/documentation/19.0/developer/reference/cli.html) y en `odoo server --help`
de la imagen fijada. El `entrypoint.sh` de la imagen agrega los datos de conexión a PostgreSQL
desde las variables del contenedor (no hay que escribirlos).

**Qué hace:** en un contenedor temporal, aplica a duranPROD los cambios de los dos módulos
(campos, vistas, archivos de la Hoja de carga) y termina solo. `-u` **actualiza, no reinstala**:
los datos se conservan.

**Por qué no basta con reiniciar:** la vista de la Hoja de carga se vuelve a crear solo cuando el
módulo se actualiza (Odoo llama a `init()` de los modelos al instalar o actualizar:
`odoo/modules/loading.py`, líneas 189-194 de la imagen). Sin `-u`, la Hoja de carga falla.

**Salió bien si:** termina sin líneas `ERROR` ni `CRITICAL`. Al final aparece
`Initiating shutdown`: es normal, es el contenedor temporal cerrándose.

**Si no:** copia las líneas de `ERROR` (sin contraseñas) y ve a la [sección 7](#7-si-algo-falla-regresar).
No enciendas Odoo con un `-u` que falló.

---

## 5. Encender

**Dónde:** VM

```
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail 100 odoo
```

**Fuente:** [guia-despliegue.md §15](guia-despliegue.md#15-operación-del-día-a-día).

**Salió bien si:** los tres servicios en `Up` (`db` como `healthy`) y en los logs no hay `ERROR`
ni `CRITICAL` recientes.

**Si no:** [guia-despliegue.md §16.5](guia-despliegue.md#165-502-bad-gateway-u-odoo-no-responde).
Si no se arregla, [sección 7](#7-si-algo-falla-regresar).

---

## 6. Verificar

### 6.1 Desde la Mac

Repite [guia-despliegue.md §11.1](guia-despliegue.md#111-el-service-worker-de-captura-llega-con-su-encabezado-a-través-de-nginx)
(service worker de `/captura`) y [§11.3](guia-despliegue.md#113-websocket-puerto-8072-de-odoo-vía-nginx)
(websocket).

**Salió bien si:** dan lo que dice la guía en cada paso.

### 6.2 Que el campo nuevo llegó a la base (primer uso)

**Dónde:** VM, en `docker/prod`

```
sudo docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d duranPROD -Atc "select count(*) from ir_model_fields where model='"'"'duran.hoja.carga'"'"' and name='"'"'productos_totales'"'"'"'
```

**Fuente:** consulta de solo lectura; probada en duranDEV el 19-oct-2026 (da `1`).

**Salió bien si:** muestra `1` (antes del despliegue daba `0`). Para otros despliegues, este
paso no aplica o se cambia por el campo que corresponda.

### 6.3 En el navegador (como administrador o gerente de Ventas)

Antes, recarga la página **por completo** (Ctrl+Shift+R en la computadora; en el celular, cierra
la pestaña o la app y vuelve a abrirla). Si alguien tenía Odoo abierto durante el despliegue, que
haga lo mismo: **SUPUESTO**, una pestaña que se quedó con los archivos viejos puede mostrar
errores hasta recargar.

1. **Ventas › Órdenes › Hoja de carga** abre agrupada por zona, con las zonas abiertas.
2. Al pie dice **"Productos totales: N"**, y N es la suma de las cantidades de todos los renglones
   (kilos y piezas cuentan 1 cada uno).
3. Cada renglón tiene un botón: gris **Acomodar**, naranja **Por acomodar** o verde
   **Acomodado**. En los verdes, la columna Aviso va vacía.
4. Toca **Acomodar** en un renglón: se pone verde. Toca **Acomodado**: se quita la marca. Son
   marcas reales del día, así que deja el renglón como estaba (o hazlo con uno que de verdad ya
   esté acomodado).
5. Abren las otras vistas de **Ventas › Órdenes**: Pendiente de cobro, Entregas y Resumen.

**En el celular:** la Hoja de carga se ve sin deslizar a los lados
([pruebas-captura.md §8](pruebas-captura.md#8-revisión-a-mano-hoja-de-carga-en-el-celular)), y
`/captura` abre en la app (ciérrala y vuelve a abrirla) y llega a Inicio.

**Salió bien si:** todo lo anterior se cumple.

**Si no:** anota qué falló (y una captura de pantalla). Si la app no se puede usar, ve a la
[sección 7](#7-si-algo-falla-regresar).

---

## 7. Si algo falla: regresar

### 7.1 Regresar el código (la opción normal)

Si el despliegue no cambió datos (como el primer uso: no hubo migraciones ni datos
transformados), basta con regresar el código y volver a actualizar los módulos.

**Dónde:** VM, en `docker/prod`

```
sudo docker compose stop odoo
git -C /home/ubuntu/plasticos-duran-ia checkout <COMMIT_ANTERIOR>
sudo docker compose run --rm odoo odoo -d duranPROD -u duran_peso_variable,duran_captura_tianguis --stop-after-init --no-http
sudo docker compose up -d
```

**Fuente:** los mismos comandos de los pasos 3 a 5; `git checkout <commit>` de la documentación de
git. `<COMMIT_ANTERIOR>` es el que anotaste en el paso 1.

**Qué hace:** deja la VM con el código anterior y vuelve a aplicar sus vistas. La vista de la Hoja
de carga se vuelve a crear como era (`init()`, `odoo/modules/loading.py` líneas 189-194).
**SUPUESTO:** que Odoo borre de su lista de campos el que ya no existe en el código; si no lo
borra, no afecta.

**Salió bien si:** igual que los pasos 4 a 6, con la pantalla como estaba antes.

**Importante:** después de esto la VM queda "fuera de la rama" (*detached HEAD*). Cuando el
arreglo esté listo en `main`, antes de volver a desplegar:
`git -C /home/ubuntu/plasticos-duran-ia checkout main` y sigue desde el paso 3.

### 7.2 Regresar la base al respaldo (solo si se dañaron datos)

**SUPUESTO, sin procedimiento probado.** `restaurar.sh` se niega a restaurar sobre una duranPROD
que ya existe ([docker/prod/scripts/restaurar.sh](../docker/prod/scripts/restaurar.sh), líneas
45-49), y la restauración real en producción no se ha ensayado
([guia-despliegue.md §14.8](guia-despliegue.md#148-restaurar-de-verdad-en-producción-desastre)).
No lo improvises: decídelo aparte y con calma, con el respaldo del paso 2 a salvo en la Mac.

---

## Cosas que NO viajan con git

`git pull` solo trae **código y archivos del repo**. Lo que se configuró en la **interfaz** de
duranDEV (con clics, en Ajustes o en Aplicaciones) vive en la base de duranDEV y **no** llega a
duranPROD. Por ejemplo:

- **Instalar un módulo estándar de Odoo**, como **Compras** (`purchase`). Hoy está instalado en
  duranDEV y **no** en duranPROD.
- **El método de costeo de una categoría de producto** (Inventario › Configuración › Categorías
  de productos).
- Los ajustes de [configuracion-produccion.md](configuracion-produccion.md).

Esto se repite **a mano** en duranPROD, **después** del despliegue y **como paso aparte** (no en
medio de los pasos 1 a 6), anotando qué se cambió y cuándo. Si no estás seguro de qué se cambió
en duranDEV, revísalo antes; el repo no lo puede saber.

---

## Fuentes

- [guia-despliegue.md](guia-despliegue.md): §11 (comprobaciones), §13 (respaldos), §14
  (restauración), §15 (operación), §16 (si algo falla).
- [docker/prod/scripts/respaldo.sh](../docker/prod/scripts/respaldo.sh) y
  [docker/prod/scripts/restaurar.sh](../docker/prod/scripts/restaurar.sh).
- [docker/prod/docker-compose.yml](../docker/prod/docker-compose.yml): imágenes fijadas por digest
  (Odoo 19.0-20260908, PostgreSQL 15.19).
- Odoo 19, Command-line interface (`-d`, `-u`, `--stop-after-init`, `--no-http`) —
  https://www.odoo.com/documentation/19.0/developer/reference/cli.html
- Imagen de Odoo fijada: `/entrypoint.sh` (datos de conexión) y `odoo/modules/loading.py`
  (cuándo se ejecuta `init()` de los modelos).
- PostgreSQL 15.19, `pg_restore --help` (`--list` y lectura de la entrada estándar).
- git: `git pull --ff-only`, `git checkout`.
