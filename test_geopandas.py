import os
import sys
from dotenv import load_dotenv
from geopack_sdk import GeopackClient

# Load configuration from .env file if it exists
load_dotenv()

def main():
    api_url = os.getenv("GEOPACK_API_URL", "http://localhost:3000/api")
    username = os.getenv("GEOPACK_USERNAME", "admin")
    password = os.getenv("GEOPACK_PASSWORD", "password")
    
    # Use the dataset ID created in the previous upload test
    dataset_id = os.getenv("TEST_DATASET_ID")
    if not dataset_id:
        print("! TEST_DATASET_ID not set. Trying to find the latest dataset...")

    try:
        # 1. Initialize Client
        client = GeopackClient(base_url=api_url)

        # 2. Authenticate
        print("\n[1/3] Logging in...")
        client.auth.login(username=username, password=password)
        print("✓ Login successful!")

        # 3. Resolve Dataset ID if not provided
        if not dataset_id:
            datasets = client.datasets.list(page_size=1)
            if not datasets:
                print("✖ No datasets found in the portal.")
                return
            dataset_id = datasets[0]['id']
            dataset_name = datasets[0]['name']
            print(f"✓ Found latest dataset: {dataset_name} (ID: {dataset_id})")
        else:
            dataset_id = int(dataset_id)
            print(f"✓ Using Dataset ID: {dataset_id}")

        # 4. Fetch as GeoDataFrame
        print(f"\n[2/3] Fetching dataset {dataset_id} as GeoDataFrame...")
        try:
            gdf = client.datasets.to_geodataframe(dataset_id, limit=50)
            
            print("\n[3/3] Verification Results:")
            print(f"✓ Type: {type(gdf)}")
            print(f"✓ Row Count: {len(gdf)}")
            print(f"✓ Columns: {gdf.columns.tolist()}")
            print(f"✓ CRS: {gdf.crs}")
            
            if len(gdf) > 0:
                print("\n--- First 5 rows head ---")
                # Drop geometry for clean text printing
                print(gdf.drop(columns='geometry').head())
            
            print("\n--- GeoPandas Integration Successful ---")

        except ImportError:
            print("\n✖ GeoPandas is not installed in your environment.")
            print("  Please run: pip install geopandas")
        except Exception as e:
            print(f"\n✖ Failed to fetch features: {str(e)}")

    except Exception as e:
        print(f"\n✖ SDK Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
