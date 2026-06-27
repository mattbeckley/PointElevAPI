#!/usr/bin/env python
"""
Integration tests for PointElevationAPI
Compares results against opentopodata.org API

Usage: python integration_tests.py
"""

import json
import os
import sys
import requests
from typing import Dict, List, Optional
from datetime import datetime
import pdb

# Service configuration
#OLD Service URL
#SERVICE_BASE_URL = "https://ot-beta.sdsc.edu/API/v1/elevation"
SERVICE_BASE_URL = "https://ot-portal3.sdsc.edu/API/v1/elevation"

_key_file = os.path.join(os.path.dirname(__file__), 'ot.api_key')
with open(_key_file) as _f:
    API_KEY = _f.read().strip()

# Test locations mapped to opentopodata datasets
TEST_LOCATIONS = {
    'denver': {
        'lon': '-104.9903',
        'lat': '39.7392',
        'tolerance': 20,
        'description': 'Denver, Colorado',
        'opentopodata_dataset': 'ned10m'  # CONUS
    },
    'death_valley': {
        'lon': '-116.8170',
        'lat': '36.2347',
        'tolerance': 20,
        'description': 'Death Valley, California',
        'opentopodata_dataset': 'ned10m'  # CONUS
    },
    'sea_level': {
        'lon': '-118.4000',
        'lat': '33.7000',
        'tolerance': 20,
        'description': 'Los Angeles coast',
        'opentopodata_dataset': 'ned10m'  # CONUS
    },
    'NZ_NorthIsland': {
        'lon': '174.76417',
        'lat': '-36.87972',
        'tolerance': 20,
        'description': 'Mount Eden, New Zealand',
        'opentopodata_dataset': 'nzdem8m'  # New Zealand
    },
    'NZ_SouthIsland': {
        'lon': '172.72694',
        'lat': '-43.59056',
        'tolerance': 20,
        'description': 'Mount Pleasant, New Zealand',
        'opentopodata_dataset': 'nzdem8m'  # New Zealand
    },
    'Europe': {
        'lon': '6.15444',
        'lat': '46.20556',
        'tolerance': 20,
        'description': 'Geneva, Switzerland',
        'opentopodata_dataset': 'eudem25m'  # Europe
    },
    'everest': {
        'lon': '86.9250',
        'lat': '27.9881',
        'tolerance': 200,
        'description': 'Mt. Everest',
        'opentopodata_dataset': 'mapzen'  # Global
    },
    'Vostok': {
        'lon': '106.8340',
        'lat': '-78.4645',
        'tolerance': 50,
        'description': 'Antarctica - Vostok Station',
        'opentopodata_dataset': 'mapzen'  # Global
    },
    'Summit': {
        'lon': '-38.5',
        'lat': '72.58',
        'tolerance': 50,
        'description': 'Greenland - Summit Station',
        'opentopodata_dataset': 'mapzen'  # Global
    },
    'Brazil': {
        'lon': '-48.6700',
        'lat': '-28.2400',
        'tolerance': 20,
        'description': 'Imbituba, Santa Catarina',
        'opentopodata_dataset': 'mapzen'  # Global
    }
}

# Datasets to test
TEST_DATASETS = ['GEBCOSubIceTopo', 'GEBCOIceTopo', 'USGS30m', 'USGS10m',       'REMA2m',
                 'REMA10m', 'REMA32m', 'ArcticDEM32m',
                 'ArcticDEM10m', 'ArcticDEM2m', 'GEDI_L3', 'EU_DTM', 'COP30', 'COP90', 'NASADEM', 'SRTM15Plus', 'AW3D30',
                 'AW3D30_E', 'SRTM_GL3', 'SRTM_GL1', 'SRTM_GL1_Ellip', 'CA_MRDEM', 'LINZ1m_DSM', 'LINZ1m_DTM', 'ANADEM','GEDTM30']


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'


class Logger:
    """Simple logger that writes to both console and file"""
    def __init__(self, log_file):
        self.log_file = log_file
        self.file_handle = open(log_file, 'w', encoding='utf-8')

    def write(self, text, to_file_only=False):
        """Write text to console and file"""
        if not to_file_only:
            print(text, end='')

        # Strip ANSI color codes for file output
        clean_text = text
        for color in [Colors.GREEN, Colors.RED, Colors.YELLOW, Colors.BLUE, Colors.END, Colors.BOLD]:
            clean_text = clean_text.replace(color, '')

        self.file_handle.write(clean_text)
        self.file_handle.flush()

    def print(self, text=''):
        """Print with newline"""
        self.write(text + '\n')

    def close(self):
        """Close the log file"""
        self.file_handle.close()


# Global logger instance
logger = None


def print_header(text: str):
    """Print a formatted header"""
    logger.print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    logger.print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    logger.print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")


def print_success(text: str):
    """Print success message"""
    logger.print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text: str):
    """Print error message"""
    logger.print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message"""
    logger.print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def call_elevation_service(lon: str, lat: str, dataset: str = 'COP30') -> requests.Response:
    """Call the elevation service and return the raw Response object."""
    params = {
        'longitude': lon,
        'latitude': lat,
        'dataset': dataset,
        'API_Key': API_KEY,
    }
    return requests.get(SERVICE_BASE_URL, params=params, timeout=30)


def get_opentopodata_elevation(lat: str, lon: str, dataset: str) -> Optional[float]:
    """
    Query opentopodata.org API for elevation at given coordinates

    Args:
        lat: Latitude as string
        lon: Longitude as string
        dataset: OpenTopoData dataset name (ned10m, eudem25m, nzdem8m, mapzen)

    Returns:
        Elevation in meters, or None if query failed
    """
    # OpenTopoData API uses lat,lon order (not lon,lat)
    url = f"https://api.opentopodata.org/v1/{dataset}?locations={lat},{lon}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data.get('status') == 'OK' and data.get('results'):
            elevation = data['results'][0].get('elevation')
            if elevation is not None:
                return float(elevation)

        logger.print(f"  OpenTopoData API returned unexpected response: {data}")
        return None

    except requests.exceptions.Timeout:
        logger.print(f"  OpenTopoData API timeout for {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.print(f"  OpenTopoData API error: {e}")
        return None
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.print(f"  Error parsing OpenTopoData response: {e}")
        return None


def test_simple_mode(location_key: str, location_data: Dict) -> bool:
    """Test simple mode (default COP30)"""
    lon = location_data['lon']
    lat = location_data['lat']
    desc = location_data['description']
    opentopodata_dataset = location_data['opentopodata_dataset']

    logger.print(f"Testing simple mode for {desc} ({lon}, {lat})...")

    # Get reference elevation from opentopodata
    logger.print(f"  Querying OpenTopoData ({opentopodata_dataset})...")
    reference_elevation = get_opentopodata_elevation(lat, lon, opentopodata_dataset)

    if reference_elevation is None:
        print_warning(f"Could not get reference elevation from OpenTopoData, skipping comparison")

    try:
        response = call_elevation_service(lon, lat)

        if response.status_code != 200:
            print_error(f"Service returned HTTP {response.status_code}")
            logger.print(f"  Response: {response.text}")
            return False

        data = response.json()

        # Validate JSON structure
        required_keys = ['Elevation', 'VCRS_WKT', 'VCRS_EPSG', 'Unit','Reference Dataset']
        for key in required_keys:
            if key not in data:
                print_error(f"Missing key in JSON: {key}")
                return False

        # Check elevation value
        try:
            elevation = float(data['Elevation'])

            if reference_elevation is not None:
                tolerance = location_data['tolerance']
                diff = abs(elevation - reference_elevation)

                if diff <= tolerance:
                    print_success(f"Elevation {elevation}m matches OpenTopoData {reference_elevation}m (diff: {diff:.2f}m)")
                else:
                    print_warning(f"Elevation {elevation}m differs from OpenTopoData {reference_elevation}m (diff: {diff:.2f}m, tolerance: ±{tolerance}m)")
            else:
                print_success(f"Elevation returned: {elevation}m (no reference available)")

        except ValueError:
            if str(data['Elevation']) == '-9999':
                print_warning(f"NoData value returned for {desc}")
            else:
                print_error(f"Invalid elevation value: {data['Elevation']}")
                return False

        print_success(f"Simple mode test passed for {desc}")
        return True

    except requests.exceptions.Timeout:
        print_error("Service request timed out")
        return False
    except (json.JSONDecodeError, ValueError) as e:
        print_error(f"Error parsing service response: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


def test_specific_dataset(dataset: str, location_key: str, location_data: Dict) -> bool:
    """Test with specific dataset"""
    lon = location_data['lon']
    lat = location_data['lat']
    desc = location_data['description']
    opentopodata_dataset = location_data['opentopodata_dataset']

    logger.print(f"Testing {dataset} for {desc} ({lon}, {lat})...")

    # Get reference elevation from opentopodata
    reference_elevation = get_opentopodata_elevation(lat, lon, opentopodata_dataset)

    try:
        response = call_elevation_service(lon, lat, dataset)

        if response.status_code != 200:
            print_warning(f"Dataset {dataset} failed (may not cover this location) — HTTP {response.status_code}")
            return True  # Don't count as failure - dataset may not cover area

        data = response.json()

        if data.get('Reference Dataset') != dataset:
            print_error(f"JSON shortname mismatch: {data.get('Shortname')} != {dataset}")
            return False

        # Check elevation value and compare to reference
        try:
            elevation = float(data['Elevation'])

            if reference_elevation is not None:
                tolerance = location_data['tolerance']
                diff = abs(elevation - reference_elevation)

                if diff <= tolerance:
                    print_success(f"{dataset}: Elevation {elevation}m matches OpenTopoData {reference_elevation}m (diff: {diff:.2f}m)")
                else:
                    print_warning(f"{dataset}: Elevation {elevation}m differs from OpenTopoData {reference_elevation}m (diff: {diff:.2f}m, tolerance: ±{tolerance}m)")
            else:
                print_success(f"{dataset}: Elevation returned: {elevation}m (no reference available)")

        except ValueError:
            if str(data.get('Elevation')) == '-9999':
                print_warning(f"{dataset}: NoData value returned for {desc}")
            else:
                print_error(f"{dataset}: Invalid elevation value: {data.get('Elevation')}")
                return False

        print_success(f"{dataset} test passed for {desc}")
        return True

    except requests.exceptions.Timeout:
        print_error("Service request timed out")
        return False
    except (json.JSONDecodeError, ValueError) as e:
        print_error(f"Error parsing service response: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


def test_invalid_inputs() -> bool:
    """Test error handling with invalid inputs"""
    print_header("Testing Error Handling")

    test_cases = [
        {
            'lon': '999',
            'lat': '39.7471',
            'dataset': 'COP30',
            'desc': 'Invalid longitude (out of range)',
            'should_fail': True
        },
        {
            'lon': '-104.9963',
            'lat': '100',
            'dataset': 'COP30',
            'desc': 'Invalid latitude (out of range)',
            'should_fail': True
        },
        {
            'lon': '-104.9963',
            'lat': 'ABC',
            'dataset': 'COP30',
            'desc': 'Text for latitude',
            'should_fail': True
        },
        {
            'lon': 'abc',
            'lat': '39.7471',
            'dataset': 'COP30',
            'desc': 'Non-numeric longitude',
            'should_fail': True
        },
        {
            'lon': '-104.9963',
            'lat': '39.7471',
            'dataset': 'INVALID_DATASET',
            'desc': 'Non-existent dataset',
            'should_fail': True
        }
    ]

    all_passed = True

    for test_case in test_cases:
        desc = test_case['desc']
        should_fail = test_case['should_fail']

        logger.print(f"Testing: {desc}...")

        try:
            response = call_elevation_service(
                test_case['lon'], test_case['lat'], test_case['dataset']
            )

            # Treat a non-200 status or an error field in the JSON body as a failure
            service_failed = response.status_code != 200
            if not service_failed:
                try:
                    body = response.json()
                    service_failed = 'error' in body or str(body.get('Elevation')) == '-9999'
                except (json.JSONDecodeError, ValueError):
                    service_failed = True

            if should_fail:
                if service_failed:
                    print_success(f"Correctly rejected: {desc}")
                else:
                    print_error(f"Should have failed but didn't: {desc}")
                    all_passed = False
            else:
                if not service_failed:
                    print_success(f"Correctly accepted: {desc}")
                else:
                    print_error(f"Should have succeeded: {desc}")
                    all_passed = False

        except Exception as e:
            print_error(f"Unexpected error testing {desc}: {e}")
            all_passed = False

    return all_passed


def test_all_datasets_single_location() -> bool:
    """Test every dataset for a single well-known location and report results."""
    print_header("Testing All Datasets (Single Location)")

    lon = '-104.9963'
    lat = '39.7471'

    logger.print(f"Querying all datasets for ({lon}, {lat})...\n")

    results_count = 0
    nodata_count = 0
    error_count = 0

    for dataset in TEST_DATASETS:
        try:
            response = call_elevation_service(lon, lat, dataset)

            if response.status_code != 200:
                print_warning(f"{dataset}: HTTP {response.status_code} (dataset may not cover this location)")
                nodata_count += 1
                continue

            data = response.json()
            elev_raw = data.get('Elevation')

            try:
                elevation = float(elev_raw)
                epsg = data.get('VCRS_EPSG', 'unknown')
                unit = data.get('Unit', 'unknown')
                print_success(f"{dataset}: {elevation} {unit}  (EPSG:{epsg})")
                results_count += 1
            except (TypeError, ValueError):
                if str(elev_raw) == '-9999':
                    print_warning(f"{dataset}: NoData (-9999)")
                    nodata_count += 1
                else:
                    print_error(f"{dataset}: Unexpected elevation value: {elev_raw}")
                    error_count += 1

        except requests.exceptions.Timeout:
            print_error(f"{dataset}: Request timed out")
            error_count += 1
        except Exception as e:
            print_error(f"{dataset}: {e}")
            error_count += 1

    logger.print(f"\nResults: {results_count} elevation values, {nodata_count} no-data/skipped, {error_count} errors")

    if error_count > 0:
        print_warning(f"All-datasets test completed with {error_count} error(s)")
    else:
        print_success("All-datasets test completed successfully")

    return error_count == 0


def main():
    """Run all integration tests"""
    global logger

    # Create timestamped log file
    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(logs_dir, f"outputlog_{timestamp}.log")

    # Initialize logger
    logger = Logger(log_filename)

    try:
        logger.print(f"Log file: {log_filename}\n")
        logger.print(f"Service URL: {SERVICE_BASE_URL}\n")

        print_header("Point Elevation API Integration Tests")
        logger.print("Comparing against OpenTopoData API (opentopodata.org)\n")

        results = {
            'simple_mode': [],
            'specific_datasets': [],
            'error_handling': None,
            'all_datasets': None
        }

        # Test simple mode (COP30) for all locations
        print_header("Testing Simple Mode (Default COP30)")
        for loc_key, loc_data in TEST_LOCATIONS.items():
            result = test_simple_mode(loc_key, loc_data)
            results['simple_mode'].append((loc_key, result))

        # Test specific datasets
        print_header("Testing Specific Datasets")
        for dataset in TEST_DATASETS:
            for loc_key, loc_data in list(TEST_LOCATIONS.items())[:2]:  # Test first 2 locations
                result = test_specific_dataset(dataset, loc_key, loc_data)
                results['specific_datasets'].append((f"{dataset}_{loc_key}", result))

        # Test error handling
        results['error_handling'] = test_invalid_inputs()

        # Test all datasets for a single location
        results['all_datasets'] = test_all_datasets_single_location()

        # Print summary
        print_header("Test Summary")

        simple_passed = sum(1 for _, r in results['simple_mode'] if r)
        simple_total = len(results['simple_mode'])
        logger.print(f"Simple Mode: {simple_passed}/{simple_total} passed")

        dataset_passed = sum(1 for _, r in results['specific_datasets'] if r)
        dataset_total = len(results['specific_datasets'])
        logger.print(f"Specific Datasets: {dataset_passed}/{dataset_total} passed")

        if results['error_handling']:
            print_success("Error Handling: Passed")
        else:
            print_error("Error Handling: Failed")

        if results['all_datasets']:
            print_success("All-Datasets Test: Passed")
        else:
            print_error("All-Datasets Test: Failed")

        # Overall result
        total_passed = simple_passed + dataset_passed + \
                       (1 if results['error_handling'] else 0) + \
                       (1 if results['all_datasets'] else 0)
        total_tests = simple_total + dataset_total + 2

        logger.print(f"\n{Colors.BOLD}Overall: {total_passed}/{total_tests} tests passed{Colors.END}")

        if total_passed == total_tests:
            logger.print(f"{Colors.GREEN}{Colors.BOLD}All tests passed! ✓{Colors.END}")
            return_code = 0
        else:
            logger.print(f"{Colors.YELLOW}{Colors.BOLD}Some tests failed{Colors.END}")
            return_code = 1

        logger.print(f"\nLog saved to: {log_filename}")

        return return_code

    finally:
        if logger:
            logger.close()


if __name__ == '__main__':
    sys.exit(main())
