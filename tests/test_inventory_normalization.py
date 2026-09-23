import unittest

from glpi_asset_mcp.glpi_client import detect_os_family, normalize_asset
from glpi_asset_mcp.server import _asset_report_row, _discover_field_paths, _filter_normalized_assets


SAMPLE = {
    "id": 42,
    "name": "srv-linux-01",
    "serial": "ABC123",
    "locations_id": {"name": "Shanghai DC"},
    "operating_system": {"name": "Ubuntu Linux 24.04"},
    "_networkports": [
        {"name": "eth0", "mac": "00:11:22:33:44:55", "ipaddress": "10.0.0.42", "speed": 1000}
    ],
    "disks": [
        {"name": "/", "totalsize": 102400, "freesize": 51200, "filesystem": "ext4"}
    ],
    "softwares": [
        {"name": "nginx", "version": "1.24.0", "date_mod": "2026-09-01"}
    ],
}


class InventoryNormalizationTests(unittest.TestCase):
    def test_extracts_full_inventory(self) -> None:
        asset = normalize_asset(SAMPLE)
        self.assertEqual("linux", detect_os_family(SAMPLE))
        self.assertEqual("10.0.0.42", asset["networks"][0]["ip"])
        self.assertEqual("00:11:22:33:44:55", asset["networks"][0]["mac"])
        self.assertEqual("102400", asset["storage"][0]["total"])
        self.assertEqual("nginx", asset["software"][0]["Display name"])

    def test_filters_by_os_ip_and_software(self) -> None:
        asset = normalize_asset(SAMPLE)
        result = _filter_normalized_assets([asset], {"os_family": "linux", "ip": "10.0.0", "software": "nginx"})
        self.assertEqual([asset], result)
        self.assertEqual([], _filter_normalized_assets([asset], {"os_family": "windows"}))

    def test_report_row_contains_summaries(self) -> None:
        row = _asset_report_row(normalize_asset(SAMPLE))
        self.assertEqual("10.0.0.42", row["IP addresses"])
        self.assertEqual("00:11:22:33:44:55", row["MAC addresses"])
        self.assertEqual(1, row["Software count"])
        self.assertIn("nginx", row["Software"])

    def test_discovers_nested_field_paths(self) -> None:
        paths = _discover_field_paths(SAMPLE)
        self.assertIn("_networkports[].ipaddress", paths)
        self.assertIn("softwares[].version", paths)


if __name__ == "__main__":
    unittest.main()
