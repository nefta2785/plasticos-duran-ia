# Plásticos Durán — Sistema de Gestión Asistido por IA

Herramienta interna para levantar los pedidos que llegan por WhatsApp usando IA
(transcripción de audios con Whisper y extracción de datos con un LLM) y volcarlos
a Odoo Community. Es de uso exclusivo del negocio familiar Plásticos Durán (venta de
productos de plástico); no se distribuye ni se comercializa.

## Estructura del repositorio

- **`custom-addons/`** — Módulos custom de Odoo Community 19 (Python + XML) hechos a medida para el negocio.
- **`ai-pipeline/`** — Scripts en Python del pipeline de IA: transcripción de audio (Whisper), extracción de pedidos con LLM y fuzzy matching de productos (rapidfuzz).
- **`docs/`** — Documentación del proyecto: decisiones de diseño, guías de operación y notas técnicas.
- **`docker/`** — Configuración de Docker para levantar Odoo Community en local.
