# GLPI Asset MCP

Lightweight Python MCP server for GLPI asset management.

The first version is intentionally focused on your current scope:

- Query Linux/Windows VM assets from GLPI `Computer`
- Query network devices from GLPI `NetworkEquipment`
- Generate CSV/XLSX reports
- Use GLPI REST API as the source of truth

## Tools

| Tool | Purpose |
| --- | --- |
| `asset_search` | Search computer assets. Use `asset_type=linux/windows/computer`. |
| `asset_get` | Get one computer asset by GLPI id. |
| `asset_summary` | Return bounded sample counts for computers and network devices. |
| `network_device_search` | Search GLPI network equipment. |
| `network_device_get` | Get one network device by GLPI id. |
| `report_generate` | Export GLPI API results as CSV or XLSX. |
| `windows_software_report` | Count Windows computers and export installed software to XLSX. |
| `custom_asset_report` | Export any GLPI item type with user-selected fields. |
| `agent_health_check` | Find assets with stale or missing agent inventory/contact dates. |
| `glpi_raw_get` | Advanced raw read for any GLPI item type. |
| `asset_inventory_query` | Query Windows/Linux computers by text, OS, IP, or installed software. |
| `asset_full_details` | Return one normalized asset with software, IP/MAC, and storage. |
| `software_inventory_query` | Search installed software across Windows and Linux computers. |
| `asset_inventory_report` | Export normalized computer inventory with network, software, and storage summaries. |
| `network_device_report` | Export network equipment with IP, MAC, model, location, and port summaries. |
| `asset_field_catalog` | Discover real field paths exposed by the connected GLPI deployment. |

## Natural-language inventory queries

The Streamable HTTP server exposes normalized inventory tools intended for
questions from Open WebUI such as:

```text
List Linux machines that have nginx installed.
Show the IP, MAC, disks, and software for computer 42.
Which Windows computers have Java 8 installed?
Export all network devices in the Shanghai location to XLSX.
```

`asset_inventory_query` returns inline JSON data for chat answers. It accepts
`query`, `os_family`, `ip`, and `software` filters. `asset_full_details` returns
a single aggregated view. `asset_inventory_report` and
`network_device_report` also return the first 20 rows as an inline preview so
Open WebUI can answer even when the generated file lives in another container.

GLPI versions and plugins expose different nested field names. Call
`asset_field_catalog` with a representative asset ID to discover the paths
available in the current deployment before building a custom report.

## Compatibility

This MCP targets the GLPI REST API and should be compatible with GLPI 11.0.7 as long as the API is enabled and the API token/user token has permission to read the requested item types.

GLPI Agent v1.17-1 is not called directly by this MCP. The MCP reads the inventory results that GLPI stored after the agent reported. For agent health checks, use GLPI fields such as last inventory/contact/update dates.

Known practical note: GLPI 11.0.x and Agent 1.17 deployments may expose different field names for "last inventory" or "last contact" depending on native inventory, plugins, and saved fields. The health check therefore checks multiple candidate fields and lets you override them with `date_fields`.

## Custom reports

Use `custom_asset_report` when the user wants to choose columns dynamically.

Basic computer report:

```json
{
  "itemtype": "Computer",
  "format": "xlsx",
  "max_items": 3000,
  "fields": [
    {"path": "id", "label": "ID"},
    {"path": "name", "label": "Name"},
    {"path": "serial", "label": "Serial"},
    {"path": "locations_id", "label": "Location"},
    {"path": "date_mod", "label": "Updated"}
  ]
}
```

Network device report:

```json
{
  "itemtype": "NetworkEquipment",
  "format": "xlsx",
  "fields": [
    {"path": "name", "label": "Name"},
    {"path": "serial", "label": "Serial"},
    {"path": "manufacturers_id", "label": "Manufacturer"},
    {"path": "networkequipmentmodels_id", "label": "Model"},
    {"path": "locations_id", "label": "Location"},
    {"path": "date_mod", "label": "Updated"}
  ]
}
```

Expanded software report:

```json
{
  "itemtype": "Computer",
  "format": "xlsx",
  "max_items": 3000,
  "include_softwares": true,
  "expand_path": "softwares",
  "fields": [
    {"path": "item.name", "label": "Display name"},
    {"path": "item.version", "label": "Version"},
    {"path": "item.discovery_model", "label": "Discovery model"},
    {"path": "asset.name", "label": "Installed on"},
    {"path": "item.date_mod", "label": "Updated"}
  ]
}
```

Field paths use dot notation. Without `expand_path`, paths point to the GLPI item directly, for example `name` or `serial`. With `expand_path`, each row contains:

```text
asset = original GLPI item
item  = expanded child object
```

## Agent health check

Use `agent_health_check` to find assets whose GLPI Agent inventory/contact data is stale. By default, anything older than 30 days is marked `stale`, and assets without a usable date are marked `missing_agent_date`.

```json
{
  "itemtype": "Computer",
  "stale_days": 30,
  "max_items": 3000,
  "include_ok": false
}
```

The tool returns summary counts and creates an XLSX report with:

```text
Status
Asset ID
Asset name
Serial
UUID
Location
Last seen
Matched field
Age days
Threshold days
Updated
```

If your GLPI exposes a known custom field for agent contact time, pass it first:

```json
{
  "date_fields": ["last_contact", "last_inventory_update", "date_mod"]
}
```

## Windows software report

Use `windows_software_report` when you need to know how many Windows machines are currently in GLPI and export their installed software inventory.

The XLSX file contains these columns:

```text
Display name
Version
Discovery model
Installed on
Updated
```

Example MCP tool arguments:

```json
{
  "max_computers": 3000
}
```

The result includes:

```json
{
  "windows_computer_count": 1200,
  "software_row_count": 25000,
  "report": {
    "format": "xlsx",
    "path": "..."
  }
}
```

## Configuration

Copy `.env.example` and set environment variables:

```powershell
$env:GLPI_BASE_URL="https://glpi.example.com/apirest.php"
$env:GLPI_APP_TOKEN="your-app-token"
$env:GLPI_USER_TOKEN="your-user-token"
$env:GLPI_REPORTS_DIR="C:\path\to\reports"
```

You can also use username/password instead of `GLPI_USER_TOKEN`:

```powershell
$env:GLPI_USERNAME="api-user"
$env:GLPI_PASSWORD="api-password"
```

## Run

```powershell
python -m glpi_asset_mcp.server
```

In this Codex workspace, Python may be available at:

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m glpi_asset_mcp.server
```

## Docker

Build the image:

```bash
docker build -t glpi-asset-mcp:0.1.0 .
```

Podman users who want the Dockerfile `HEALTHCHECK` metadata preserved should
build with Docker image format:

```bash
podman build --format docker -t glpi-asset-mcp:0.1.0 .
```

The default OCI format ignores Dockerfile health-check metadata. This does not
prevent the MCP server from running, and Kubernetes uses its own probes.

Run the MCP Streamable HTTP server used by Open WebUI and Kubernetes:

```bash
docker run --rm -p 8000:8000 \
  -e GLPI_BASE_URL="https://glpi.example.com/apirest.php" \
  -e GLPI_APP_TOKEN="your-app-token" \
  -e GLPI_USER_TOKEN="your-user-token" \
  -v "$PWD/reports:/app/reports" \
  glpi-asset-mcp:0.1.0
```

Create the bind-mount directory first with `mkdir -p reports`. Replace every
example value with the real GLPI URL and tokens. The URL value must be a plain
URL such as `https://glpi.company.example/apirest.php`; do not paste Markdown
link syntax such as `[https://...](https://...)`.

The MCP endpoint is:

```text
http://localhost:8000/mcp
```

It uses the official MCP SDK's stateless Streamable HTTP transport with JSON
responses. Kubernetes and Docker health checks probe the TCP port so they do
not create MCP sessions.

The original stdio MCP server is still available for desktop MCP hosts:

```bash
python -m glpi_asset_mcp.server
```

## Kubernetes

Manifests are in `k8s/`.

Edit `k8s/secret.example.yaml` and replace the GLPI URL/token values, or create your own Secret named `glpi-asset-mcp-secret`.

Apply:

```bash
kubectl apply -k k8s/
```

Check status:

```bash
kubectl get pods -l app=glpi-asset-mcp
kubectl logs deploy/glpi-asset-mcp
```

Port-forward for testing:

```bash
kubectl port-forward svc/glpi-asset-mcp 8000:8000
```

Then configure an MCP client with `http://localhost:8000/mcp`.

Production note: Kubernetes runs the official Streamable HTTP transport
(`python -m glpi_asset_mcp.http_server`). The original stdio server remains
available for desktop MCP hosts.

## Open WebUI / MCP Host

Open WebUI 0.6.31 or newer can connect directly:

```text
Settings > Admin > Integrations > External Tool Servers
Type: MCP (Streamable HTTP)
URL: http://glpi-asset-mcp:8000/mcp
Auth: None (or configure authentication at your reverse proxy)
```

When Open WebUI and this server run in the same Docker or Kubernetes network,
use the service name instead of `localhost`. Do not expose the unauthenticated
MCP endpoint directly to the public Internet.

Configure your MCP host to run the server over stdio:

```json
{
  "mcpServers": {
    "glpi-asset": {
      "command": "python",
      "args": ["-m", "glpi_asset_mcp.server"],
      "env": {
        "GLPI_BASE_URL": "https://glpi.example.com/apirest.php",
        "GLPI_APP_TOKEN": "replace-with-app-token",
        "GLPI_USER_TOKEN": "replace-with-user-token",
        "GLPI_REPORTS_DIR": "reports"
      }
    }
  }
}
```

## Notes for 3000 VM scale

This MVP queries GLPI API directly. For production use with frequent reports, add an asset cache database:

```text
GLPI API -> sync worker -> PostgreSQL/MySQL asset_cache -> MCP tools
```

Keep writes through GLPI API. Use the cache database for reports, filters, and expensive summaries.
