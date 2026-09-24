from __future__ import annotations

import os
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .reports import cleanup_expired_reports
from .server import McpServer as ToolService


service = ToolService()
mcp = MCPServer(
    "glpi-asset-mcp",
    description="Read GLPI assets and generate inventory reports.",
)


@mcp.tool(description="Return a lightweight summary count from GLPI computers and network devices.")
def asset_summary(sample_limit: Annotated[int, Field(ge=1, le=500)] = 100) -> dict:
    return service.asset_summary(locals())


@mcp.tool(description="List GLPI Agent computers with hostname, IP, OS, agent version, last inventory time, and health status. Use this tool alone for Agent version questions; agent_version=1.17 matches GLPI-Agent_v1.17-1, 1.17-1, and 1.17. Do not use software_inventory_query for Agent version filtering.")
def glpi_agent_list(
    query: str | None = None,
    agent_version: str | None = None,
    stale_days: Annotated[int, Field(ge=1, le=3650)] = 30,
    max_items: Annotated[int, Field(ge=1, le=10000)] = 3000,
    limit: Annotated[int, Field(ge=1, le=1000)] = 100,
    date_fields: list[str] | None = None,
    version_fields: list[str] | None = None,
) -> dict:
    return service.glpi_agent_list(locals())


@mcp.tool(description="Query normalized Windows/Linux assets by text, IP, software, or OS family. Returns compact chat data; use a report tool for complete exports.")
def asset_inventory_query(
    query: str | None = None,
    os_family: Literal["windows", "linux", "unknown"] | None = None,
    ip: str | None = None,
    software: str | None = None,
    max_items: Annotated[int, Field(ge=1, le=10000)] = 3000,
    limit: Annotated[int, Field(ge=1, le=200)] = 100,
) -> dict:
    return service.asset_inventory_query(locals())


@mcp.tool(description="Get one complete normalized asset view including software, IP/MAC, and storage. Use for one specific asset only; do not call repeatedly for reports.")
def asset_full_details(
    id: Annotated[int, Field(ge=1)],
    asset_type: Literal["computer", "network_device"] = "computer",
    include_raw: bool = False,
) -> dict:
    return service.asset_full_details(locals())


@mcp.tool(description="Search installed software inline for a small result set. Default limit is 100; for complete data use software_inventory_report.")
def software_inventory_query(
    query: str | None = None,
    computer_query: str | None = None,
    os_family: Literal["windows", "linux", "unknown"] | None = None,
    max_computers: Annotated[int, Field(ge=1, le=1000)] = 300,
    limit: Annotated[int, Field(ge=1, le=1000)] = 100,
) -> dict:
    return service.software_inventory_query(locals())


@mcp.tool(description="Generate one CSV/XLSX software report across Windows and Linux computers. Use this tool alone for software report requests; return only the server path, row count, and first 20 rows. Do not call custom reports or software_inventory_query.")
def software_inventory_report(
    max_computers: Annotated[int, Field(ge=1, le=1000)] = 300,
    os_family: Literal["windows", "linux", "unknown"] | None = None,
    query: str | None = None,
    format: Literal["csv", "xlsx"] = "xlsx",
) -> dict:
    return service.software_inventory_report(locals())


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


def main() -> None:
    host = os.environ.get("GLPI_MCP_HTTP_HOST", "0.0.0.0")
    port = int(os.environ.get("GLPI_MCP_HTTP_PORT", "8000"))
    path = os.environ.get("GLPI_MCP_HTTP_PATH", "/mcp")
    cleanup_expired_reports(service.settings.reports_dir)
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

