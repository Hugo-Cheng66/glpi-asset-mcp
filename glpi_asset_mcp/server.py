from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .glpi_client import (
    DEFAULT_AGENT_DATE_FIELDS,
    DEFAULT_AGENT_VERSION_FIELDS,
    GlpiClient,
    find_first_date_value,
    find_first_text_value,
    normalize_asset,
    parse_glpi_datetime,
)
from .reports import expand_items, generate_custom_report, generate_report


SERVER_INFO = {
    "name": "glpi-asset-mcp",
    "version": "0.1.0",
}


TOOLS = [
    {
        "name": "asset_search",
        "description": "Search GLPI computer assets. Use asset_type linux/windows/computer for VMs and servers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_type": {"type": "string", "enum": ["computer", "linux", "windows"], "default": "computer"},
                "query": {"type": "string", "description": "Optional local filter for name, serial, UUID, contact, or text fields."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
        },
    },
    {
        "name": "asset_get",
        "description": "Get one GLPI computer asset by id.",
        "inputSchema": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "asset_type": {"type": "string", "enum": ["computer", "linux", "windows"], "default": "computer"},
                "id": {"type": "integer", "minimum": 1},
            },
        },
    },
    {
        "name": "asset_summary",
        "description": "Return a lightweight summary count from GLPI computers and network devices.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sample_limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
            },
        },
    },
    {
        "name": "network_device_search",
        "description": "Search GLPI network equipment assets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
        },
    },
    {
        "name": "network_device_get",
        "description": "Get one GLPI network equipment asset by id.",
        "inputSchema": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "integer", "minimum": 1},
            },
        },
    },
    {
        "name": "report_generate",
        "description": "Generate a CSV or XLSX asset report from GLPI API data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_type": {
                    "type": "string",
                    "enum": ["computer", "linux", "windows", "network_device"],
                    "default": "computer",
                },
                "query": {"type": "string"},
                "format": {"type": "string", "enum": ["csv", "xlsx"], "default": "csv"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 500},
                "columns": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "windows_software_report",
        "description": "Generate one XLSX software report for Windows computers. Use this tool alone for report requests; return only metadata and the first 20 rows. Do not call custom_asset_report or software_inventory_query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_computers": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10000,
                    "default": 3000,
                    "description": "Maximum number of GLPI Computer records to scan.",
                },
            },
        },
    },
    {
        "name": "custom_asset_report",
        "description": "Generate a custom CSV/XLSX report for any GLPI item type with user-selected fields.",
        "inputSchema": {
            "type": "object",
            "required": ["fields"],
            "properties": {
                "itemtype": {
                    "type": "string",
                    "default": "Computer",
                    "description": "GLPI item type, for example Computer, NetworkEquipment, Printer, Monitor, Software.",
                },
                "fields": {
                    "type": "array",
                    "description": "Report columns. Paths can use dot notation, for example asset.name, item.version, locations_id.",
                    "items": {
                        "type": "object",
                        "required": ["path"],
                        "properties": {
                            "path": {"type": "string"},
                            "label": {"type": "string"},
                        },
                    },
                },
                "format": {"type": "string", "enum": ["csv", "xlsx"], "default": "xlsx"},
                "max_items": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 3000},
                "query": {"type": "string", "description": "Optional text filter across returned GLPI values."},
                "expand_path": {
                    "type": "string",
                    "description": "Optional list path to expand into multiple rows, for example softwares or NetworkPort.",
                },
                "include_deleted": {"type": "boolean", "default": False},
                "include_softwares": {
                    "type": "boolean",
                    "default": False,
                    "description": "Request with_softwares=true from GLPI when supported.",
                },
            },
        },
    },
    {
        "name": "agent_health_check",
        "description": "Check GLPI assets for stale or missing agent inventory/contact dates and generate an Excel security report.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "itemtype": {
                    "type": "string",
                    "default": "Computer",
                    "description": "GLPI item type to check. Usually Computer for GLPI Agent inventory.",
                },
                "stale_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 3650,
                    "default": 30,
                    "description": "Assets older than this threshold are marked stale.",
                },
                "max_items": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 3000},
                "include_ok": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include healthy assets in the report. By default only stale/missing assets are exported.",
                },
                "date_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional ordered date fields to check before defaults.",
                },
            },
        },
    },
    {
        "name": "glpi_agent_list",
        "description": "List GLPI Agent computers with hostname, IP, OS, agent version, last inventory time, and health status. Use this for requests such as 'GLPI agent list'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional filter across hostname, IP, OS, version, and status."},
                "stale_days": {"type": "integer", "minimum": 1, "maximum": 3650, "default": 30},
                "max_items": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 3000},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
                "date_fields": {"type": "array", "items": {"type": "string"}},
                "version_fields": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "glpi_raw_get",
        "description": "Advanced: get one raw GLPI item by itemtype and id.",
        "inputSchema": {
            "type": "object",
            "required": ["itemtype", "id"],
            "properties": {
                "itemtype": {"type": "string", "description": "GLPI item type, for example Computer or NetworkEquipment."},
                "id": {"type": "integer", "minimum": 1},
            },
        },
    },
]

TOOLS.extend([
    {
        "name": "asset_inventory_query",
        "description": "Query normalized Windows/Linux assets by name, text, IP, software, or OS family.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"}, "os_family": {"type": "string", "enum": ["windows", "linux", "unknown"]},
            "ip": {"type": "string"}, "software": {"type": "string"},
            "max_items": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 3000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
        }},
    },
    {
        "name": "asset_full_details",
        "description": "Get a normalized complete asset view including software, IP/MAC, and storage.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {
            "id": {"type": "integer", "minimum": 1},
            "asset_type": {"type": "string", "enum": ["computer", "network_device"], "default": "computer"},
            "include_raw": {"type": "boolean", "default": False},
        }},
    },
    {
        "name": "software_inventory_query",
        "description": "Find Windows or Linux machines and installed software by software name/version or machine text.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"}, "computer_query": {"type": "string"},
            "os_family": {"type": "string", "enum": ["windows", "linux", "unknown"]},
            "max_computers": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 3000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 500},
        }},
    },
    {
        "name": "asset_inventory_report",
        "description": "Generate a computer inventory report in one call. Use this tool alone for requested fields; do not call field catalog or per-asset details first.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"}, "os_family": {"type": "string", "enum": ["windows", "linux", "unknown"]},
            "format": {"type": "string", "enum": ["csv", "xlsx"], "default": "xlsx"},
            "max_items": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 3000},
            "fields": {"type": "array", "items": {"type": "string", "enum": [
                "name", "serial_number", "hostname", "operating_system", "os_version", "ip_address",
                "mac_address", "location", "manufacturer", "model", "asset_tag", "software_count", "updated"
            ]}},
        }},
    },
    {
        "name": "network_device_report",
        "description": "Generate a network device inventory report in one call. Use this tool alone for requested network fields; do not call field catalog or per-device details first.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"}, "format": {"type": "string", "enum": ["csv", "xlsx"], "default": "xlsx"},
            "max_items": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 3000},
            "fields": {"type": "array", "items": {"type": "string", "enum": [
                "name", "serial_number", "hostname", "ip_address", "mac_address", "manufacturer",
                "model", "location", "status", "asset_tag", "network_ports", "updated"
            ]}},
        }},
    },
    {
        "name": "asset_field_catalog",
        "description": "Discover the field paths returned by this GLPI deployment for a real asset.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {
            "id": {"type": "integer", "minimum": 1},
            "asset_type": {"type": "string", "enum": ["computer", "network_device"], "default": "computer"},
        }},
    },
])


class McpServer:
    def __init__(self) -> None:
        self.settings = Settings.from_env()
        self.handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "asset_search": self.asset_search,
            "asset_get": self.asset_get,
            "asset_summary": self.asset_summary,
            "network_device_search": self.network_device_search,
            "network_device_get": self.network_device_get,
            "report_generate": self.report_generate,
            "windows_software_report": self.windows_software_report,
            "custom_asset_report": self.custom_asset_report,
            "agent_health_check": self.agent_health_check,
            "glpi_agent_list": self.glpi_agent_list,
            "glpi_raw_get": self.glpi_raw_get,
            "asset_inventory_query": self.asset_inventory_query,
            "asset_full_details": self.asset_full_details,
            "software_inventory_query": self.software_inventory_query,
            "asset_inventory_report": self.asset_inventory_report,
            "network_device_report": self.network_device_report,
            "asset_field_catalog": self.asset_field_catalog,
        }

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")

        try:
            if method == "initialize":
                return self.response(request_id, {
                    "protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                })
            if method == "notifications/initialized":
                return None
            if method == "tools/list":
                return self.response(request_id, {"tools": TOOLS})
            if method == "tools/call":
                params = message.get("params", {})
                name = params.get("name")
                arguments = params.get("arguments", {}) or {}
                if name not in self.handlers:
                    raise ValueError(f"Unknown tool: {name}")
                result = self.handlers[name](arguments)
                return self.response(request_id, {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=False, indent=2),
                        }
                    ],
                    "isError": False,
                })
            return self.error(request_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            return self.response(request_id, {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            })

    def asset_search(self, args: dict[str, Any]) -> dict[str, Any]:
        with GlpiClient(self.settings) as client:
            items = client.search_items(
                args.get("asset_type", "computer"),
                query=args.get("query"),
                limit=int(args.get("limit", 50)),
                offset=int(args.get("offset", 0)),
            )
        return {"items": items, "count": len(items)}

    def asset_get(self, args: dict[str, Any]) -> dict[str, Any]:
        with GlpiClient(self.settings) as client:
            return client.get_item(args.get("asset_type", "computer"), int(args["id"]))

    def asset_summary(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = int(args.get("sample_limit", 100))
        with GlpiClient(self.settings) as client:
            computers = client.list_items("computer", limit=limit)
            network_devices = client.list_items("network_device", limit=limit)
        return {
            "sample_limit": limit,
            "computer_sample_count": len(computers),
            "network_device_sample_count": len(network_devices),
            "note": "Counts are sample counts from bounded GLPI API reads. Use a cache DB for exact large reports.",
        }

    def network_device_search(self, args: dict[str, Any]) -> dict[str, Any]:
        with GlpiClient(self.settings) as client:
            items = client.search_items(
                "network_device",
                query=args.get("query"),
                limit=int(args.get("limit", 50)),
                offset=int(args.get("offset", 0)),
            )
        return {"items": items, "count": len(items)}

    def network_device_get(self, args: dict[str, Any]) -> dict[str, Any]:
        with GlpiClient(self.settings) as client:
            return client.get_item("network_device", int(args["id"]))

    def report_generate(self, args: dict[str, Any]) -> dict[str, Any]:
        asset_type = args.get("asset_type", "computer")
        file_format = args.get("format", "csv")
        with GlpiClient(self.settings) as client:
            items = client.search_items(
                asset_type,
                query=args.get("query"),
                limit=int(args.get("limit", 500)),
            )
        return generate_report(
            items,
            self.settings.reports_dir,
            report_type=asset_type,
            file_format=file_format,
            columns=args.get("columns"),
        )

    def windows_software_report(self, args: dict[str, Any]) -> dict[str, Any]:
        with GlpiClient(self.settings) as client:
            inventory = client.windows_software_inventory(
                max_computers=int(args.get("max_computers", 3000)),
            )
        report = generate_report(
            inventory["rows"],
            self.settings.reports_dir,
            report_type="windows-software",
            file_format="xlsx",
            columns=["Display name", "Version", "Discovery model", "Installed on", "Updated"],
        )
        preview = inventory["rows"][:20]
        return {
            "windows_computer_count": inventory["windows_computer_count"],
            "software_row_count": inventory["software_row_count"],
            "fields": ["Display name", "Version", "Discovery model", "Installed on", "Updated"],
            "preview": preview,
            "markdown_preview": _markdown_table(preview, ["Display name", "Version", "Discovery model", "Installed on", "Updated"]),
            "report": report,
            "instruction": "Present the report path, row count, and markdown_preview. Do not output all software rows or call another tool.",
        }

    def custom_asset_report(self, args: dict[str, Any]) -> dict[str, Any]:
        itemtype = str(args.get("itemtype", "Computer"))
        options = {}
        if args.get("include_softwares"):
            options["with_softwares"] = "true"

        with GlpiClient(self.settings) as client:
            items = client.iter_itemtype(
                itemtype,
                max_items=int(args.get("max_items", 3000)),
                include_deleted=bool(args.get("include_deleted", False)),
                options=options,
            )

        query = args.get("query")
        if query:
            needle = str(query).casefold()
            items = [item for item in items if needle in json.dumps(item, ensure_ascii=False).casefold()]

        expanded = expand_items(items, args.get("expand_path"))
        fields = args["fields"]
        report = generate_custom_report(
            expanded,
            self.settings.reports_dir,
            report_type=f"custom-{itemtype}",
            file_format=args.get("format", "xlsx"),
            fields=fields,
        )
        return {
            "itemtype": itemtype,
            "source_items": len(items),
            "report_rows": report["rows"],
            "report": report,
        }

    def agent_health_check(self, args: dict[str, Any]) -> dict[str, Any]:
        with GlpiClient(self.settings) as client:
            health = client.agent_health_check(
                itemtype=str(args.get("itemtype", "Computer")),
                stale_days=int(args.get("stale_days", 30)),
                max_items=int(args.get("max_items", 3000)),
                date_fields=args.get("date_fields"),
                include_ok=bool(args.get("include_ok", False)),
            )

        report = generate_report(
            health["rows"],
            self.settings.reports_dir,
            report_type="agent-health-check",
            file_format="xlsx",
            columns=[
                "Status",
                "Asset ID",
                "Asset name",
                "Serial",
                "UUID",
                "Location",
                "Last seen",
                "Matched field",
                "Age days",
                "Threshold days",
                "Updated",
            ],
        )
        return {
            "itemtype": health["itemtype"],
            "checked_at": health["checked_at"],
            "threshold_days": health["threshold_days"],
            "total_checked": health["total_checked"],
            "ok_count": health["ok_count"],
            "stale_count": health["stale_count"],
            "missing_agent_date_count": health["missing_agent_date_count"],
            "items": health["rows"][:100],
            "report": report,
        }

    def glpi_agent_list(self, args: dict[str, Any]) -> dict[str, Any]:
        stale_days = int(args.get("stale_days", 30))
        date_fields = args.get("date_fields") or DEFAULT_AGENT_DATE_FIELDS
        version_fields = args.get("version_fields") or DEFAULT_AGENT_VERSION_FIELDS
        with GlpiClient(self.settings) as client:
            items = client.complete_inventory("computer", max_items=int(args.get("max_items", 3000)))

        now = datetime.now(timezone.utc)
        agents: list[dict[str, Any]] = []
        for item in items:
            asset = normalize_asset(item)
            last_seen_raw, date_field = find_first_date_value(item, date_fields)
            agent_version, version_field = find_first_text_value(item, version_fields)
            last_seen = parse_glpi_datetime(last_seen_raw)
            age_days = (now - last_seen).days if last_seen else None
            status = "unknown"
            if age_days is not None:
                status = "stale" if age_days >= stale_days else "active"
            agents.append({
                "id": asset["id"],
                "hostname": asset["name"],
                "status": status,
                "ip_addresses": [row["ip"] for row in asset["networks"] if row.get("ip")],
                "os": asset["operating_system"],
                "os_family": asset["os_family"],
                "agent_version": agent_version or "unknown",
                "last_inventory": last_seen_raw or "unknown",
                "age_days": age_days,
                "location": asset["location"],
                "matched_date_field": date_field or "",
                "matched_version_field": version_field or "",
            })

        query = str(args.get("query") or "").casefold()
        if query:
            agents = [agent for agent in agents if query in json.dumps(agent, ensure_ascii=False).casefold()]
        total = len(agents)
        agents = agents[:int(args.get("limit", 100))]
        counts = {status: sum(agent["status"] == status for agent in agents) for status in ("active", "stale", "unknown")}
        lines = [
            "# GLPI Agent list",
            "",
            f"Total matches: {total}; returned: {len(agents)}; active: {counts['active']}; stale: {counts['stale']}; unknown: {counts['unknown']}.",
            "",
            "| ID | Hostname | Status | IP address | Operating system | Agent version | Last inventory |",
            "|---:|---|---|---|---|---|---|",
        ]
        for agent in agents:
            values = [
                agent["id"], agent["hostname"], agent["status"], ", ".join(agent["ip_addresses"]),
                agent["os"], agent["agent_version"], agent["last_inventory"],
            ]
            lines.append("| " + " | ".join(str(value or "-").replace("|", "\\|") for value in values) + " |")
        return {
            "summary": {"total_matches": total, "returned": len(agents), **counts, "stale_threshold_days": stale_days},
            "agents": agents,
            "markdown": "\n".join(lines),
            "notes": [
                "Status is inferred from the latest GLPI inventory/contact date; it is not a live connection state.",
                "Unknown version/date means this GLPI deployment did not expose a recognized field. Use asset_field_catalog to discover custom fields.",
            ],
        }

    def glpi_raw_get(self, args: dict[str, Any]) -> dict[str, Any]:
        itemtype = str(args["itemtype"])
        with GlpiClient(self.settings) as client:
            response = client._request("GET", f"/{itemtype}/{int(args['id'])}", params={"expand_dropdowns": "true"})
        return response.data

    def asset_full_details(self, args: dict[str, Any]) -> dict[str, Any]:
        asset_type = str(args.get("asset_type", "computer"))
        with GlpiClient(self.settings) as client:
            item = client.get_complete_item(asset_type, int(args["id"]))
        return normalize_asset(item, asset_type, include_raw=bool(args.get("include_raw", False)))

    def asset_inventory_query(self, args: dict[str, Any]) -> dict[str, Any]:
        with GlpiClient(self.settings) as client:
            items = client.complete_inventory("computer", max_items=int(args.get("max_items", 3000)))
        assets = [normalize_asset(item) for item in items]
        assets = _filter_normalized_assets(assets, args)
        total = len(assets)
        assets = assets[:int(args.get("limit", 100))]
        return {"total_matches": total, "returned": len(assets), "items": assets}

    def software_inventory_query(self, args: dict[str, Any]) -> dict[str, Any]:
        with GlpiClient(self.settings) as client:
            items = client.complete_inventory("computer", max_items=int(args.get("max_computers", 3000)))
        assets = [normalize_asset(item) for item in items]
        if args.get("os_family"):
            assets = [asset for asset in assets if asset["os_family"] == args["os_family"]]
        computer_query = str(args.get("computer_query") or "").casefold()
        software_query = str(args.get("query") or "").casefold()
        rows: list[dict[str, Any]] = []
        for asset in assets:
            if computer_query and computer_query not in json.dumps(asset, ensure_ascii=False).casefold():
                continue
            for software in asset["software"]:
                if software_query and software_query not in json.dumps(software, ensure_ascii=False).casefold():
                    continue
                rows.append({"Computer ID": asset["id"], "Computer": asset["name"], "OS family": asset["os_family"], **software})
        total = len(rows)
        rows = rows[:int(args.get("limit", 500))]
        return {"total_matches": total, "returned": len(rows), "items": rows}

    def asset_inventory_report(self, args: dict[str, Any]) -> dict[str, Any]:
        query_args = {**args, "limit": int(args.get("max_items", 3000))}
        result = self.asset_inventory_query(query_args)
        rows = [_asset_report_row(asset) for asset in result["items"]]
        field_columns = {
            "name": "Name", "serial_number": "Serial number", "hostname": "Hostname",
            "operating_system": "Operating system", "os_version": "OS version",
            "ip_address": "IP address", "mac_address": "MAC address", "location": "Location",
            "manufacturer": "Manufacturer", "model": "Model", "asset_tag": "Asset tag",
            "software_count": "Software count", "updated": "Updated",
        }
        requested_fields = args.get("fields") or [
            "name", "serial_number", "hostname", "operating_system", "os_version", "ip_address"
        ]
        unknown_fields = [field for field in requested_fields if field not in field_columns]
        if unknown_fields:
            raise ValueError(f"Unsupported report fields: {', '.join(unknown_fields)}")
        columns = [field_columns[field] for field in requested_fields]
        projected_rows = [{column: row.get(column, "") for column in columns} for row in rows]
        report = generate_report(
            projected_rows, self.settings.reports_dir, report_type="asset-inventory",
            file_format=args.get("format", "xlsx"), columns=columns,
        )
        preview = projected_rows[:20]
        return {
            "matches": result["total_matches"], "returned": len(projected_rows), "fields": requested_fields,
            "preview": preview, "markdown_preview": _markdown_table(preview, columns), "report": report,
            "instruction": "Present markdown_preview and the generated file path. Do not call other tools.",
        }

    def network_device_report(self, args: dict[str, Any]) -> dict[str, Any]:
        with GlpiClient(self.settings) as client:
            items = client.complete_inventory("network_device", max_items=int(args.get("max_items", 3000)))
        assets = [normalize_asset(item, "network_device") for item in items]
        query = str(args.get("query") or "").casefold()
        if query:
            assets = [asset for asset in assets if query in json.dumps(asset, ensure_ascii=False).casefold()]
        rows = [_asset_report_row(asset) for asset in assets]
        field_columns = {
            "name": "Name", "serial_number": "Serial number", "hostname": "Hostname",
            "ip_address": "IP address", "mac_address": "MAC address",
            "manufacturer": "Manufacturer", "model": "Model", "location": "Location",
            "status": "Status", "asset_tag": "Asset tag", "network_ports": "Network ports",
            "updated": "Updated",
        }
        requested_fields = args.get("fields") or [
            "name", "serial_number", "hostname", "ip_address", "mac_address",
            "manufacturer", "model", "location", "status", "network_ports",
        ]
        unknown_fields = [field for field in requested_fields if field not in field_columns]
        if unknown_fields:
            raise ValueError(f"Unsupported network report fields: {', '.join(unknown_fields)}")
        columns = [field_columns[field] for field in requested_fields]
        projected_rows = [{column: row.get(column, "") for column in columns} for row in rows]
        report = generate_report(
            projected_rows, self.settings.reports_dir, report_type="network-devices",
            file_format=args.get("format", "xlsx"), columns=columns,
        )
        preview = projected_rows[:20]
        return {
            "matches": len(projected_rows), "returned": len(projected_rows), "fields": requested_fields,
            "preview": preview, "markdown_preview": _markdown_table(preview, columns), "report": report,
            "instruction": "Present markdown_preview and the generated file path. Do not call other tools.",
        }

    def asset_field_catalog(self, args: dict[str, Any]) -> dict[str, Any]:
        asset_type = str(args.get("asset_type", "computer"))
        with GlpiClient(self.settings) as client:
            item = client.get_complete_item(asset_type, int(args["id"]))
        paths = sorted(_discover_field_paths(item))
        return {"asset_type": asset_type, "id": int(args["id"]), "field_count": len(paths), "fields": paths}

    @staticmethod
    def response(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _filter_normalized_assets(assets: list[dict[str, Any]], args: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for asset in assets:
        if args.get("os_family") and asset["os_family"] != args["os_family"]:
            continue
        text = json.dumps(asset, ensure_ascii=False).casefold()
        if args.get("query") and str(args["query"]).casefold() not in text:
            continue
        if args.get("ip") and str(args["ip"]).casefold() not in json.dumps(asset["networks"], ensure_ascii=False).casefold():
            continue
        if args.get("software") and str(args["software"]).casefold() not in json.dumps(asset["software"], ensure_ascii=False).casefold():
            continue
        result.append(asset)
    return result


def _asset_report_row(asset: dict[str, Any]) -> dict[str, Any]:
    networks = asset.get("networks", [])
    storage = asset.get("storage", [])
    software = asset.get("software", [])
    return {
        "ID": asset.get("id"), "Name": asset.get("name"), "Hostname": asset.get("name"),
        "Asset type": asset.get("asset_type"), "OS family": asset.get("os_family"),
        "Operating system": asset.get("operating_system"), "OS version": asset.get("os_version"),
        "Serial": asset.get("serial"), "Serial number": asset.get("serial"), "Asset tag": asset.get("asset_tag"),
        "UUID": asset.get("uuid"), "Location": asset.get("location"), "Status": asset.get("status"),
        "Manufacturer": asset.get("manufacturer"), "Model": asset.get("model"),
        "IP addresses": ", ".join(row.get("ip", "") for row in networks if row.get("ip")),
        "IP address": ", ".join(row.get("ip", "") for row in networks if row.get("ip")),
        "MAC addresses": ", ".join(row.get("mac", "") for row in networks if row.get("mac")),
        "MAC address": ", ".join(row.get("mac", "") for row in networks if row.get("mac")),
        "Network ports": len(networks), "Storage": json.dumps(storage, ensure_ascii=False),
        "Software count": len(software), "Software": ", ".join(row.get("Display name", "") for row in software),
        "Updated": asset.get("updated"),
    }


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "No matching assets."
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        values = [str(row.get(column, "") or "-").replace("|", "\\|").replace("\n", " ") for column in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _discover_field_paths(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.add(path)
            paths.update(_discover_field_paths(child, path))
    elif isinstance(value, list):
        list_prefix = f"{prefix}[]"
        paths.add(list_prefix)
        for child in value[:10]:
            paths.update(_discover_field_paths(child, list_prefix))
    return paths


def main() -> None:
    server = McpServer()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = server.handle(message)
        except Exception:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": traceback.format_exc()},
            }
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

