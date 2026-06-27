# PointElevationAPI

A Python utility for querying interpolated point elevations from global and regional Digital Elevation Models (DEMs) hosted on OpenTopography S3 infrastructure. Uses GDAL's `gdallocationinfo` under the hood to sample raster values directly from VRT files without downloading full datasets.

## Overview

Given a longitude/latitude, the API returns the interpolated elevation, the dataset shortname, and the Vertical Coordinate Reference System (VCRS) in both WKT and EPSG formats. The default dataset is Copernicus 30m (COP30).


## Usage

**Simple mode** (defaults to COP30):
```bash
python PointElevationAPI.py <lon> <lat>
python PointElevationAPI.py -104.9963 39.7471
```

**Specific dataset:**
```bash
python PointElevationAPI.py <shortname> <lon> <lat>
python PointElevationAPI.py USGS30m -104.9963 39.7471
```

**Test mode** (queries all datasets):
```bash
python PointElevationAPI.py test <lon> <lat>
```

**Custom metadata file:**
```bash
python PointElevationAPI.py --jsonFile my_metadata.json USGS30m -104.9963 39.7471
```

Output is written to `output.json`:
```json
{
    "Elevation": "1609.5",
    "Shortname": "USGS30m",
    "VCRS_WKT": "...",
    "VCRS_EPSG": "5703",
    "Unit": "Meters"
}
```

## Supported Datasets

| Shortname | Coverage | Vertical Datum |
|---|---|---|
| COP30 / COP90 | Global | EGM2008 Geoid |
| USGS10m / USGS30m | CONUS | NAVD88 |
| ArcticDEM2m / 10m / 32m | Arctic | WGS84 Ellipsoid |
| REMA2m / 10m / 32m | Antarctica | WGS84 Ellipsoid |
| GEDI_L3 | Global (~52°S–52°N) | WGS84 Ellipsoid |
| EU_DTM | Europe | EGM2008 Geoid |
| NASADEM | Global | EGM96 Geoid |
| AW3D30 / AW3D30_E | Global | EGM96 / WGS84 Ellipsoid |
| SRTM_GL1 / GL3 / GL1_Ellip | Global | EGM96 / WGS84 Ellipsoid |
| SRTM15Plus | Global (ocean+land) | EGM96 Geoid |
| GEBCOIceTopo / SubIceTopo | Global | Mean Sea Level |
| CA_MRDEM | Canada | CGVD2013 |
| LINZ1m_DSM / DTM | New Zealand | NZVD2016 |

## Integration Tests

`integration_tests.py` runs against the live OpenTopography service and cross-validates results against the public [opentopodata.org](https://www.opentopodata.org) API. Tests cover:

- Simple mode (COP30) across 10 global locations
- Each dataset against multiple locations
- Error handling (invalid coordinates, bad dataset names)
- All datasets queried for a single reference point

Logs are written to `logs/outputlog_<timestamp>.log`.

```bash
python integration_tests.py
```

Requires `ot.api_key` to be present in the project root.

## Dependencies

- Python 3.x
- GDAL (`gdallocationinfo`, `gdalsrsinfo` must be on `PATH`)
- `requests`
