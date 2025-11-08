from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()

IMOVEIS_GEOJSON_SQL = text(
    """        with a as (
        select
            id,
            cod_imovel,
            municipio,
            modulos_ru,
            ST_Simplify(geom, 20./100000., true) geom
        from
            imoveis
    )
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'bbox', format('%s,%s,%s,%s', ST_XMin(st_extent(geom)),ST_YMin(st_extent(geom)),ST_XMax(st_extent(geom)),ST_YMax(st_extent(geom))),
        'features', json_agg(ST_AsGeoJSON(a, 'geom')::json)
        ) AS geojson
    FROM a
    """
)

IMOVEIS_COM_INDICIOS_DE_SOJA_GEOJSON_SQL = text("""
 with a as (SELECT 
    i.id,
    i.cod_imovel,
    i.municipio,
    i.modulos_ru,
    round((st_area((st_intersection(i.geom, s.geom ))::geography )/10000)::numeric, 2) area_ha , i.geom
FROM 
    "public"."imoveis"  as i inner join
    "public"."indicios_de_cultivo_de_soja" as s 
    ON
        i.geom && s.geom and st_intersects(i.geom, s.geom ) order by st_area(st_intersection(i.geom, s.geom )) desc)
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'bbox', format('%s,%s,%s,%s', ST_XMin(st_extent(geom)),ST_YMin(st_extent(geom)),ST_XMax(st_extent(geom)),ST_YMax(st_extent(geom))),
        'features', json_agg(ST_AsGeoJSON(a, 'geom')::json)
        ) AS geojson
    FROM a
""")

@router.get(
    "/imoveis",
    summary="Lista os imóveis como GeoJSON (FeatureCollection).",
)
def list_imoveis_geojson(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Retorna todos os imóveis como GeoJSON em WGS84 (EPSG:4326)."""
    result = db.execute(IMOVEIS_GEOJSON_SQL).scalar_one_or_none()
    return result or {"type": "FeatureCollection", "features": []}


@router.get(
    "/imoveis_com_indicios_de_soja",
    summary="Lista os imóveis como GeoJSON (FeatureCollection).",
)
def imoveis_com_indicios_de_soja(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Retorna todos os imóveis como GeoJSON em WGS84 (EPSG:4326)."""
    result = db.execute(IMOVEIS_COM_INDICIOS_DE_SOJA_GEOJSON_SQL).scalar_one_or_none()
    return result or {"type": "FeatureCollection", "features": []}