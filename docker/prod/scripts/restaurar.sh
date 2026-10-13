#!/usr/bin/env bash
# Restaura un respaldo hecho por respaldo.sh en una base NUEVA.
#
# Uso:  restaurar.sh <carpeta-del-respaldo> <base-destino>
#
# - Nunca sobrescribe: si ya existe la base destino O su filestore
#   (/var/lib/odoo/filestore/<base-destino>), se detiene sin tocar nada.
#   Tampoco borra nada.
# - Nunca restaura sobre duranDEV. duranPROD sí se acepta, pero solo si NO
#   existe (restauración por desastre en un stack limpio; guía, paso 14.8).
# - Usa el docker compose de COMPOSE_DIR (por defecto docker/prod). Para el
#   ensayo en la Mac: COMPOSE_DIR=docker (el de desarrollo); ver la guía.
# - El filestore se copia a /var/lib/odoo/filestore/<base-destino>: Odoo lo
#   busca por el nombre de la base.
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Uso: $0 <carpeta-del-respaldo> <base-destino>" >&2
    echo "Restaura en una base NUEVA: si la base o su filestore ya existen, no sobrescribe nada y se detiene." >&2
    exit 2
fi
RESPALDO="$(cd "$1" && pwd)"
DESTINO="$2"
COMPOSE_DIR="$(cd "${COMPOSE_DIR:-$(dirname "$0")/..}" && pwd)"

if [ "$DESTINO" = "duranDEV" ]; then
    echo "ERROR: nunca se restaura sobre duranDEV." >&2
    exit 1
fi
if ! [[ "$DESTINO" =~ ^[A-Za-z][A-Za-z0-9_]*$ ]]; then
    echo "ERROR: nombre de base no válido: $DESTINO" >&2
    exit 1
fi
DUMP="$(find "$RESPALDO" -maxdepth 1 -name '*.dump' | head -n 1)"
FILESTORE="$RESPALDO/filestore.tar.gz"
if [ -z "$DUMP" ] || [ ! -s "$DUMP" ] || [ ! -s "$FILESTORE" ]; then
    echo "ERROR: en $RESPALDO falta el .dump o filestore.tar.gz" >&2
    exit 1
fi

compose() {
    docker compose --project-directory "$COMPOSE_DIR" -f "$COMPOSE_DIR/docker-compose.yml" "$@"
}

existe="$(compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '"'"'$1'"'"'"' _ "$DESTINO")"
if [ "$existe" = "1" ]; then
    echo "ERROR: la base $DESTINO ya existe; no se sobrescribe ni se toca. Elige otro nombre." >&2
    exit 1
fi
if compose exec -T odoo test -e "/var/lib/odoo/filestore/$DESTINO"; then
    echo "ERROR: ya existe el filestore de $DESTINO (/var/lib/odoo/filestore/$DESTINO); no se sobrescribe ni se toca. Elige otro nombre." >&2
    exit 1
fi

echo "Restaurando $DUMP en la base $DESTINO (compose: $COMPOSE_DIR)…"
compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" "$1"' _ "$DESTINO"
# --no-owner: los objetos quedan del usuario que restaura (en DEV puede ser otro).
compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --exit-on-error' _ "$DESTINO" < "$DUMP"

echo "Copiando el filestore a /var/lib/odoo/filestore/$DESTINO…"
# La carpeta de dentro del tar se llama como la base de origen: se renombra.
compose exec -T odoo sh -c 'mkdir -p /var/lib/odoo/filestore && tar -C /var/lib/odoo/filestore -xzf - --transform "s,^[^/]*,$1,"' _ "$DESTINO" < "$FILESTORE"

echo "Listo: base $DESTINO restaurada."
