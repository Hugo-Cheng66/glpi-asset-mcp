from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Callable
from typing import Any

from .config import Settings
from .glpi_client import GlpiClient
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
        "description": "Generate an Excel report of software installed on Windows computers, with Windows computer count.",
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
            "glpi_raw_get": self.glpi_raw_get,
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
        return {
            "windows_computer_count": inventory["windows_computer_count"],
            "software_row_count": inventory["software_row_count"],
            "report": report,
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
            "report": report,
        }

    def glpi_raw_get(self, args: dict[str, Any]) -> dict[str, Any]:
        itemtype = str(args["itemtype"])
        with GlpiClient(self.settings) as client:
            response = client._request("GET", f"/{itemtype}/{int(args['id'])}", params={"expand_dropdowns": "true"})
        return response.data

    @staticmethod
    def response(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


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
