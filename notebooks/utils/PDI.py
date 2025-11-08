import numpy as np
import xarray as xr
from pystac_client import Client
import stackstac, rasterio
from rasterio.transform import Affine
from datetime import datetime


# ---------- Utilitários ----------

def newest_item(items):
    if not items:
        return None
    items_sorted = sorted(items, key=lambda it: it.datetime or datetime.fromisoformat(it.properties.get("datetime")), reverse=True)
    return items_sorted[0]

def search_newest_stac(stac_url, collection, start, end, aoi, extra=None):
    cat = Client.open(stac_url, headers=[], ignore_conformance=True)
    params = {"collections":[collection], "datetime":f"{start}/{end}", "intersects":aoi, "limit":1000}
    if extra: params.update(extra)
    items = list(cat.search(**params).get_items())
    return newest_item(items)


def search_stac(stac_url, collection, start, end, aoi, extra=None):
    cat = Client.open(stac_url, headers=[], ignore_conformance=True)
    params = {"collections":[collection], "datetime":f"{start}/{end}", "intersects":aoi, "limit":1000}
    if extra: params.update(extra)
    return list(cat.search(**params).get_items())

def stack_s2(items, bbox, PIXEL_RES=10, CHUNK=1024):
    # Earth Search usa aliases: red(B04), nir(B08), swir16(B11), rededge2(B06), scl(mask)
    assets = ("red","nir","swir16","rededge2","scl")
    common = set(assets)
    for it in items: common &= set(it.assets.keys())
    req = {"red","nir","swir16","rededge2"}
    if not req.issubset(common):
        raise RuntimeError(f"S2 sem assets mínimos {req}. Presentes: {sorted(common)}")
    use = sorted(common)
    da = stackstac.stack(items, assets=use, bounds_latlon=bbox, epsg=4326, resolution=PIXEL_RES, chunksize=CHUNK)
    return da.transpose("time","y","x","band")

def stack_s1(items, bbox, chunksize=1024):
    # Confere assets comuns (alguns itens podem vir sem vh/vv)
    wanted = {"vv", "vh"}
    common = set(wanted)
    for it in items:
        common &= set(it.assets.keys())

    if not wanted.issubset(common):
        ex = list(items[0].assets.keys())
        raise RuntimeError(f"S1 sem vv/vh em todos os itens. Comuns: {sorted(common)} | Exemplo: {ex}")

    use_assets = ["vv", "vh"]  # <<<<< LISTA, não tupla
    da = stackstac.stack(
        items,
        assets=use_assets,       # <<<<< LISTA
        bounds_latlon=bbox,
        epsg=4326,
        resolution=10,
        chunksize=chunksize,
    )
    return da.transpose("time", "y", "x", "band")


def s2_mask_scale(s2_da: xr.DataArray) -> xr.DataArray:
    bands = list(s2_da.band.values)
    has_scl = "scl" in bands
    mask = xr.ones_like(s2_da.isel(band=0), dtype=bool)
    if has_scl:
        scl = s2_da.sel(band="scl")
        scl_ok = (scl > 3) & (~scl.isin([8,9,10,11]))  # remove sombra/nuvens
        mask = mask & scl_ok
    out = s2_da.copy()
    for b in ["red","nir","swir16","rededge2"]:
        arr = out.sel(band=b)
        # escala segura: se max>1, assume 0..10000 e divide por 1e4
        needs_scale = (arr.max(skipna=True) > 1.0)
        arr = xr.where(needs_scale, arr/10000.0, arr)
        out.loc[dict(band=b)] = arr.where(mask)
    if has_scl:
        out.loc[dict(band="scl")] = out.sel(band="scl").where(mask)
    return out

def s2_indices(s2_da: xr.DataArray) -> xr.Dataset:
    R = s2_da.sel(band="red"); N = s2_da.sel(band="nir"); SW = s2_da.sel(band="swir16"); RE2 = s2_da.sel(band="rededge2")
    ndvi = (N - R) / (N + R)
    ndwi = (N - SW) / (N + SW)
    re2n = (RE2 - R) / (RE2 + R)
    return xr.Dataset({"NDVI": ndvi, "NDWI": ndwi, "RE2N": re2n})



def s1_feats(s1_da: xr.DataArray) -> xr.Dataset:
    # Seleciona e remove o coord 'band' (que vem como escalar e conflita no merge)
    vv = s1_da.sel(band="vv").reset_coords(drop=True).drop_vars("band", errors="ignore")
    vh = s1_da.sel(band="vh").reset_coords(drop=True).drop_vars("band", errors="ignore")

    # Evita log10(0) e mantém compatível com Dask
    vv_safe = vv.clip(min=1e-6)
    vh_safe = vh.clip(min=1e-6)

    vv_db = 10.0 * xr.apply_ufunc(
        np.log10, vv_safe,
        dask="parallelized",
        output_dtypes=[vv.dtype]
    ).reset_coords(drop=True)

    vh_db = 10.0 * xr.apply_ufunc(
        np.log10, vh_safe,
        dask="parallelized",
        output_dtypes=[vh.dtype]
    ).reset_coords(drop=True)

    ratio = (vv / xr.where(vh <= 0, np.nan, vh)).reset_coords(drop=True)

    # Garante nomes e ausência de coords conflitando
    vv_db.name = "VV_dB"
    vh_db.name = "VH_dB"
    ratio.name = "VVVH_lin"

    # Constrói o Dataset com variáveis que NÃO têm coord 'band'
    ds = xr.Dataset({
        "VV_dB": vv_db,
        "VH_dB": vh_db,
        "VVVH_lin": ratio
    })

    return ds

def reduce_period(ds: xr.Dataset) -> xr.Dataset:
    med = ds.median("time")
    p90 = ds.quantile(0.90, "time")
    out = xr.merge([med.rename({v: f"{v}_med" for v in med.data_vars}),
                    p90.rename({v: f"{v}_p90" for v in p90.data_vars})])
    if "NDVI" in ds:
        t = xr.DataArray(np.arange(ds.sizes["time"]), dims=["time"])
        ndvi = ds["NDVI"]
        cov = ((t - t.mean())*(ndvi - ndvi.mean("time"))).sum("time")/(ndvi.count("time")-1)
        var = ((t - t.mean())**2).sum()
        slope = (cov/var).rename("NDVI_slope")
        out = xr.merge([out, slope])
    return out

def affine_from_coords(x, y) -> Affine:
    res_x = float(x[1]-x[0]); res_y = float(y[1]-y[0])
    return Affine(res_x, 0, float(x.min()), 0, res_y, float(y.max()))

def save_geotiff(path, array2d, x, y, crs="EPSG:4326", dtype="float32", compress="deflate"):
    h, w = array2d.shape
    transform = affine_from_coords(x, y)
    profile = {"driver":"GTiff","height":h,"width":w,"count":1,"dtype":dtype,"crs":crs,"transform":transform,"compress":compress}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array2d.astype(dtype), 1)


from contextlib import contextmanager

@contextmanager
def rio_fast_env():
    with rasterio.Env(
        GDAL_NUM_THREADS='ALL_CPUS',  # paraleliza escrita
        NUM_THREADS='ALL_CPUS',
        # compressão padrão para todos os GeoTIFFs
        # (ainda dá para sobrescrever no profile por arquivo)
        ) as env:
        yield env


def save_geotiff_fast(path, array2d, x, y, crs="EPSG:4326",
                      dtype="float32", compress="ZSTD", block=512, zlevel=9):
    # array2d pode ser um dask array -> compute antes de escrever
    if hasattr(array2d, "compute"):
        array2d = array2d.astype(dtype).compute()
    else:
        array2d = array2d.astype(dtype)

    h, w = array2d.shape
    res_x = float(x[1]-x[0]); res_y = float(y[1]-y[0])
    transform = Affine(res_x, 0, float(x.min()), 0, res_y, float(y.max()))

    profile = {
        "driver": "GTiff",
        "height": h, "width": w, "count": 1,
        "dtype": dtype, "crs": crs, "transform": transform,
        "tiled": True, "blockxsize": block, "blockysize": block,
        "compress": compress,
        "ZLEVEL": zlevel,  # para ZSTD/DEFLATE
        # predictor ajuda em float: 3 (floating-point), melhora compressão e I/O
        "PREDICTOR": 3 if dtype.startswith("float") else 2,
        # BigTIFF automático se precisar
        "BIGTIFF": "IF_SAFER",
    }

    with rio_fast_env():
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(array2d, 1)