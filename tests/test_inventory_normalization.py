import unittest

from glpi_asset_mcp.glpi_client import detect_os_family, find_first_text_value, normalize_asset
from glpi_asset_mcp.server import _asset_report_row, _discover_field_paths, _filter_normalized_assets, _markdown_table


SAMPLE = {
    "id": 42,
    "name": "srv-linux-01",
    "serial": "ABC123",
    "locations_id": {"name": "Shanghai DC"},
    "operating_system": {"name": "Ubuntu Linux 24.04"},
    "operatingsystemversions_id": {"name": "24.04"},
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
        self.assertEqual("Ubuntu Linux 24.04", asset["operating_system"])
        self.assertEqual("24.04", asset["os_version"])
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
        self.assertEqual("Ubuntu Linux 24.04", row["Operating system"])
        self.assertEqual("24.04", row["OS version"])

    def test_markdown_report_preview(self) -> None:
        markdown = _markdown_table([{"Name": "srv-01", "IP address": "10.0.0.1"}], ["Name", "IP address"])
        self.assertIn("| Name | IP address |", markdown)
        self.assertIn("| srv-01 | 10.0.0.1 |", markdown)

    def test_discovers_nested_field_paths(self) -> None:
        paths = _discover_field_paths(SAMPLE)
        self.assertIn("_networkports[].ipaddress", paths)
        self.assertIn("softwares[].version", paths)

    def test_finds_nested_agent_version(self) -> None:
        value, path = find_first_text_value(
            {"inventory": {"glpi_agent_version": "1.17"}},
            ["agent_version", "glpi_agent_version"],
        )
        self.assertEqual("1.17", value)
        self.assertEqual("inventory.glpi_agent_version", path)

    def test_finds_glpi_user_agent_aliases(self) -> None:
        value, path = find_first_text_value(
            {"inventory": {"User-Agent": "GLPI-Agent_v1.17-1"}},
            ["agent_version", "useragent", "versionclient"],
        )
        self.assertEqual("GLPI-Agent_v1.17-1", value)
        self.assertEqual("inventory.User-Agent", path)

        value, path = find_first_text_value(
            {"versionclient": "GLPI-Agent_v1.17-1"},
            ["agent_version", "useragent", "versionclient"],
        )
        self.assertEqual("GLPI-Agent_v1.17-1", value)
        self.assertEqual("versionclient", path)

    def test_agent_version_filter_matches_glpi_agent_suffix(self) -> None:
        agents = [
            {"agent_version": "GLPI-Agent_v1.17-1"},
            {"agent_version": "1.16"},
        ]
        matches = [agent for agent in agents if "1.17" in agent["agent_version"].casefold()]
        self.assertEqual([{"agent_version": "GLPI-Agent_v1.17-1"}], matches)


if __name__ == "__main__":
    unittest.main()

