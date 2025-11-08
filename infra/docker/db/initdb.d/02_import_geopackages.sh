#!/bin/bash
set -euo pipefail

DATA_DIR="${GEOPACKAGE_DIR:-/opt/app/data}"
SOCKET_DIR="${POSTGRES_SOCKET_DIR:-/var/run/postgresql}"
HOST_OVERRIDE="${POSTGRES_HOST:-}"
INTERNAL_PORT="${POSTGRES_INTERNAL_PORT:-${POSTGRES_PORT:-5432}}"
DB_NAME="${POSTGRES_DB:-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_PASSWORD="${POSTGRES_PASSWORD:-postgres}"

if [ ! -d "${DATA_DIR}" ]; then
  echo ">> Geopackage directory '${DATA_DIR}' not found. Skipping import."
  exit 0
fi

shopt -s nullglob
declare -a FILES=()
for pattern in "${DATA_DIR}"/*.gpkg "${DATA_DIR}"/*.GPKG; do
  if [ -e "${pattern}" ]; then
    FILES+=("${pattern}")
  fi
done

if [ "${#FILES[@]}" -eq 0 ]; then
  echo ">> No .gpkg files detected under '${DATA_DIR}'. Nothing to import."
  exit 0
fi

if [ -n "${HOST_OVERRIDE}" ]; then
  HOST_PART="host=${HOST_OVERRIDE} port=${INTERNAL_PORT}"
else
  HOST_PART="host=${SOCKET_DIR} port=${INTERNAL_PORT}"
fi

PG_CONN="PG:${HOST_PART} dbname=${DB_NAME} user=${DB_USER} password=${DB_PASSWORD}"

echo ">> Waiting for PostgreSQL to accept connections..."
for attempt in $(seq 1 30); do
  if pg_isready -h "${HOST_OVERRIDE:-${SOCKET_DIR}}" -p "${INTERNAL_PORT}" -d "${DB_NAME}" -U "${DB_USER}" >/dev/null 2>&1; then
    break
  fi
  echo ">> postgres not ready yet (attempt ${attempt}/30). Retrying..."
  sleep 2
done

if ! pg_isready -h "${HOST_OVERRIDE:-${SOCKET_DIR}}" -p "${INTERNAL_PORT}" -d "${DB_NAME}" -U "${DB_USER}" >/dev/null 2>&1; then
  echo "!! postgres did not become ready in time. Aborting import."
  exit 1
fi

for file in "${FILES[@]}"; do
  base="$(basename "${file}")"
  echo ">> Importing ${base} into ${DB_NAME}"
  ogr2ogr -f PostgreSQL "${PG_CONN}" "${file}" \
    -lco GEOMETRY_NAME=geom \
    -lco FID=id \
    -nlt PROMOTE_TO_MULTI \
    -overwrite \
    -progress
done

echo ">> Completed geopackage import."
