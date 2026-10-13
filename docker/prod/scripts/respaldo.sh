#!/usr/bin/env bash
# Respaldo de duranPROD: base (pg_dump, formato custom) + filestore, y rotación.
#
# Deja cada respaldo en su propia carpeta con fecha:
#   $DESTINO/AAAAMMDD-HHMMSS/duranPROD.dump
#   $DESTINO/AAAAMMDD-HHMMSS/filestore.tar.gz
# y conserva solo los $CONSERVAR más recientes. La Mac los copia con rsync.
#
# Uso:  respaldo.sh                (lo programa cron/duran-respaldo)
# Variables opcionales: DESTINO (por defecto /var/backups/duran), CONSERVAR (14).
set -euo pipefail

DIR_PROD="$(cd "$(dirname "$0")/.." && pwd)"
DESTINO="${DESTINO:-/var/backups/duran}"
CONSERVAR="${CONSERVAR:-14}"
BASE="duranPROD"
FECHA="$(date +%Y%m%d-%H%M%S)"

compose() {
    docker compose --project-directory "$DIR_PROD" -f "$DIR_PROD/docker-compose.yml" "$@"
}

umask 077
mkdir -p "$DESTINO"
EN_CURSO="$DESTINO/.en-curso-$FECHA"
mkdir "$EN_CURSO"
# Si algo falla, no queda un respaldo a medias que parezca bueno.
trap 'rm -rf "$EN_CURSO"' EXIT

echo "$(date -Is) Inicio del respaldo de $BASE"

# 1) Primero la base y después el filestore: así el filestore trae todo lo
#    que la base menciona (si entra un adjunto en medio, sobra, no falta).
compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$1"' _ "$BASE" > "$EN_CURSO/$BASE.dump"
compose exec -T odoo tar -C /var/lib/odoo/filestore -czf - "$BASE" > "$EN_CURSO/filestore.tar.gz"

# 2) Comprobaciones mínimas: que no pesen 0 y que el dump tenga la firma PGDMP.
for archivo in "$EN_CURSO/$BASE.dump" "$EN_CURSO/filestore.tar.gz"; do
    if [ ! -s "$archivo" ]; then
        echo "ERROR: $archivo quedó vacío" >&2
        exit 1
    fi
done
if [ "$(head -c 5 "$EN_CURSO/$BASE.dump")" != "PGDMP" ]; then
    echo "ERROR: el dump no tiene la firma PGDMP" >&2
    exit 1
fi
gzip -t "$EN_CURSO/filestore.tar.gz"

mv "$EN_CURSO" "$DESTINO/$FECHA"
trap - EXIT
echo "$(date -Is) Respaldo listo: $DESTINO/$FECHA ($(du -sh "$DESTINO/$FECHA" | cut -f1))"

# 3) Rotación: borra los más viejos y deja los $CONSERVAR más recientes.
find "$DESTINO" -mindepth 1 -maxdepth 1 -type d -name '20*' | sort | head -n "-$CONSERVAR" | while read -r viejo; do
    echo "Borrando respaldo viejo: $viejo"
    rm -rf "$viejo"
done
