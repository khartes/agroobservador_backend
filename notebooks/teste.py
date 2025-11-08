from datetime import datetime
import os
import sys
from pathlib import Path
from pystac_client import Client


PROJECT_ROOT = Path.cwd()  # onde está o .ipynb
sys.path.append(str(PROJECT_ROOT))

from utils.database import fetch_vector_from_postgres


os.environ['DB_HOST'] = "localhost"
os.environ["DB_PORT"] = "5433"
os.environ['DB_NAME'] = "hackathon"
os.environ['DB_USER'] = "hack_user"
os.environ['DB_PASSWORD'] = "hack_pass"

PG_URI = "postgresql://{0}:{1}@{2}:{3}/{4}".format( os.environ['DB_USER'],
                                                    os.environ['DB_PASSWORD'],
                                                    os.environ['DB_HOST'],
                                                    os.environ['DB_PORT'],
                                                    os.environ['DB_NAME'])


def search_scenes(STAC_API_URL, collection, geom, start_date, end_date, query=None, limit=1000):
    """
    Busca as cenas disponíveis para o território e período definidos.
    Retorna: lista de features (imagens encontradas)
    """
    items = []   
    client = Client.open(STAC_API_URL, headers=[], timeout=(3, 10))  
    try:
        search = client.search(
            collections=[collection],
            intersects=geom,
            datetime= f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}",
            query=query,
            max_items=limit
        )
        items = list(search.items())
        if items:
            print(f"Found {len(items)} images in {collection}")
            items.sort(key=lambda x: x.properties["datetime"], reverse=True)
            items = items
        else:
            print(f"No images found in {collection}")
    except Exception as e:
        print(f"Error searching {collection} images: {str(e)}")
    
    return items



STAC_URL = "https://landsatlook.usgs.gov/stac-server"

query ="SELECT id, luh_nm, ST_envelope(geom) geom FROM unidades_hidrograficas where luh_nm = 'Rio Jardim';"
UH = fetch_vector_from_postgres(PG_URI, query)
AOI_POLY = UH.iloc[0].geom.__geo_interface__
AOI_BBOX = UH.total_bounds.tolist()

DATA_INICIO_VAZIO = datetime.strptime("2025-07-01", "%Y-%m-%d")
DATA_FIM_VAZIO    = datetime.strptime("2025-09-30", "%Y-%m-%d")




COLLECTION = "landsat-c2l2-sr"  # Landsat Collection 2 Level 2 Surface Reflectance
query = {
        "platform": {"in": ["LANDSAT_8","LANDSAT_9"]},
        "eo:cloud_cover": {"lt": 10}
    }
scenes = search_scenes(STAC_URL, COLLECTION, AOI_POLY, DATA_INICIO_VAZIO, DATA_FIM_VAZIO, query=query)



print(f"Total scenes found: {len(scenes)}")
for scene in scenes:
    print(f"ID: {scene.id}, Date: {scene.properties['datetime']}, Cloud Cover: {scene.properties.get('eo:cloud_cover', 'N/A')}%")

import subprocess

asset_url = f"/vsicurl/{scene.assets['nir08'].get_absolute_href()}"
asset_url = f"/vsicurl/{scene.assets['red'].get_absolute_href()}"
output_file = os.path.join("/home/astolfinho/Documentos/vazio_sanitario/data", f"nir.tif")
cmd = [
    "gdalwarp",
    "-tr", f"{500/112000}", f"{500/112000}",
    "-r", "max",
    "-t_srs", "EPSG:4326",
    asset_url,
    output_file
]
subprocess.run(cmd, check=True)