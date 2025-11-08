
"""Helpers for composing raster and vector map layers."""
from __future__ import annotations
from typing import Any, Dict, Optional
from sqlalchemy import create_engine
import geopandas as gpd

def fetch_vector_from_postgres(
    connection_uri: str,
    sql: str,
    geom_column: str = "geom",
    params: Optional[Dict[str, Any]] = None,
) -> gpd.GeoDataFrame:
    """Read a GeoDataFrame from a PostGIS enabled PostgreSQL database."""

    engine = create_engine(connection_uri)
    try:
        gdf = gpd.read_postgis(sql=sql, con=engine, geom_col=geom_column, params=params)
    finally:
        engine.dispose()
    return gdf