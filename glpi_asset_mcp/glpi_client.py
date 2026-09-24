from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import Settings


ASSET_TYPES = {
    "computer": "Computer",
    "linux": "Computer",
    "windows": "Computer",
    "network_device": "NetworkEquipment",
    "network": "NetworkEquipment",
}


DEFAULT_AGENT_DATE_FIELDS = [
    "last_inventory_update",
    "date_last_inventory_update",
    "last_inventory_date",
    "date_last_inventory",
    "last_contact",
    "date_mod",
    "updated",
]

DEFAULT_AGENT_VERSION_FIELDS = [
    "agent_version",
    "glpi_agent_version",
    "fusioninventory_agent_version",
    "useragent",
    "user-agent",
    "user_agent",
    "versionclient",
    "agent.version",
]


@dataclass
class GlpiResponse:
    data: Any
    headers: dict[str, str]


class GlpiClient:
    def __init__(self, settings: Settings):
        settings.validate()
        self.settings = settings
        self._session_token: str | None = None

    def __enter__(self) -> "GlpiClient":
        self.init_session()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.kill_session()

    def init_session(self) -> str:
        if self._session_token:
            return self._session_token

        headers = self._base_headers(include_session=False)
        if self.settings.glpi_user_token:
            headers["Authorization"] = f"user_token {self.settings.glpi_user_token}"
        else:
            raw = f"{self.settings.glpi_username}:{self.settings.glpi_password}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")

        response = self._request("GET", "/initSession", headers=headers, include_session=False)
        token = response.data.get("session_token")
        if not token:
            raise RuntimeError("GLPI did not return session_token")
        self._session_token = token
        return token

    def kill_session(self) -> None:
        if not self._session_token:
            return
        try:
            self._request("GET", "/killSession")
        finally:
            self._session_token = None

    def list_items(
        self,
        asset_type: str,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        itemtype = resolve_asset_type(asset_type)
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        end = offset + limit - 1
        params = {
            "range": f"{offset}-{end}",
            "is_deleted": "1" if include_deleted else "0",
            "expand_dropdowns": "true",
            "with_networkports": "true",
        }
        response = self._request("GET", f"/{itemtype}", params=params)
        if isinstance(response.data, list):
            return response.data
        if isinstance(response.data, dict) and "data" in response.data:
            return response.data["data"]
        return []

    def list_itemtype(
        self,
        itemtype: str,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        options: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        end = offset + limit - 1
        params = {
            "range": f"{offset}-{end}",
            "is_deleted": "1" if include_deleted else "0",
            "expand_dropdowns": "true",
            "with_networkports": "true",
            "with_infocoms": "true",
        }
        if options:
            params.update({key: str(value) for key, value in options.items()})
        response = self._request("GET", f"/{itemtype}", params=params)
        if isinstance(response.data, list):
            return response.data
        if isinstance(response.data, dict) and "data" in response.data:
            return response.data["data"]
        return []

    def iter_items(
        self,
        asset_type: str,
        *,
        max_items: int = 3000,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        page_size = max(1, min(page_size, 500))
        max_items = max(1, max_items)
        while len(items) < max_items:
            batch = self.list_items(asset_type, limit=min(page_size, max_items - len(items)), offset=offset)
            if not batch:
                break
            items.extend(batch)
            if len(batch) < page_size:
                break
            offset += len(batch)
        return items

    def iter_itemtype(
        self,
        itemtype: str,
        *,
        max_items: int = 3000,
        page_size: int = 100,
        include_deleted: bool = False,
        options: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        page_size = max(1, min(page_size, 500))
        max_items = max(1, max_items)
        while len(items) < max_items:
            batch = self.list_itemtype(
                itemtype,
                limit=min(page_size, max_items - len(items)),
                offset=offset,
                include_deleted=include_deleted,
                options=options,
            )
            if not batch:
                break
            items.extend(batch)
            if len(batch) < page_size:
                break
            offset += len(batch)
        return items

    def get_itemtype(self, itemtype: str, item_id: int, *, options: dict[str, str] | None = None) -> dict[str, Any]:
        params = {
            "expand_dropdowns": "true",
            "with_networkports": "true",
            "with_infocoms": "true",
        }
        if options:
            params.update({key: str(value) for key, value in options.items()})
        response = self._request("GET", f"/{itemtype}/{item_id}", params=params)
        if not isinstance(response.data, dict):
            raise RuntimeError(f"Unexpected GLPI response for {itemtype}/{item_id}")
        return response.data

    def get_item(self, asset_type: str, item_id: int, *, include_softwares: bool = False) -> dict[str, Any]:
        itemtype = resolve_asset_type(asset_type)
        params = {
            "expand_dropdowns": "true",
            "with_networkports": "true",
            "with_infocoms": "true",
        }
        if include_softwares:
            params["with_softwares"] = "true"
        response = self._request("GET", f"/{itemtype}/{item_id}", params=params)
        if not isinstance(response.data, dict):
            raise RuntimeError(f"Unexpected GLPI response for {itemtype}/{item_id}")
        return response.data

    def get_complete_item(self, asset_type: str, item_id: int) -> dict[str, Any]:
        itemtype = resolve_asset_type(asset_type)
        params = {
            "expand_dropdowns": "true",
            "with_devices": "true",
            "with_disks": "true",
            "with_softwares": "true",
            "with_networkports": "true",
            "with_infocoms": "true",
        }
        response = self._request("GET", f"/{itemtype}/{item_id}", params=params)
        if not isinstance(response.data, dict):
            raise RuntimeError(f"Unexpected GLPI response for {itemtype}/{item_id}")
        return response.data

    def complete_inventory(self, asset_type: str, *, max_items: int = 3000) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in self.iter_items(asset_type, max_items=max_items):
            item_id = item.get("id")
            if not item_id:
                continue
            detail = self.get_complete_item(asset_type, int(item_id))
            results.append({**item, **detail})
        return results

    def windows_software_inventory(self, *, max_computers: int = 3000) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        windows_computers: list[dict[str, Any]] = []
        computers = self.iter_items("computer", max_items=max_computers)

        for computer in computers:
            computer_id = computer.get("id")
            if not computer_id:
                continue
            detail = self.get_item("computer", int(computer_id), include_softwares=True)
            merged = {**computer, **detail}
            if not is_windows_computer(merged):
                continue

            windows_computers.append(merged)
            rows.extend(extract_software_rows(merged))

        return {
            "windows_computer_count": len(windows_computers),
            "software_row_count": len(rows),
            "rows": rows,
        }

    def software_inventory(self, *, max_computers: int = 3000, os_family: str | None = None) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        computers: list[dict[str, Any]] = []
        for computer in self.iter_items("computer", max_items=max_computers):
            computer_id = computer.get("id")
            if not computer_id:
                continue
            detail = self.get_item("computer", int(computer_id), include_softwares=True)
            merged = {**computer, **detail}
            family = detect_os_family(merged)
            if os_family and family != os_family:
                continue
            computers.append(merged)
            rows.extend(extract_software_rows(merged))
        return {
            "computer_count": len(computers),
            "software_row_count": len(rows),
            "rows": rows,
        }

    def agent_health_check(
        self,
        *,
        itemtype: str = "Computer",
        stale_days: int = 30,
        max_items: int = 3000,
        date_fields: list[str] | None = None,
        include_ok: bool = False,
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        stale_assets = 0
        missing_date_assets = 0
        ok_assets = 0
        checked_at = datetime.now(timezone.utc)
        fields = date_fields or DEFAULT_AGENT_DATE_FIELDS
        items = self.iter_itemtype(
            itemtype,
            max_items=max_items,
            options={"with_networkports": "true", "with_infocoms": "true"},
        )

        for item in items:
            last_seen_raw, matched_field = find_first_date_value(item, fields)
            last_seen = parse_glpi_datetime(last_seen_raw)
            age_days: int | None = None
            status = "missing_agent_date"

            if last_seen:
                age_days = (checked_at - last_seen).days
                status = "stale" if age_days >= stale_days else "ok"

            if status == "stale":
                stale_assets += 1
            elif status == "missing_agent_date":
                missing_date_assets += 1
            else:
                ok_assets += 1
                if not include_ok:
                    continue

            rows.append({
                "Status": status,
                "Asset ID": item.get("id", ""),
                "Asset name": item.get("name", ""),
                "Serial": item.get("serial", ""),
                "UUID": item.get("uuid", ""),
                "Location": _value_to_text(item.get("locations_id")),
                "Last seen": last_seen_raw or "",
                "Matched field": matched_field or "",
                "Age days": age_days if age_days is not None else "",
                "Threshold days": stale_days,
                "Updated": item.get("date_mod", ""),
            })

        return {
            "itemtype": itemtype,
            "checked_at": checked_at.isoformat(),
            "threshold_days": stale_days,
            "total_checked": len(items),
            "ok_count": ok_assets,
            "stale_count": stale_assets,
            "missing_agent_date_count": missing_date_assets,
            "rows": rows,
        }

    def search_items(
        self,
        asset_type: str,
        *,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        # GLPI search criteria field IDs differ between deployments. For a reliable MVP,
        # fetch a bounded list through the REST item endpoint and do local filtering.
        items = self.list_items(asset_type, limit=limit, offset=offset)
        if not query:
            return items

        needle = query.casefold()
        return [item for item in items if needle in _asset_search_blob(item)]

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        include_session: bool = True,
    ) -> GlpiResponse:
        base = self.settings.glpi_base_url
        if not base.endswith("/apirest.php"):
            base = base.rstrip("/") + "/apirest.php"

        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)

        request_headers = self._base_headers(include_session=include_session)
        if headers:
            request_headers.update(headers)

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                return GlpiResponse(parsed, dict(response.headers.items()))
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GLPI HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach GLPI API: {exc.reason}") from exc

    def _base_headers(self, *, include_session: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
        }
        if self.settings.glpi_app_token:
            headers["App-Token"] = self.settings.glpi_app_token
        if include_session:
            token = self.init_session()
            headers["Session-Token"] = token
        return headers


def resolve_asset_type(asset_type: str) -> str:
    key = asset_type.strip().lower()
    if key not in ASSET_TYPES:
        raise ValueError(f"Unsupported asset_type '{asset_type}'. Use: {', '.join(sorted(ASSET_TYPES))}")
    return ASSET_TYPES[key]


def _asset_search_blob(item: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("id", "name", "serial", "otherserial", "contact", "comment", "uuid"):
        value = item.get(key)
        if value is not None:
            values.append(str(value))
    for value in item.values():
        if isinstance(value, str):
            values.append(value)
    return " ".join(values).casefold()


def is_windows_computer(item: dict[str, Any]) -> bool:
    blob = _recursive_text(item).casefold()
    return "windows" in blob or "microsoft windows" in blob


def detect_os_family(item: dict[str, Any]) -> str:
    blob = _recursive_text(item).casefold()
    if "windows" in blob or "microsoft" in blob:
        return "windows"
    linux_markers = ("linux", "ubuntu", "debian", "red hat", "rhel", "centos", "rocky", "alma", "suse")
    if any(marker in blob for marker in linux_markers):
        return "linux"
    return "unknown"


def normalize_asset(item: dict[str, Any], asset_type: str = "computer", *, include_raw: bool = False) -> dict[str, Any]:
    normalized = {
        "id": item.get("id"),
        "asset_type": resolve_asset_type(asset_type),
        "name": item.get("name", ""),
        "os_family": detect_os_family(item),
        "operating_system": _value_to_text(
            item.get("operating_system")
            or item.get("operatingsystems_id")
            or item.get("operating_system_name")
        ),
        "os_version": _value_to_text(
            item.get("os_version")
            or item.get("operating_system_version")
            or item.get("operatingsystemversions_id")
            or item.get("operating_system_version_name")
        ),
        "serial": item.get("serial", ""),
        "asset_tag": item.get("otherserial", ""),
        "uuid": item.get("uuid", ""),
        "location": _value_to_text(item.get("locations_id")),
        "status": _value_to_text(item.get("states_id")),
        "manufacturer": _value_to_text(item.get("manufacturers_id")),
        "model": _value_to_text(item.get("computermodels_id") or item.get("networkequipmentmodels_id")),
        "updated": item.get("date_mod", ""),
        "networks": extract_network_rows(item),
        "storage": extract_storage_rows(item),
        "software": extract_software_rows(item),
    }
    if include_raw:
        normalized["raw"] = item
    return normalized


def extract_network_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def visit(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            path_text = " ".join(path).casefold()
            keys = {str(key).casefold() for key in value}
            networkish = any(marker in path_text for marker in ("network", "ethernet", "wifi", "ipaddress"))
            networkish = networkish or bool(keys & {"mac", "ip", "ipaddress", "ip_address"})
            if networkish:
                ip = _first_value(value, "ip", "ipaddress", "ip_address", "name") if "ip" in path_text else _first_value(value, "ip", "ipaddress", "ip_address")
                mac = _first_value(value, "mac", "mac_address")
                name = _first_value(value, "name", "ifname", "port", "logical_number")
                if ip or mac:
                    key = (name, ip, mac)
                    if key not in seen:
                        seen.add(key)
                        rows.append({
                            "name": name,
                            "ip": ip,
                            "mac": mac,
                            "type": _first_value(value, "instantiation_type", "type"),
                            "speed": _first_value(value, "speed"),
                            "vlan": _first_value(value, "vlan", "vlans_id"),
                        })
            for key, child in value.items():
                visit(child, (*path, str(key)))
        elif isinstance(value, list):
            for child in value:
                visit(child, path)

    visit(item, ())
    return rows


def extract_storage_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def visit(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            path_text = " ".join(path).casefold()
            storageish = any(marker in path_text for marker in ("disk", "harddrive", "volume", "filesystem", "storage"))
            if storageish:
                name = _first_value(value, "name", "designation", "device", "mountpoint", "mount_point")
                total = _first_value(value, "totalsize", "total_size", "capacity", "size")
                free = _first_value(value, "freesize", "free_size", "free")
                if name or total or free:
                    key = (name, total, free)
                    if key not in seen:
                        seen.add(key)
                        rows.append({
                            "name": name,
                            "type": _first_value(value, "type", "interfacetypes_id", "filesystems_id"),
                            "total": total,
                            "free": free,
                            "mount": _first_value(value, "mountpoint", "mount_point"),
                            "filesystem": _first_value(value, "filesystem", "filesystems_id"),
                            "serial": _first_value(value, "serial"),
                        })
            for key, child in value.items():
                visit(child, (*path, str(key)))
        elif isinstance(value, list):
            for child in value:
                visit(child, path)

    visit(item, ())
    return rows


def extract_software_rows(computer: dict[str, Any]) -> list[dict[str, Any]]:
    installed_on = str(computer.get("name") or computer.get("id") or "")
    candidates = _find_software_candidates(computer)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for candidate in candidates:
        display_name = _first_value(
            candidate,
            "Display name",
            "display_name",
            "name",
            "software_name",
            "softwares_id",
            "Software",
            "software",
        )
        version = _first_value(
            candidate,
            "Version",
            "version",
            "softwareversions_id",
            "SoftwareVersion",
            "software_version",
        )
        discovery_model = _first_value(
            candidate,
            "Discovery model",
            "discovery_model",
            "discoverymodels_id",
            "inventorymodels_id",
            "model",
            "source",
        )
        updated = _first_value(candidate, "Updated", "date_mod", "updated", "date_update", "date_creation")

        if not display_name:
            continue

        key = (display_name, version, installed_on)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "Display name": display_name,
            "Version": version,
            "Discovery model": discovery_model,
            "Installed on": installed_on,
            "Updated": updated,
        })

    return rows


def _find_software_candidates(value: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def visit(current: Any, path: tuple[str, ...]) -> None:
        if isinstance(current, dict):
            lowered_path = " ".join(path).casefold()
            has_software_key = any("software" in str(key).casefold() for key in current)
            has_versionish_value = any(str(key).casefold() in {"version", "softwareversions_id"} for key in current)
            if "software" in lowered_path and (has_software_key or "name" in current or has_versionish_value):
                candidates.append(current)
            for key, child in current.items():
                visit(child, (*path, str(key)))
        elif isinstance(current, list):
            for child in current:
                visit(child, path)

    visit(value, ())
    return candidates


def _first_value(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key not in item:
            continue
        value = item.get(key)
        text = _value_to_text(value)
        if text:
            return text
    return ""


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("name", "completename", "display_name", "version", "id"):
            if key in value and value[key] not in (None, ""):
                return str(value[key])
        return ""
    if isinstance(value, list):
        return ", ".join(_value_to_text(item) for item in value if _value_to_text(item))
    return str(value)


def _recursive_text(value: Any) -> str:
    parts: list[str] = []

    def visit(current: Any) -> None:
        if isinstance(current, dict):
            for key, child in current.items():
                parts.append(str(key))
                visit(child)
        elif isinstance(current, list):
            for child in current:
                visit(child)
        elif current is not None:
            parts.append(str(current))

    visit(value)
    return " ".join(parts)


def find_first_date_value(item: dict[str, Any], fields: list[str]) -> tuple[str | None, str | None]:
    for field in fields:
        direct = _get_path(item, field)
        if direct not in (None, ""):
            return _value_to_text(direct), field

    lowered_fields = {field.casefold() for field in fields}
    found: tuple[str | None, str | None] = (None, None)

    def visit(value: Any, path: str) -> None:
        nonlocal found
        if found[0] is not None:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                full_path = f"{path}.{key_text}" if path else key_text
                if key_text.casefold() in lowered_fields and child not in (None, ""):
                    found = (_value_to_text(child), full_path)
                    return
                visit(child, full_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(item, "")
    return found


def parse_glpi_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d",
    ]
    normalized = text.replace("Z", "+00:00")
    for fmt in formats:
        try:
            parsed = datetime.strptime(normalized, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def find_first_text_value(item: dict[str, Any], fields: list[str]) -> tuple[str | None, str | None]:
    """Find a deployment-specific field without requiring a fixed GLPI schema."""
    for field in fields:
        direct = _get_path(item, field)
        if direct not in (None, ""):
            return _value_to_text(direct), field

    lowered_fields = {_canonical_field_name(field) for field in fields}
    found: tuple[str | None, str | None] = (None, None)

    def visit(value: Any, path: str) -> None:
        nonlocal found
        if found[0] is not None:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                full_path = f"{path}.{key_text}" if path else key_text
                if _canonical_field_name(key_text) in lowered_fields and child not in (None, ""):
                    found = (_value_to_text(child), full_path)
                    return
                visit(child, full_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(item, "")
    return found


def _canonical_field_name(value: str) -> str:
    """Compare GLPI keys independent of case, hyphens, underscores, or spaces."""
    return "".join(character for character in value.casefold() if character.isalnum())


def _get_path(item: Any, path: str) -> Any:
    current = item
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
            continue
        return None
    return current

