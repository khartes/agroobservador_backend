from h3 import geo_to_cells
from pystac_client import Client
import boto3
import json
import os
import subprocess
import pandas as pd
from .utils import simplificar_poligono,  geojson_para_wkt, bbox_dos_hexagonos, calcular_pixels_utilizados
from .make_gdalenhance_lut import make_gdalenhance_lut
from h3 import cells_to_geo

STAC_API_URL = "https://data.inpe.br/bdc/stac/v1"
BUCKET_NAME = os.environ['BUCKET_NAME']

S3_CLIENT = boto3.client('s3')


class INPEImageAssembler(object):

    def __init__(self, output_dir="/tmp/inpe_images"):
        """
        start_date: str (data de início) no formato 'YYYY-MM-DD'
        end_date: str (data de término) no formato 'YYYY-MM-DD' 
        """
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        else:
            subprocess.run(f"rm -rf {output_dir}/*", shell=True)
            
        headers = []
        self.client = Client.open(STAC_API_URL, headers=headers, timeout=(3, 10))

    def search_scenes(self, collection, geom, start_date, end_date, limit=1000):
        """
        Busca as cenas disponíveis para o território e período definidos.
        Retorna: lista de features (imagens encontradas)
        """
        self.items = []     
        try:
            search = self.client.search(
                collections=[collection],
                intersects=geom,
                datetime= f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}",
                max_items=limit
            )
            items = list(search.items())
            if items:
                print(f"Found {len(items)} images in {collection}")
                items.sort(key=lambda x: x.properties["datetime"], reverse=True)
                self.items = items
            else:
                print(f"No images found in {collection}")
        except Exception as e:
            print(f"Error searching {collection} images: {str(e)}")

    def download_low_resolution_asset(self):
        """
        Baixa imagens de pré-visualização (baixa resolução) para análise.
        """
        self.assets = {}
        for i in self.items:
            if 'tci' in i.assets:
                asset_url = f"/vsicurl/{i.assets['tci'].get_absolute_href()}"
                output_file = os.path.join(self.territory_output_dir, f"{i.id}_low_res.tif")
                cmd = [
                    "gdalwarp",
                    "-tr", f"{500/112000}", f"{500/112000}",
                    "-r", "max",
                    "-t_srs", "EPSG:4326",
                    asset_url,
                    output_file
                ]
                subprocess.run(cmd, check=True)
                self.assets[i.id] = {
                    "asset_url": asset_url,
                    "low_res": output_file
                }
            else:
                print(f"No TCI asset found for {i.id}")

    def calculate_image_useful_area(self):
        """
        Calcula a área útil de cada imagem.
        Atualiza os itens com a área útil calculada.
        """
        for k, item in self.assets.items():
            print(f"Calculating useful area for {k} - {item}")
            footprint_path = os.path.join(self.territory_output_dir, f"{k}_footprint.tif")
            footprint_geojson_path = os.path.join(self.territory_output_dir, f'{k}_footprint.geojson')

            areautil_path = os.path.join(self.territory_output_dir, f'{k}_areautil.tif')
            areautil_geojson_path = os.path.join(self.territory_output_dir, f'{k}_areautil.geojson')

            subprocess.run([
                "gdal_calc.py",
                "-A", item["low_res"], "--A_band=1",
                "-B", item["low_res"], "--B_band=2",
                "-C", item["low_res"], "--C_band=3",
                f"--outfile={footprint_path}",
                "--calc=\"logical_and(A>0,B>0,C>0)\"",
                "--NoDataValue=0",
                "--overwrite"
            ])

            subprocess.run([
                "gdal_calc.py",
                "-A", item["low_res"], "--A_band=1",
                "-B", item["low_res"], "--B_band=2",
                "-C", item["low_res"], "--C_band=3",
                f"--outfile={areautil_path}",
                "--calc=\"(logical_and(A>0,B>0,C>0)*1 - logical_and(A>125,B>125,C>125)*1)==1\"",
                "--NoDataValue=0",
                "--overwrite"
            ])

            subprocess.run([
                "gdal_polygonize.py",
                footprint_path,
                "-mask", footprint_path,
                "-f", "GeoJSON",
                footprint_geojson_path,
            ])

            subprocess.run([
                "gdal_polygonize.py",
                areautil_path,
                "-mask", areautil_path,
                "-f", "GeoJSON",
                areautil_geojson_path,
            ])
            

            with open(footprint_geojson_path, 'r') as f:
                footprint_pol = json.load(f)['features'][0]['geometry']

            with open(areautil_geojson_path, 'r') as f:
                areautil_pol = json.load(f)            

           
            hex_resolution = 8  # Hex resolution of 8
            aoi_hexes = set(geo_to_cells(self.territory.bbox_optimum, hex_resolution))  # Hex resolution of 8

            footprint_hexes = set(geo_to_cells(footprint_pol, hex_resolution)).intersection(aoi_hexes)

            areautil_hexes = []
            for feature in areautil_pol['features']:
                areautil_hexes.extend(geo_to_cells(feature['geometry'], hex_resolution))
            areautil_hexes= set(areautil_hexes).intersection(aoi_hexes)

            if len(footprint_hexes) > 0 and len(areautil_hexes)/len(footprint_hexes) > 0.90:
                item["useful_area"] = footprint_pol

            print("Useful area calculation completed.")
            with open(footprint_geojson_path, 'w') as f:
                f.write(json.dumps(cells_to_geo(footprint_hexes, False)))

            with open(areautil_geojson_path, 'w') as f:
                f.write(json.dumps(cells_to_geo(areautil_hexes, False)))

    def select_image_patches(self):
        """
        Seleciona os melhores trechos de cada cena com base em critérios como:
        cobertura, ausência de nuvem, posição e sobreposição.
        """
        hex_resolution = 8  # Hex resolution of 8
        aoi_hexes = set(geo_to_cells(self.territory.bbox_optimum, hex_resolution))  # Hex resolution of 8

        img_ids = []
        hex_ids = [] 

        for k, item in self.assets.items():
            if 'useful_area' in item:
                hexes = set(geo_to_cells(item['useful_area'], hex_resolution)).intersection(aoi_hexes)
                hex_ids.extend(hexes)
                img_ids.extend([k for n in range(len(hexes))])

        df = pd.DataFrame({
            'hex_id': hex_ids,
            'img_id': img_ids
        })

        hexes_a_cobrir = set(df['hex_id'].unique())
        imagens_selecionadas = {}
        selection_order = []

        while hexes_a_cobrir:
            cobertura = df[df['hex_id'].isin(hexes_a_cobrir)].groupby('img_id')['hex_id'].nunique()
            melhor_img = cobertura.idxmax()   
            selection_order.append(melhor_img) 
            hexes_cobertos_por_melhor = set(df[df['img_id'] == melhor_img]['hex_id']) & hexes_a_cobrir
            imagens_selecionadas[melhor_img] = hexes_cobertos_por_melhor
            hexes_a_cobrir -= hexes_cobertos_por_melhor
        self.selected_images = imagens_selecionadas
        self.selection_order = selection_order
        return imagens_selecionadas
    
    def download_selected_patches(self):
        """
        Baixa os trechos selecionados em alta resolução.
        """
        epsg = "EPSG:4326"
        for img_id, hexes in self.selected_images.items():
            bbox_hex = bbox_dos_hexagonos(hexes)
            minlon, minlat, maxlon, maxlat = bbox_hex
            largura_px, altura_px = calcular_pixels_utilizados(
                self.territory.bbox_optimum, 
                bbox_hex, 
                self.territory.paper_width_px, 
                self.territory.paper_height_px)
            output_file = os.path.join(self.territory_output_dir, f"{img_id}_high_res.tif")
            cmd = [
                "gdalwarp",
                "-te", str(minlon), str(minlat), str(maxlon), str(maxlat),
                "-te_srs", epsg,
                "-ts", str(largura_px), str(altura_px),
                "-t_srs", epsg,
                "-r", "bilinear",
                "-overwrite",
                self.assets[img_id]['asset_url'], 
                output_file
            ]
            subprocess.run(cmd, check=True)
            self.assets[img_id]['high_res'] = output_file

    # def calibrate_contrast_reference(self):
    #     """
    #     Identifica o trecho com melhor contraste para usar como referência.
    #     """

    #     biggest_image = os.path.join(self.territory_output_dir, f"{self.selection_order[0]}_high_res.tif")
    #     self.contrast_path = os.path.join(self.territory_output_dir, "contrast.gdalenhance")
    #     scales = make_gdalenhance_lut(
    #         biggest_image,
    #         self.contrast_path,
    #         p_low=2, p_high=98, gamma=1
    #     )

    def apply_contrast_to_all(self):
        """
        Aplica a correção de contraste nos demais trechos com base na referência.
        """
        import re
        from collections import defaultdict
        by_date = defaultdict(list)
        pat = re.compile(r'_(\d{8})_')

        for s in self.selection_order:
            m = pat.search(s)
            if not m:
                continue  # ou raise se quiser ser estrito
            date = m.group(1)
            by_date[date].append(s)


        for date in by_date:
            images = by_date[date]
            img_id = images[0]
            contrast_path = os.path.join(self.territory_output_dir, f"{date}_contrast.gdalenhance")
            biggest_image = os.path.join(self.territory_output_dir, f"{img_id}_high_res.tif")
            make_gdalenhance_lut(
                biggest_image,
                contrast_path,
                p_low=1, p_high=99, gamma=2
            )
            for img_id in images:
                input_file = os.path.join(self.territory_output_dir, f"{img_id}_high_res.tif")
                output_file = os.path.join(self.territory_output_dir, f"{img_id}_enhance.tif")
                cmd = [
                    "gdalenhance",
                    "-config", contrast_path,
                    input_file,
                    output_file
                ]
                subprocess.run(cmd, check=True)
                self.assets[img_id]['enhance'] = output_file

    def generate_mosaic(self):
        """
        Gera o mosaico final a partir dos trechos corrigidos.
        """
        images = self.selection_order
        images.reverse()  # Ordem de sobreposição: do mais antigo para o mais recente    
        inputs = [self.assets[img_id]['enhance'] for img_id in images]
        mosaic_path = os.path.join(self.territory_output_dir, f"mosaic_{self.territory.id}.tif")

        cmd = [
            "gdal_merge.py",
            "-o", mosaic_path,
            "-of", "GTiff",
            "-co", "COMPRESS=LZW",
            *inputs
        ]
        subprocess.run(cmd, check=True)
        self.mosaic_path = mosaic_path

        S3_CLIENT.upload_file( self.mosaic_path, BUCKET_NAME, f"territorios/mosaic_{self.territory.id}.tif")

    def clean_outputdir(self):
        subprocess.run(f"rm -rf {self.output_dir}/*", shell=True)

    def process(self, collection, territory, start_date, end_date, limit=1000):
        """
        Executa a sequência completa de etapas de montagem do mosaico.

        Este método pode ser chamado por um controlador externo que percorre
        diferentes territórios ou datas.
        """
        self.territory = territory
        
        print(f"Processing {collection} for territory {territory.id} from {start_date} to {end_date}")
        output_dir = os.path.join(self.output_dir, str(territory.id))   
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        else:
            subprocess.run(f"rm -rf {output_dir}/*", shell=True)

        self.territory_output_dir = output_dir

        self.search_scenes(collection, territory.geom, start_date, end_date, limit=limit)
        self.download_low_resolution_asset()
        self.calculate_image_useful_area()
        self.select_image_patches()
        self.download_selected_patches()
        # self.calibrate_contrast_reference()
        self.apply_contrast_to_all()
        self.generate_mosaic()
