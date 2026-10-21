# Plásticos Durán — Sistema de gestión

Sistema de gestión de Plásticos Durán, negocio familiar de venta de productos de plástico.
Corre sobre **Odoo 19 Community** con dos módulos custom hechos a medida. Es de uso interno
del negocio: no se distribuye ni tiene fin comercial.

## Entornos

- **duranDEV** — Odoo en Docker local, para desarrollo y capacitación.
- **duranPROD** — producción, en una VM de Oracle Cloud con Docker (Odoo, PostgreSQL y nginx).

## Estructura del repositorio

- **`custom-addons/`** — módulos custom de Odoo (Python + XML):
  - `duran_peso_variable` — productos que se facturan por su peso real, con precio por kg.
  - `duran_captura_tianguis` — página para celular (`/captura`) para levantar pedidos por zona,
    entregar y cobrar en el tianguis, más sus bitácoras y reportes en Odoo.
- **`docker/`** — Docker Compose de duranDEV (Odoo 19 y PostgreSQL 15).
- **`docker/prod/`** — Docker Compose de duranPROD, configuración de nginx, renovación de
  certificados y scripts de respaldo y restauración.
- **`docs/`** — documentación de instalación, producción, operación y pruebas.

## Dónde está cada cosa

- [CLAUDE.md](CLAUDE.md) — reglas del negocio, reglas de trabajo y comandos de desarrollo.
- [docs/00-setup-inicial.md](docs/00-setup-inicial.md) — cómo se armó el entorno local.
- [docs/guia-despliegue.md](docs/guia-despliegue.md) — instalación inicial de duranPROD en la VM.
- [docs/despliegue-produccion.md](docs/despliegue-produccion.md) — cómo llevar cambios del repo a duranPROD.
- [docs/configuracion-produccion.md](docs/configuracion-produccion.md) — ajustes de Odoo que necesita la captura.
- [docs/guia-operacion.md](docs/guia-operacion.md) — guía para el día a día de los cobros en el tianguis.
- [docs/pruebas-captura.md](docs/pruebas-captura.md) — cómo actualizar los módulos y correr sus pruebas.

## Nota

La captura de pedidos con IA/WhatsApp se evaluó y se descartó.
