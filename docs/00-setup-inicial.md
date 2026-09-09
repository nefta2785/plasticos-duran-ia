# Setup Inicial — Plásticos Durán IA

**Fecha:** Septiembre 2026
**Objetivo de esta sesión:** dejar el proyecto arrancado con repositorio en GitHub, entorno de desarrollo aislado, y Odoo Community 19 corriendo localmente con su primera base de datos.

---

## 1. Decisiones de arquitectura tomadas

| Decisión | Elegido | Por qué |
|---|---|---|
| Instalación de Odoo | Completamente independiente de la del proyecto de la academia (otro Odoo, otra carpeta) | Evita mezclar código, bases de datos o configuración entre los dos negocios/proyectos |
| Método de instalación | Docker (Docker Desktop) | Empaqueta Python, PostgreSQL y Odoo dentro de un contenedor aislado — no toca el Python ni las librerías instaladas directo en la Mac, y se puede borrar sin dejar rastro. El proyecto de la academia corre nativo (sin Docker), así que además evita cualquier choque de versiones entre ambos proyectos |
| Puerto de Odoo | **8071** (host) → 8069 (contenedor) | Los puertos 8069 y 8070 ya estaban ocupados en la Mac por el proyecto de la academia (`gym_dev`/`gym_prod`), confirmado con `lsof` antes de asumirlo |
| Puerto de Postgres | **5433** (host) → 5432 (contenedor) | Mismo motivo — se verificó con `lsof` que estaba libre antes de usarlo |
| Nomenclatura de bases de datos | `duranDEV` / `duranPROD` (camelCase) | Decisión explícita del usuario — distinta al patrón `gym_dev`/`gym_prod` de la academia (snake_case), pero se mantiene así por ser la que ya se usó al crear la primera base |
| Manejo de credenciales | Archivo `.env` real (nunca se sube a git) + `.env.example` como plantilla (sí se sube, sin valores reales) | Evita que contraseñas terminen en el historial de GitHub. `.env` está declarado en `.gitignore` |
| Estructura de carpetas | `custom-addons/`, `ai-pipeline/`, `docs/`, `docker/` | Separa claramente: código de Odoo, scripts del pipeline de IA, documentación, y configuración de infraestructura |
| Construcción de archivos de configuración | Vía prompts scoped a Claude Code, no escritos a mano en el chat | El usuario está aprendiendo a programar — se usa Claude Code como el "constructor" real, revisando cada propuesta antes de aceptarla |

---

## 2. Paso a paso de lo realizado

### 2.1 Diagnóstico de entorno
Se corrieron en Terminal:
```
docker --version   → no instalado (se resolvió en el paso 2.2)
git --version      → 2.50.1 (ya disponible)
python3 --version  → no encontrado en el PATH del sistema (sin problema: con Docker, Python vive dentro del contenedor, no hace falta en la Mac)
```

### 2.2 Instalación de Docker Desktop
- Se descargó la versión para Apple Silicon (Mac M1) desde docker.com.
- Se instaló y se confirmó con `docker --version` → `Docker version 29.7.2`.

### 2.3 Repositorio en GitHub
- Se creó `plasticos-duran-ia` en GitHub, **privado**, vacío (sin README/.gitignore/licencia automáticos, para tener control total del contenido inicial desde la Mac).
- URL: `https://github.com/nefta2785/plasticos-duran-ia`

### 2.4 Clonado local y estructura
```
cd ~/Documents
git clone https://github.com/nefta2785/plasticos-duran-ia.git
cd plasticos-duran-ia
mkdir custom-addons ai-pipeline docs docker
```
El proyecto vive en `~/Documents/plasticos-duran-ia`.

### 2.5 Scaffolding inicial (`.gitignore` + `README.md`)
Se le dio a Claude Code un prompt scoped para crear:
- `.gitignore`: ignora artefactos de Python (`__pycache__`, `.pyc`, entornos virtuales), archivos de macOS (`.DS_Store`), variables de entorno (`.env`), y archivos típicos de una instancia local de Odoo (filestore, sesiones, logs).
- `README.md`: nombre del proyecto, propósito, y descripción de las 4 carpetas.

Commit: `"Estructura inicial del proyecto"` → subido a GitHub.

### 2.6 Configuración de Docker para Odoo
Se le dio a Claude Code un segundo prompt scoped, pidiéndole explícitamente **verificar en Docker Hub** (no asumir) la versión de imagen correcta para Odoo Community 19 y una versión de Postgres compatible. Se generaron dentro de `docker/`:

- **`docker-compose.yml`** con dos servicios:
  - `db`: PostgreSQL, con volumen nombrado para persistir los datos, puerto `5433→5432`.
  - `odoo`: imagen oficial de Odoo, dependiente de `db`, con:
    - Bind mount de `../custom-addons` → `/mnt/extra-addons` dentro del contenedor (para que los módulos custom que se desarrollen en la Mac sean visibles para Odoo).
    - Volumen nombrado para `/var/lib/odoo` (así el filestore sobrevive a reinicios del contenedor y nunca se sube a git).
    - Puerto `8071→8069`.

  *(Las versiones exactas de las imágenes usadas quedan documentadas dentro del propio `docker-compose.yml` — revisar ahí como fuente de verdad en vez de este documento, por si se actualizan más adelante.)*

- **`.env.example`**: plantilla con las variables `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` sin valores reales.
- Se confirmó que `.gitignore` ya cubría `.env`.

Commit: `"Configuración de Docker para Odoo Community aislado"` → subido a GitHub.

**Investigado (no es un problema):** el log de Odoo mostró un warning: `invalid addons directory '/mnt/extra-addons', skipped`. Se diagnosticó paso a paso (se descartaron permisos con `docker compose exec odoo ls -la /mnt/extra-addons`, que salió correcto) hasta confirmar, con la documentación oficial de Odoo, que este warning es el comportamiento esperado cuando la carpeta de addons está **vacía** — Odoo la descarta hasta que contenga al menos un módulo. Se resolverá solo en cuanto se coloque el primer módulo custom en `custom-addons/`.

### 2.7 Archivo `.env` real
```
cd docker
cp .env.example .env
```
Se rellenaron `POSTGRES_USER` y `POSTGRES_PASSWORD` con valores reales elegidos por el usuario (nunca compartidos con el asistente). Confirmado con `git check-ignore docker/.env` que el archivo está correctamente ignorado por git.

> Nota de proceso: el primer intento de editar `.env` con TextEdit y luego con `nano` falló (los valores no se guardaron por errores de navegación/atajos). Se resolvió usando `sed -i ''` para insertar los valores directo desde la línea de comandos, sin depender de un editor interactivo.

### 2.8 Levantar Odoo por primera vez
```
cd docker
docker compose up -d
docker compose ps       # confirmar servicios "Up"
docker compose logs odoo
```
Confirmado: `HTTP service (werkzeug) running on 0.0.0.0:8069` dentro del contenedor, accesible en la Mac vía `http://localhost:8071`.

### 2.9 Creación de la primera base de datos
En `http://localhost:8071/web/database/selector`:

- **Master Password**: generada automáticamente por Odoo — controla el gestor de bases de datos (crear/borrar/respaldar), no es la contraseña de ningún usuario. Guardada por el usuario fuera del repositorio (no documentada aquí por seguridad).
- **Database Name**: `duranDEV`
- **Email / Password**: credenciales del usuario administrador — no documentadas aquí, viven solo en el gestor de contraseñas del usuario.
- **Language**: Spanish (MX)
- **Country**: Mexico
- **Demo Data**: sin marcar (base limpia, sin datos de ejemplo, porque este proyecto eventualmente maneja datos reales del negocio)

**Troubleshooting durante este paso:** el primer intento (con el nombre `duran_dev`, presumiblemente con un carácter extra colado al escribirlo) arrojó:
```
Database creation error: 'NoneType' object has no attribute 'uid'
```
Se revisaron los logs del contenedor (`docker compose logs --tail=100 odoo`) y se encontró que este era un error *secundario*: un bug en el sistema de traducción de mensajes de Odoo 19 rompió al intentar mostrar el mensaje de error real, que era:
> "Houston, we have a database naming issue! Make sure you only use letters, numbers, underscores, hyphens, or dots in the database name."

Se corrigió reescribiendo el nombre desde cero (`duranDEV`), sin espacios ni caracteres inválidos, y la base se creó correctamente.

---

## 3. Arquitectura resultante

```
Mac (Apple Silicon M1)
│
├── ~/Documents/plasticos-duran-ia/   ← repo git, conectado a GitHub (privado)
│   ├── custom-addons/                ← (vacío) módulos custom de Odoo — montado dentro del contenedor
│   ├── ai-pipeline/                  ← (vacío) scripts del pipeline de IA (fase siguiente)
│   ├── docs/                         ← documentación (este archivo)
│   ├── docker/
│   │   ├── docker-compose.yml        ← versionado en git
│   │   ├── .env.example              ← versionado en git (plantilla, sin secretos)
│   │   └── .env                      ← NO versionado (credenciales reales)
│   ├── .gitignore
│   └── README.md
│
└── Docker Desktop
    └── docker-compose (proyecto "docker")
        ├── contenedor "db"    (Postgres)   — puerto Mac 5433 → 5432
        └── contenedor "odoo"  (Odoo 19)    — puerto Mac 8071 → 8069
                                              → base de datos activa: duranDEV
```

---

## 4. Pendientes conocidos

- [ ] Documentar (fuera de este repo, en un lugar seguro del usuario) la Master Password del gestor de bases de datos.
- [ ] Definir cuándo se crea `duranPROD` (base de producción) — no se ha creado todavía, solo `duranDEV`.

## 5. Siguiente paso sugerido

Iniciar el diseño de la **Fase 1: Levantamiento de pedidos** — el pipeline de IA (transcripción + extracción + fuzzy matching) y el módulo custom de Odoo que crea el pedido borrador.
