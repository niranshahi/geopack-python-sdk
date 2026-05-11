import json
from typing import Any, Dict, List, Optional, Union

class WorkflowManager:
    """Manager for Workflow Definitions and Operations."""

    def __init__(self, client):
        self.client = client
        self.base_url = "/workflows"

    def list(
        self,
        page: int = 1,
        page_size: int = 10,
        search_query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """List workflow definitions.
        
        REST API: `GET /api/workflows`
        """
        params = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
            **(filters or {})
        }
        if search_query:
            params["q"] = search_query

        response = self.client.get(self.base_url, params=params)
        return response.get("items", [])

    def get(self, workflow_id: int) -> Dict[str, Any]:
        """Get a single workflow definition by ID.
        
        REST API: `GET /api/workflows/:id`
        """
        return self.client.get(f"{self.base_url}/{workflow_id}")

    def extract_params(self, workflow: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract runtime parameters from the workflow graph definition.
        
        This mimics the logic in WorkflowRunParametersForm.vue.
        """
        graph = workflow.get('graphJson', {})
        if not graph:
            return []
            
        nodes = graph.get('nodes', [])
        if not isinstance(nodes, list):
            return []
            
        items = []
        for n in nodes:
            kind = str(n.get('kind') or n.get('data', {}).get('kind', ''))
            type_name = str(n.get('type') or '')
            
            # Match logic from WorkflowRunParametersForm.vue
            is_param = (
                kind == 'param' or 
                type_name in ['paramNode', 'geomParamNode', 'datasetSelectorParamNode', 'datasetFieldParamNode']
            )
            
            if is_param:
                config = n.get('config') or n.get('data', {}).get('config', {})
                key = str(config.get('key', ''))
                if not key:
                    continue
                
                param_type = 'dataset-field' if type_name == 'datasetFieldParamNode' else str(config.get('type', 'string'))
                
                items.append({
                    "key": key,
                    "type": param_type,
                    "description": config.get('description'),
                    "default": config.get('default'),
                    "required": not config.get('nullable', True),
                    "runVisibility": config.get('runVisibility', 'editable'),
                    # Additional metadata
                    "dataType": config.get('dataType'), # for dataset-selector
                    "geometryType": config.get('geometryType'), # for geom-param
                    "multiple": config.get('multiple', False)
                })
        
        # Sort by Y position (Top to Bottom) then X (Left to Right) as per frontend layout logic
        items.sort(key=lambda x: (nodes[0].get('position', {}).get('y', 0), nodes[0].get('position', {}).get('x', 0)))
        
        return items

    def get_operations(self) -> List[Dict[str, Any]]:
        """Get the manifest of all available workflow operations (OGR, GDAL, etc.).
        
        REST API: `GET /api/workflows/operations`
        """
        response = self.client.get(f"{self.base_url}/operations")
        return response.get("items", [])

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new workflow definition.
        
        REST API: `POST /api/workflows`
        """
        return self.client.post(self.base_url, json=payload)

    def update(self, workflow_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing workflow definition.
        
        REST API: `PUT /api/workflows/:id`
        """
        return self.client.put(f"{self.base_url}/{workflow_id}", json=payload)

    def delete(self, workflow_id: int) -> bool:
        """Delete a workflow definition.
        
        REST API: `DELETE /api/workflows/:id`
        """
        self.client.delete(f"{self.base_url}/{workflow_id}")
        return True
