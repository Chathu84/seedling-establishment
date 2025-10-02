from osgeo import gdal
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
from typing import Union, Tuple, Optional

# ---------- PRISM helpers (VSI) ----------
_RES_CODE = {"4km": "25m", "800m": "30s", "400m": "15s"}

def _as_datecode(date: Union[str, dt.date, dt.datetime], freq: str) -> Tuple[str, str]:
    """
    Parse date for PRISM naming. Accepts:
      daily:    'YYYY-MM-DD' or 'YYYYMMDD'
      monthly:  'YYYY-MM'    or 'YYYYMM'
      annual:   'YYYY'
    Also accepts datetime/date objects.
    Returns: (datecode, yyyy)
    """
    if isinstance(date, (dt.datetime, dt.date)):
        d = date if isinstance(date, dt.date) and not isinstance(date, dt.datetime) else date.date()
    elif isinstance(date, str):
        s = date.strip()
        if freq == "daily":
            # Try ISO first, then compact
            try:
                d = dt.datetime.strptime(s, "%Y-%m-%d").date()
            except ValueError:
                d = dt.datetime.strptime(s, "%Y%m%d").date()
        elif freq == "monthly":
            # Use day=1 internally
            try:
                d = dt.datetime.strptime(s, "%Y-%m").date().replace(day=1)
            except ValueError:
                d = dt.datetime.strptime(s, "%Y%m").date().replace(day=1)
        elif freq == "annual":
            d = dt.datetime.strptime(s, "%Y").date().replace(month=1, day=1)
        else:
            raise ValueError("freq must be one of: 'daily','monthly','annual'")
    else:
        raise TypeError("date must be str, datetime, or date")

    if freq == "daily":
        return d.strftime("%Y%m%d"), d.strftime("%Y")
    elif freq == "monthly":
        return d.strftime("%Y%m"), d.strftime("%Y")
    else:  # annual
        return d.strftime("%Y"), d.strftime("%Y")

def build_prism_vsi(
    variable: str = "tmax",
    date: Union[str, dt.date, dt.datetime] = "2025-07-15",
    resolution: str = "800m",
    region: str = "us",
    freq: str = "daily",
    network: str = "an",
) -> str:
    if resolution not in _RES_CODE:
        raise ValueError("resolution must be one of {'800m','4km','400m'}")
    datecode, yyyy = _as_datecode(date, freq)
    res_code = _RES_CODE[resolution]
    base_dir = f"https://data.prism.oregonstate.edu/time_series/{region}/{network}/{resolution}/{variable}/{freq}/{yyyy}/"
    zip_name = f"prism_{variable}_{region}_{res_code}_{datecode}.zip"
    tif_name = f"prism_{variable}_{region}_{res_code}_{datecode}.tif"
    return f"/vsizip//vsicurl/{base_dir}{zip_name}/{tif_name}"

def gdal_open_prism(**kwargs) -> gdal.Dataset:
    vsi = build_prism_vsi(**kwargs)
    gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "YES")
    gdal.SetConfigOption("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".zip,.tif,.xml,.stx,.prj,.aux.xml")
    ds = gdal.Open(vsi, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"GDAL failed to open PRISM via VSI:\n{vsi}")
    return ds

def _extent_from_gt(ds) -> Tuple[float, float, float, float]:
    gt = ds.GetGeoTransform()
    w = ds.RasterXSize
    h = ds.RasterYSize
    xmin = gt[0]
    ymax = gt[3]
    xmax = xmin + w * gt[1]
    ymin = ymax + h * gt[5]
    return (xmin, xmax, ymin, ymax)

def plot_prism(
    variable="tmax",
    date="2025-07-15",
    resolution="800m",
    freq="daily",
    bbox: Optional[Tuple[float, float, float, float]] = None,  # minx,miny,maxx,maxy
    title: Optional[str] = None,
    vmin=None,
    vmax=None,
):
    """
    Stream a PRISM raster and plot it.
    If bbox is provided, data are warped/cropped in-memory before plotting.
    """
    ds = gdal_open_prism(variable=variable, date=date, resolution=resolution, freq=freq)

    # Optionally crop to bbox using a WarpedVRT (no download, server-side reads)
    if bbox:
        minx, miny, maxx, maxy = bbox
        warp_opts = gdal.WarpOptions(
            format="VRT",
            outputBounds=(minx, miny, maxx, maxy),
            dstSRS="EPSG:4326",
            resampleAlg="nearest"
        )
        vrt = gdal.Warp("", ds, options=warp_opts)
        src = vrt
    else:
        src = ds

    band = src.GetRasterBand(1)
    arr = band.ReadAsArray()
    arr = np.where(arr == band.GetNoDataValue(), np.nan, arr)

    extent = _extent_from_gt(src)
    plt.figure(figsize=(8, 6))
    im = plt.imshow(arr, extent=extent, origin="upper", vmin=vmin, vmax=vmax)
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    if title is None:
        title = f"PRISM {variable.upper()} ({freq}) {date}"
    plt.title(title)
    cb = plt.colorbar(im, shrink=0.85)
    cb.set_label(f"{variable} (native units)")
    plt.tight_layout()
    plt.show()

# 1) PRISM: daily max temp for Colorado Front Range, 2025-07-15
plot_prism(
    variable="tmax",
    date="2025-07-15",
    resolution="800m",
    freq="daily",
    bbox=[-106.0, 39.0, -104.5, 40.5],  # minx,miny,maxx,maxy
    title="PRISM TMAX daily (°C×10) — Front Range"
)

# 2) PRISM: monthly precipitation for March 2024, CONUS view
plot_prism(variable="ppt", date="2024-03", freq="monthly", resolution="4km")
