#!/usr/bin/env python

import subprocess
import json
import argparse
import sys
from typing import Tuple, List

"""
Description: Given a global/regional dataset shortname and a lat lon,
get the interpolated elevation for that point location. For simplified
queries, if the user only supplies a lon/lat, then Copernicus data is
used by default.

Date Created: March 13th 2025
Date Updated: December 10th 2025
Date Updated: January 2nd 2026

Input(s): shortname for a Global/Regional, longitude, latitude. If
you only enter a longitude and latitude it will default to Copernicus 30m
data.

Output(s): A JSON file, output.json, that contains the following
fields:
 Elevation. This is the interpolated elevation for the point.
 Shortname. This is the shortname of the OT dataset.
 VCRS_WKT. This is the Vertical Coordinate Reference System (VCRS) in
           standard WKT format.
 VCRS_EPSG. This is the VCRS EPSG code. 
 Unit. This is the unit of the elevation. It is currently
        HARD-CODED to meters.

Example of how to run in "simple" or default mode (i.e. using Copernicus 30m):
   python PointElevationAPI.py -104.9963 39.7471

Example of how to run with specific dataset: 
   python PointElevationAPI.py USGS30m -104.9963 39.7471

Example of how to run in "test" mode, which gets elevations for ALL datasets:
   python PointElevationAPI.py test -104.9963 39.7471

Example of how to run with custom JSON metadata file:
   python PointElevationAPI.py --jsonFile my_metadata.json USGS30m -104.9963 39.7471

Notes:
- All datasets use the -wgs84 flag with gdallocationinfo.
- Datasets with multiple VRTs (e.g., GEDI_L3 with _be, _hh, _vh variants) get special handling to select the appropriate VRT for elevation queries:
   Priority 1: bare earth (_be.vrt)
   Priority 2: highest hit (_hh.vrt)
- Metadata is loaded from JSON file (default: s3_url.json).
- Removed 0 from numeric_badvalues.  this list is now only used for tolerance-based checking.  We need to allow elevations near 0 to be valid.
- Kept '0' in badvalues - so an exact string match of '0' is still flagged as bad since COP30 uses 0 for bad values.
"""

# Global Parameters
badvalues = ['-999999', '-9999', '', '-32768', '0']
# Numeric bad values for tolerance checking (exclude 0 from tolerance checks)
numeric_badvalues = [-999999, -9999, -32768]
NODATA_TOLERANCE = 1.0  # Tolerance for floating-point NoData comparison
# Values >= this threshold are FLT_MAX-style NoData sentinels (e.g. GEDTM30 uses 3.4028234663852886e+38)
NODATA_LARGE_THRESHOLD = 1e38
DEFAULT_JSON_FILE = 's3_url.json'


class ElevationAPIError(Exception):
    """Custom exception for elevation API errors"""
    pass


def is_nodata_value(value_str: str) -> bool:
    """
    Check if a value is a NoData value, accounting for floating-point precision.
    
    Args:
        value_str: The elevation value as a string
        
    Returns:
        True if the value is considered NoData, False otherwise
    """
    # Check exact string matches first (includes empty string)
    if value_str in badvalues:
        return True
    
    # Try to convert to float for numeric comparison
    try:
        value_float = float(value_str)
    except ValueError:
        # If it can't be converted to float, it's invalid
        return True
    
    # FLT_MAX-style sentinels (e.g. GEDTM30 NoData = 3.4028234663852886e+38)
    if abs(value_float) >= NODATA_LARGE_THRESHOLD:
        return True

    # Check if the value is close to any known numeric bad value
    # Note: We exclude 0 from tolerance checking since values near 0 are valid elevations
    for bad_val in numeric_badvalues:
        if abs(value_float - bad_val) < NODATA_TOLERANCE:
            return True

    return False


def validate_coordinates(lon: str, lat: str) -> Tuple[float, float]:
    """
    Validate longitude and latitude inputs.
    
    Args:
        lon: Longitude as string
        lat: Latitude as string
        
    Returns:
        Tuple of (longitude, latitude) as floats
        
    Raises:
        ElevationAPIError: If coordinates are invalid
    """
    try:
        lon_float = float(lon)
        lat_float = float(lat)
    except ValueError:
        raise ElevationAPIError(f"Invalid coordinates: lon={lon}, lat={lat}. Must be numeric.")
    
    if not (-180 <= lon_float <= 180):
        raise ElevationAPIError(f"Longitude {lon_float} out of valid range [-180, 180]")
    
    if not (-90 <= lat_float <= 90):
        raise ElevationAPIError(f"Latitude {lat_float} out of valid range [-90, 90]")
    
    return lon_float, lat_float


def get_wkt(vertical_epsg: str) -> str:
    """
    Get the standard WKT format for the CRS based on its EPSG code.
    
    Args:
        vertical_epsg: EPSG code as string
        
    Returns:
        WKT string representation of the CRS
        
    Raises:
        ElevationAPIError: If gdalsrsinfo command fails
    """
    cmd = ['gdalsrsinfo', f'epsg:{vertical_epsg}', '-o', 'wkt']
    
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return p.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise ElevationAPIError(f"Failed to get WKT for EPSG:{vertical_epsg}: {e.stderr}")


def get_metadata_from_json(shortname: str, json_file: str = DEFAULT_JSON_FILE) -> Tuple[str, str, str, str]:
    """
    Query metadata from JSON file based on shortname.
    
    For datasets with multiple VRTs (e.g., GEDI_L3 with _be, _hh, _vh variants),
    this function selects the appropriate VRT for elevation queries:
    Priority 1: bare earth (_be.vrt)
    Priority 2: highest hit (_hh.vrt)
    
    Args:
        shortname: Dataset short name
        json_file: Path to JSON metadata file
        
    Returns:
        Tuple of (short_name, vertical_coordinate, vertical_epsg, s3_url)
        
    Raises:
        ElevationAPIError: If shortname not found, file not found, or no valid 
                          elevation VRT found for datasets with multiple VRTs
    """
    try:
        with open(json_file, 'r') as f:
            metadata = json.load(f)
    except FileNotFoundError:
        raise ElevationAPIError(f"JSON metadata file '{json_file}' not found")
    except json.JSONDecodeError as e:
        raise ElevationAPIError(f"Error parsing JSON file: {e}")
    
    # Filter results for this shortname
    results = [item for item in metadata if item['short_name'] == shortname]
    
    if not results:
        raise ElevationAPIError(f"Shortname '{shortname}' not found in JSON metadata")
    
    # If only one result, return it
    if len(results) == 1:
        item = results[0]
        return item['short_name'], item['vertical_coordinate'], item['vertical_epsg'], item['s3_url']
    
    # Multiple results - look for bare earth (_be.vrt) first
    be_results = [item for item in results if item['s3_url'].endswith('_be.vrt')]
    if be_results:
        item = be_results[0]
        return item['short_name'], item['vertical_coordinate'], item['vertical_epsg'], item['s3_url']
    
    # Otherwise look for highest hit (_hh.vrt)
    hh_results = [item for item in results if item['s3_url'].endswith('_hh.vrt')]
    if hh_results:
        item = hh_results[0]
        return item['short_name'], item['vertical_coordinate'], item['vertical_epsg'], item['s3_url']
    
    # If neither _be nor _hh found, raise error
    available_vrts = [item['s3_url'] for item in results]
    raise ElevationAPIError(
        f"Multiple VRTs found for '{shortname}', but none are suitable for "
        f"elevation queries (_be.vrt or _hh.vrt). Available: {', '.join(available_vrts)}"
    )


def run_gdallocationinfo(s3_url: str, lon: str, lat: str) -> str:
    """
    Run gdallocationinfo command to get elevation at point.
    
    Args:
        s3_url: URL to the dataset VRT
        lon: Longitude
        lat: Latitude
        
    Returns:
        Elevation value as string
        
    Raises:
        ElevationAPIError: If command fails
    """
    cmd = ['gdallocationinfo', '-wgs84', '-valonly', s3_url, lon, lat]
    
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return p.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise ElevationAPIError(f"gdallocationinfo failed: {e.stderr}")


def write_to_json(elevation: str, shortname: str, vertical_coordinate: str, 
                  vertical_epsg: str, filename: str = "output.json") -> None:
    """
    Writes elevation, shortname, and VCRS to a JSON file.

    Args:
        elevation: The elevation value
        shortname: The dataset shortname
        vertical_coordinate: VCRS WKT
        vertical_epsg: VCRS EPSG code
        filename: The name of the JSON file to create
        
    Raises:
        ElevationAPIError: If file write fails
    """
    data = {
        "Elevation": elevation,
        "Shortname": shortname,
        "VCRS_WKT": vertical_coordinate,
        "VCRS_EPSG": vertical_epsg,
        "Unit": "Meters"
    }

    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        raise ElevationAPIError(f"Error writing to {filename}: {e}")


def getElev(short: str, lon: str, lat: str, json_file: str = DEFAULT_JSON_FILE) -> Tuple[str, str, str, str]:
    """
    Main module which gets the elevation for a given lat lon.
    
    Args:
        short: Dataset shortname
        lon: Longitude
        lat: Latitude
        json_file: Path to JSON metadata file
        
    Returns:
        Tuple of (short_name, elevation, vertical_coordinate, vertical_epsg)
    """
    # Validate coordinates first
    validate_coordinates(lon, lat)
    
    # Get dataset info from JSON
    short_name, vertical_coordinate, vertical_epsg, s3_url = get_metadata_from_json(short, json_file)
    
    # Run gdallocationinfo
    try:
        output = run_gdallocationinfo(s3_url, lon, lat)
    except ElevationAPIError as e:
        # If gdallocationinfo fails, it's likely because the point is outside
        # the dataset bounds (e.g., querying REMA for a point outside Antarctica)
        # Return NoData value instead of raising an error
        output = "-9999"
    
    # Check for NoData values (including floating-point variants)
    if is_nodata_value(output):
        output_format = "-9999"
    else:
        try:
            # Try to format as float to validate it's a number
            output_format = str(float(output))
        except ValueError:
            output_format = "-9999"
               
    return short_name, output_format, vertical_coordinate, vertical_epsg


def test(lon: str, lat: str, json_file: str = DEFAULT_JSON_FILE) -> List[str]:
    """
    Testing module. Gets elevations for ALL global/regional datasets
    for a given lat/lon.
    
    Args:
        lon: Longitude
        lat: Latitude
        json_file: Path to JSON metadata file
        
    Returns:
        List of formatted result strings
    """
    # Validate coordinates first
    validate_coordinates(lon, lat)
    
    # Get list of shortnames from JSON
    try:
        with open(json_file, 'r') as f:
            metadata = json.load(f)
        # Get unique shortnames from JSON
        shortnames = list(set(item['short_name'] for item in metadata))
    except Exception as e:
        raise ElevationAPIError(f"Error loading shortnames from JSON: {e}")

    final_output = []
    
    for short in shortnames:
        try:
            short_name, vertical_coordinate, vertical_epsg, s3_url = get_metadata_from_json(short, json_file)
            
            try:
                out = run_gdallocationinfo(s3_url, lon, lat)
            except ElevationAPIError:
                # Point is outside dataset bounds - return NoData
                out = "-9999"
            
            # Check if it is NoData (including floating-point variants)
            if is_nodata_value(out):
                output_format = "-9999"
            else:
                try:
                    output_format = str(float(out))
                except ValueError:
                    output_format = "-9999"
            
            result = (f"Elevation for {short_name}: {output_format} meters "
                     f"relative to: {vertical_coordinate} [EPSG:{vertical_epsg}]")
            final_output.append(result)
            
        except ElevationAPIError as e:
            # Other errors (e.g., missing dataset)
            final_output.append(f"Error for {short}: {str(e)}")
       
    return final_output


def parse_arguments():
    """
    Parse command line arguments.
    
    Returns:
        Namespace object with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Get elevation for a point from global/regional datasets.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Simple mode (COP30 default):
    python PointElevationAPI.py -104.9963 39.7471
  
  Specific dataset:
    python PointElevationAPI.py USGS30m -104.9963 39.7471
  
  Test mode (all datasets):
    python PointElevationAPI.py test -104.9963 39.7471
  
  Custom JSON file:
    python PointElevationAPI.py --jsonFile my_metadata.json USGS30m -104.9963 39.7471
        """
    )
    
    parser.add_argument('--jsonFile', type=str, default=DEFAULT_JSON_FILE,
                       help=f'Path to JSON metadata file (default: {DEFAULT_JSON_FILE})')
    parser.add_argument('args', nargs='+',
                       help='Either [lon lat] or [shortname lon lat] or [test lon lat]')
    
    return parser.parse_args()


def main():
    """Main entry point for the script"""
    try:
        args = parse_arguments()
        
        # Parse positional arguments
        if len(args.args) == 2:
            # Simple mode - use COP30 as default
            shortname = "COP30"
            lon = args.args[0]
            lat = args.args[1]
            test_mode = False
            
        elif len(args.args) == 3:
            if args.args[0].lower() == "test":
                # Test mode
                test_mode = True
                lon = args.args[1]
                lat = args.args[2]
            else:
                # Specific dataset mode
                shortname = args.args[0]
                lon = args.args[1]
                lat = args.args[2]
                test_mode = False
        else:
            print("Error: Invalid number of arguments")
            print("\nUsage:")
            print("  Simple mode: python PointElevationAPI.py [--jsonFile FILE] <lon> <lat>")
            print("  Specific dataset: python PointElevationAPI.py [--jsonFile FILE] <shortname> <lon> <lat>")
            print("  Test mode: python PointElevationAPI.py [--jsonFile FILE] test <lon> <lat>")
            sys.exit(1)
        
        # Execute based on mode
        if test_mode:
            print("Running tests...")
            results = test(lon, lat, json_file=args.jsonFile)
            for result in results:  
                print(result)
        else:
            short_name, elevation, vertical_coordinate, vertical_epsg = getElev(
                shortname, lon, lat, json_file=args.jsonFile
            )
            wkt = get_wkt(vertical_epsg)
            
            print(f"Elevation for {short_name}: {elevation} meters relative to: "
                  f"{vertical_coordinate} [EPSG:{vertical_epsg}]")
            write_to_json(elevation, short_name, wkt, vertical_epsg)
            
    except ElevationAPIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()