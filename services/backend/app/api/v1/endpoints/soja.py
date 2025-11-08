from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()

SOJA_GEOJSON_SQL = text(
    """        with a as (
        select
            id,
            ST_Simplify(geom, 20./100000., true) geom
        from
            vetorizado
    )
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'bbox', format('%s,%s,%s,%s', ST_XMin(st_extent(geom)),ST_YMin(st_extent(geom)),ST_XMax(st_extent(geom)),ST_YMax(st_extent(geom))),
        'features', json_agg(ST_AsGeoJSON(a, 'geom')::json)
        ) AS geojson
    FROM a
    """
)


INDICIO_SOJA_GEOJSON_SQL = text(
    """        with a as (
        select
            id,
            geom
        from
            indicios_de_cultivo_de_soja
    )
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'bbox', format('%s,%s,%s,%s', ST_XMin(st_extent(geom)),ST_YMin(st_extent(geom)),ST_XMax(st_extent(geom)),ST_YMax(st_extent(geom))),
        'features', json_agg(ST_AsGeoJSON(a, 'geom')::json)
        ) AS geojson
    FROM a
    """
)



@router.get(
    "/soja",
    summary="Lista os imóveis como GeoJSON (FeatureCollection).",
)
def soja(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Retorna todos os imóveis como GeoJSON em WGS84 (EPSG:4326)."""
    result = db.execute(SOJA_GEOJSON_SQL).scalar_one_or_none()
    return result or {"type": "FeatureCollection", "features": []}


@router.get(
    "/indicio_de_soja",
    summary="Lista os imóveis como GeoJSON (FeatureCollection).",
)
def indicio_soja(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Retorna todos os imóveis como GeoJSON em WGS84 (EPSG:4326)."""
    result = db.execute(INDICIO_SOJA_GEOJSON_SQL).scalar_one_or_none()
    return result or {"type": "FeatureCollection", "features": []}