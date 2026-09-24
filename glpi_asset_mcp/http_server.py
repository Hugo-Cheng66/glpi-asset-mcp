from __future__ import annotations

import os
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .server import McpServer as ToolService


service = ToolService()
mcp = MCPServer(
    "glpi-asset-mcp",
    description="Read GLPI assets and generate inventory reports.",
)


@mcp.tool(description="Search GLPI computer assets. Use asset_type linux/windows/computer for VMs and servers.")
def asset_search(
    asset_type: Literal["computer", "linux", "windows"] = "computer",
    query: str | None = None,
    limit: Annotated[int, Field(ge=1, le=500)] = 50,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    return service.asset_search(locals())


@mcp.tool(description="Get one GLPI computer asset by id.")
def asset_get(
    id: Annotated[int, Field(ge=1)],
    asset_type: Literal["computer", "linux", "windows"] = "computer",
) -> dict:
    return service.asset_get(locals())


@mcp.tool(description="Return a lightweight summary count from GLPI computers and network devices.")
def asset_summary(sample_limit: Annotated[int, Field(ge=1, le=500)] = 100) -> dict:
    return service.asset_summary(locals())


@mcp.tool(description="Search GLPI network equipment assets.")
def network_device_search(
    query: str | None = None,
    limit: Annotated[int, Field(ge=1, le=500)] = 50,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    return service.network_device_search(locals())


@mcp.tool(description="Get one GLPI network equipment asset by id.")
def network_device_get(id: Annotated[int, Field(ge=1)]) -> dict:
    return service.network_device_get(locals())


@mcp.tool(description="Generate a CSV or XLSX asset report from GLPI API data.")
def report_generate(
    asset_type: Literal["computer", "linux", "windows", "network_device"] = "computer",
    query: str | None = None,
    format: Literal["csv", "xlsx"] = "csv",
    limit: Annotated[int, Field(ge=1, le=5000)] = 500,
    columns: list[str] | None = None,
) -> dict:
    return service.report_generate(locals())


@mcp.tool(description="Generate one XLSX software report for Windows computers. Use this tool alone for software report requests; scan at most the requested number of computers, return only report metadata and the first 20 rows, and do not call custom_asset_report or software_inventory_query.")
def windows_software_report(
    max_computers: Annotated[int, Field(ge=1, le=10000)] = 3000,
) -> dict:
    return service.windows_software_report(locals())


@mcp.tool(description="Generate a custom CSV/XLSX report for any GLPI item type with user-selected fields.")
def custom_asset_report(
    fields: list[dict[str, str]],
    itemtype: str = "Computer",
    format: Literal["csv", "xlsx"] = "xlsx",
    max_items: Annotated[int, Field(ge=1, le=10000)] = 3000,
    query: str | None = None,
    expand_path: str | None = None,
    include_deleted: bool = False,
    include_softwares: bool = False,
) -> dict:
    return service.custom_asset_report(locals())


@mcp.tool(description="Check GLPI assets for stale or missing agent dates and generate an Excel report.")
def agent_health_check(
    itemtype: str = "Computer",
    stale_days: Annotated[int, Field(ge=1, le=3650)] = 30,
    max_items: Annotated[int, Field(ge=1, le=10000)] = 3000,
    include_ok: bool = False,
    date_fields: list[str] | None = None,
) -> dict:
    return service.agent_health_check(locals())


@mcp.tool(description="List GLPI Agent computers with hostname, IP, OS, agent version, last inventory time, and health status. Use for 'GLPI agent list' requests.")
def glpi_agent_list(
    query: str | None = None,
    stale_days: Annotated[int, Field(ge=1, le=3650)] = 30,
    max_items: Annotated[int, Field(ge=1, le=10000)] = 3000,
    limit: Annotated[int, Field(ge=1, le=1000)] = 100,
    date_fields: list[str] | None = None,
    version_fields: list[str] | None = None,
) -> dict:
    return service.glpi_agent_list(locals())


@mcp.tool(description="Advanced: get one raw GLPI item by itemtype and id.")
def glpi_raw_get(itemtype: str, id: Annotated[int, Field(ge=1)]) -> dict:
    return service.glpi_raw_get(locals())


@mcp.tool(description="Query normalized Windows/Linux assets by text, IP, software, or OS family.")
def asset_inventory_query(
    query: str | None = None,
    os_family: Literal["windows", "linux", "unknown"] | None = None,
    ip: str | None = None,
    software: str | None = None,
    max_items: Annotated[int, Field(ge=1, le=10000)] = 3000,
    limit: Annotated[int, Field(ge=1, le=1000)] = 100,
) -> dict:
    return service.asset_inventory_query(locals())


@mcp.tool(description="Get a complete normalized asset view including software, IP/MAC, storage, and optional raw GLPI data.")
def asset_full_details(
    id: Annotated[int, Field(ge=1)],
    asset_type: Literal["computer", "network_device"] = "computer",
    include_raw: bool = False,
) -> dict:
    return service.asset_full_details(locals())


@mcp.tool(description="Find installed software across Windows and Linux machines by name, version, or machine text.")
def software_inventory_query(
    query: str | None = None,
    computer_query: str | None = None,
    os_family: Literal["windows", "linux", "unknown"] | None = None,
    max_computers: Annotated[int, Field(ge=1, le=10000)] = 3000,
    limit: Annotated[int, Field(ge=1, le=5000)] = 500,
) -> dict:
    return service.software_inventory_query(locals())


@mcp.tool(description="Generate a computer inventory report in one call. Use this tool alone for user-requested fields such as name, serial number, hostname, operating system, OS version, and IP address; do not call field catalog or per-asset details first.")
def asset_inventory_report(
    query: str | None = None,
    os_family: Literal["windows", "linux", "unknown"] | None = None,
    format: Literal["csv", "xlsx"] = "xlsx",
    max_items: Annotated[int, Field(ge=1, le=10000)] = 3000,
    fields: list[Literal[
        "name", "serial_number", "hostname", "operating_system", "os_version",
        "ip_address", "mac_address", "location", "manufacturer", "model",
        "asset_tag", "software_count", "updated",
    ]] | None = None,
) -> dict:
    return service.asset_inventory_report(locals())


@mcp.tool(description="Generate a network device inventory report in one call. Use this tool alone for selected fields such as name, serial number, hostname, IP, MAC, manufacturer, model, location, status, and port count.")
def network_device_report(
    query: str | None = None,
    format: Literal["csv", "xlsx"] = "xlsx",
    max_items: Annotated[int, Field(ge=1, le=10000)] = 3000,
    fields: list[Literal[
        "name", "serial_number", "hostname", "ip_address", "mac_address",
        "manufacturer", "model", "location", "status", "asset_tag",
        "network_ports", "updated",
    ]] | None = None,
) -> dict:
    return service.network_device_report(locals())


@mcp.tool(description="Discover field paths returned by this GLPI deployment for a real asset.")
def asset_field_catalog(
    id: Annotated[int, Field(ge=1)],
    asset_type: Literal["computer", "network_device"] = "computer",
) -> dict:
    return service.asset_field_catalog(locals())


def main() -> None:
    host = os.environ.get("GLPI_MCP_HTTP_HOST", "0.0.0.0")
    port = int(os.environ.get("GLPI_MCP_HTTP_PORT", "8000"))
    path = os.environ.get("GLPI_MCP_HTTP_PATH", "/mcp")
    try:
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            streamable_http_path=path,
            stateless_http=True,
            json_response=True,
        )
    except KeyboardInterrupt:
        # The MCP SDK has already completed ASGI shutdown at this point.
        pass


if __name__ == "__main__":
    main()

