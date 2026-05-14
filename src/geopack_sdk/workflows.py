import json
import logging
from typing import Any, Dict, List, Optional, Union, Literal
from .models import (
    Workflow,
    WorkflowParameter,
    WorkflowRun,
)

logger = logging.getLogger(__name__)

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
    ) -> List[Workflow]:
        """List workflow definitions with type-safe response.

        REST API: `GET /api/workflows`

        Returns:
            List[Workflow]: Validated workflow models
        """
        params = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
            **(filters or {})
        }
        if search_query:
            params["q"] = search_query

        response_data = self.client.get(self.base_url, params=params)
        items = response_data.get("items", [])
        
        # Validate each item as Workflow
        if isinstance(items, list):
            return [Workflow(**item) for item in items]
        return []

    def get(self, workflow_id: int) -> Workflow:
        """Get a single workflow definition by ID with type-safe response.

        REST API: `GET /api/workflows/:id`

        Args:
            workflow_id: ID of the workflow to fetch

        Returns:
            Workflow: Validated workflow model
        """
        response_data = self.client.get(f"{self.base_url}/{workflow_id}")
        return Workflow(**response_data)

    def extract_params(self, workflow: Union[Workflow, Dict[str, Any]]) -> List[WorkflowParameter]:
        """Extract runtime parameters from the workflow graph definition with type-safe response.

        This mimics the logic in WorkflowRunParametersForm.vue.

        Args:
            workflow: Workflow model or dictionary containing graphJson

        Returns:
            List[WorkflowParameter]: Validated workflow parameter models
        """
        # Convert to dict if it's a Pydantic model
        if isinstance(workflow, Workflow):
            workflow_dict = workflow.model_dump()
        else:
            workflow_dict = workflow
        
        graph = workflow_dict.get('graphJson', {})
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
                
                param_dict = {
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
                }
                
                # Validate as WorkflowParameter
                items.append(WorkflowParameter(**param_dict))
        
        # Sort by Y position (Top to Bottom) then X (Left to Right) as per frontend layout logic
        if items:
            items.sort(key=lambda x: (nodes[0].get('position', {}).get('y', 0), nodes[0].get('position', {}).get('x', 0)))
        
        return items

    def get_operations(self) -> List[Dict[str, Any]]:
        """Get the manifest of all available workflow operations (OGR, GDAL, etc.).
        
        REST API: `GET /api/workflows/operations`
        """
        response = self.client.get(f"{self.base_url}/operations")
        return response.get("items", [])

    def create(self, payload: Dict[str, Any]) -> Workflow:
        """Create a new workflow definition with type-safe response.

        REST API: `POST /api/workflows`

        Args:
            payload: Workflow definition data

        Returns:
            Workflow: Validated workflow model
        """
        response_data = self.client.post(self.base_url, json=payload)
        return Workflow(**response_data)

    def update(self, workflow_id: int, payload: Dict[str, Any]) -> Workflow:
        """Update an existing workflow definition with type-safe response.

        REST API: `PUT /api/workflows/:id`

        Args:
            workflow_id: ID of the workflow to update
            payload: Updated workflow definition data

        Returns:
            Workflow: Validated workflow model
        """
        response_data = self.client.put(f"{self.base_url}/{workflow_id}", json=payload)
        return Workflow(**response_data)

    def delete(self, workflow_id: int) -> bool:
        """Delete a workflow definition.
        
        REST API: `DELETE /api/workflows/:id`
        """
        self.client.delete(f"{self.base_url}/{workflow_id}")
        return True
