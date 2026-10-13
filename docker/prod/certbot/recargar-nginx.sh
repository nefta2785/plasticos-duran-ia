#!/bin/sh
# deploy-hook de Certbot: cada vez que se emite o renueva el certificado,
# nginx (en su contenedor) vuelve a leerlo sin cortar conexiones.
#
# Certbot lo corre como root en el host; se registra con
#   certbot certonly ... --deploy-hook /ruta/absoluta/a/este/archivo
# y queda guardado para las renovaciones. Ver docs/guia-despliegue.md.
set -eu

DIR_PROD="$(cd "$(dirname "$0")/.." && pwd)"

docker compose --project-directory "$DIR_PROD" -f "$DIR_PROD/docker-compose.yml" \
    exec -T nginx nginx -s reload
echo "nginx recargado con el certificado de: ${RENEWED_LINEAGE:-(sin RENEWED_LINEAGE)}"
