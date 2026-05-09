class DatasetManager:
    def __init__(self, client):
        self.client = client

    def list(self, page=1, page_size=10, search=None):
        """
        List available datasets.
        """
        params = {
            "page": page,
            "pageSize": page_size,
        }
        if search:
            params["searchQuery"] = search
            
        response = self.client.get("/datasets", params=params)
        
        # Based on DatasetsApiResponse, datasets are in the 'datasets' field
        if isinstance(response, dict) and "datasets" in response:
            return response["datasets"]
        return response

    def get(self, dataset_id):
        """
        Get detailed information about a single dataset.
        """
        return self.client.get(f"/datasets/{dataset_id}")

    def upload(self, file_path, name, data_store_id, **kwargs):
        """
        Upload a geospatial file and create a new dataset.
        This operation is asynchronous and returns a TaskReference.
        """
        # Note: Implement actual multipart upload logic here
        endpoint = "/datasets/upload" 
        # ... logic to handle file upload ...
        pass
