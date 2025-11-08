FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin \
    && rm -rf /var/lib/apt/lists/*

ENV GEOPACKAGE_DIR=/opt/app/data

COPY infra/docker/db/initdb.d/ /docker-entrypoint-initdb.d/

RUN find /docker-entrypoint-initdb.d -type f -name "*.sh" -exec chmod +x {} \;
