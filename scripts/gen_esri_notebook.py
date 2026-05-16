"""One-off generator for notebooks/06_ESRI_Geodatabase_Manager.ipynb"""
import nbformat as nbf
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

nb = new_notebook()
nb.cells = [
    new_markdown_cell(
        "# Geopack SDK: ESRI Geodatabase Manager\n\n"
        "Python equivalent of the portal **ESRI Geodatabase Manager** dialog "
        "(`EsriGeodatabaseDataStoreManager.vue`) for a datastore such as "
        "**GDB_Golbahar** (ID 31).\n\n"
        "| Portal action | SDK call |\n"
        "|---------------|----------|\n"
        "| Refresh Discovery | `discover_esri_datasets(id)` |\n"
        "| Register (one) | `register_esri_datasets(id, wg_id, dataset_names=[name])` |\n"
        "| Register All | `register_esri_datasets(id, wg_id)` |\n"
        "| Update All Schemas | `update_esri_dataset_schemas(id)` |\n"
        "| Delete All Datasets | `delete_all_esri_datasets(id, confirm=True)` |\n"
        "| Status / counts | `get_esri_geodatabase_info(id)` |\n\n"
        "`.env`: `GEOPACK_*`, `TEST_ESRI_DATASTORE_ID`, `TEST_WORKGROUP_ID`."
    ),
    new_code_cell(
        "%load_ext autoreload\n"
        "%autoreload 2\n\n"
        "import os\n"
        "import sys\n"
        "from dotenv import load_dotenv\n\n"
        'source_path = os.path.abspath(os.path.join(os.getcwd(), "..", "src"))\n'
        "if os.path.exists(source_path) and source_path not in sys.path:\n"
        "    sys.path.insert(0, source_path)\n\n"
        "from geopack_sdk import GeopackClient\n"
        "from geopack_sdk.esri_geodatabase import (\n"
        "    filter_datasets,\n"
        "    group_datasets_by_feature_dataset,\n"
        "    print_discovery_table,\n"
        "    print_registration_summary,\n"
        "    print_schema_update_summary,\n"
        ")\n\n"
        "load_dotenv()\n"
        'client = GeopackClient(base_url=os.getenv("GEOPACK_API_URL", "http://localhost:3000/api"))\n'
        "client.auth.login(\n"
        '    os.getenv("GEOPACK_USERNAME", "admin"),\n'
        '    os.getenv("GEOPACK_PASSWORD", "password"),\n'
        ")\n"
        'print("Logged in as", client.users.me().userName)'
    ),
    new_markdown_cell("## 1. Select ESRI datastore (like opening the manager for ID 31)"),
    new_code_cell(
        'ESRI_DATASTORE_ID = int(os.getenv("TEST_ESRI_DATASTORE_ID", "31"))\n'
        'WORKGROUP_ID = int(os.getenv("TEST_WORKGROUP_ID", "1"))\n\n'
        "store = client.datastores.get(ESRI_DATASTORE_ID)\n"
        'print(f"Datastore #{store.id}: {store.name} ({store.type}) — {store.status}")'
    ),
    new_markdown_cell("## 2. Geodatabase info"),
    new_code_cell(
        "info = client.datastores.get_esri_geodatabase_info(ESRI_DATASTORE_ID)\n"
        "gdb = info.data.geodatabase\n"
        'print("Version:", gdb.version)\n'
        'print("Feature classes:", gdb.featureClassCount, "| Tables:", gdb.tableCount)'
    ),
    new_markdown_cell("## 3. Refresh discovery"),
    new_code_cell(
        "discovery = client.datastores.discover_esri_datasets(ESRI_DATASTORE_ID)\n"
        "print_discovery_table(discovery, max_rows_per_category=8)"
    ),
    new_markdown_cell("## 4. Search & browse by feature dataset"),
    new_code_cell(
        'SEARCH = ""  # e.g. "BTS" or "Communication"\n'
        "filtered = filter_datasets(discovery.data, SEARCH)\n"
        "for cat in group_datasets_by_feature_dataset(filtered)[:5]:\n"
        '    print(f"{cat.name} ({len(cat.datasets)}) — {cat.category_type}")'
    ),
    new_markdown_cell(
        "## 5. Register one dataset (portal **Register** button)\n\n"
        "Uncomment and set a name from the discovery table (`dataset.name`)."
    ),
    new_code_cell(
        '# SINGLE_NAME = "GDB_Golbahar.DBO.BTS"\n'
        "# reg = client.datastores.register_esri_datasets(\n"
        "#     ESRI_DATASTORE_ID,\n"
        "#     workgroup_id=WORKGROUP_ID,\n"
        "#     dataset_names=[SINGLE_NAME],\n"
        "# )\n"
        "# print_registration_summary(reg)\n"
        "# discovery = client.datastores.discover_esri_datasets(ESRI_DATASTORE_ID)"
    ),
    new_markdown_cell("## 6. Register all — use with care"),
    new_code_cell(
        "# RUN_REGISTER_ALL = False\n"
        "# if RUN_REGISTER_ALL:\n"
        "#     reg_all = client.datastores.register_esri_datasets(\n"
        "#         ESRI_DATASTORE_ID, workgroup_id=WORKGROUP_ID\n"
        "#     )\n"
        "#     print_registration_summary(reg_all)"
    ),
    new_markdown_cell("## 7. Update schemas / delete all (destructive)"),
    new_code_cell(
        "# schema = client.datastores.update_esri_dataset_schemas(\n"
        "#     ESRI_DATASTORE_ID, force_update=True\n"
        "# )\n"
        "# print_schema_update_summary(schema)\n\n"
        "# deleted = client.datastores.delete_all_esri_datasets(\n"
        "#     ESRI_DATASTORE_ID, confirm=True\n"
        "# )\n"
        '# print(len(deleted.data.deleted), "deleted")'
    ),
    new_markdown_cell("## 8. CLI test\n\n`python test_esri_datastore.py`"),
]

out = "notebooks/06_ESRI_Geodatabase_Manager.ipynb"
with open(out, "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print("wrote", out)
