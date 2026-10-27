import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "router_doctor", ROOT / "skills" / "router-doctor" / "scripts" / "router_doctor.py")
rd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rd)


def stats(median, jitter=1.0, loss=0.0):
    return {"median_ms": median, "jitter_ms": jitter, "loss_pct": loss}


class PingTest(unittest.TestCase):
    def test_parses_unix_and_windows(self):
        unix = "64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=2.31 ms\n" \
               "64 bytes from 192.168.1.1: icmp_seq=2 ttl=64 time=4.31 ms\n"
        win = "Reply from 192.168.1.1: bytes=32 time<1ms TTL=64\n" \
              "Reply from 1.1.1.1: bytes=32 time=14ms TTL=57\n"
        self.assertEqual(rd.parse_ping(unix), [2.31, 4.31])
        self.assertEqual(rd.parse_ping(win), [0.5, 14.0])

    def test_link_stats(self):
        s = rd.link_stats([10.0, 20.0, 10.0], sent=4)
        self.assertEqual(s, {"median_ms": 10.0, "jitter_ms": 10.0, "loss_pct": 25.0})
        self.assertEqual(rd.link_stats([], 5)["loss_pct"], 100.0)


class ScanTest(unittest.TestCase):
    def test_nmcli_with_escaped_colon(self):
        nets = rd.parse_nmcli("*:Home\\:Net:6:70\n :Neighbour:149:40\n :bad:line\n")
        self.assertEqual(nets[0], {"ssid": "Home:Net", "channel": 6, "band": "2.4",
                                   "signal": 70, "current": True})
        self.assertEqual(nets[1]["band"], "5")
        self.assertEqual(len(nets), 2)

    def test_netsh(self):
        text = "SSID 1 : Cafe\n    Network type : Infrastructure\n" \
               "    BSSID 1 : aa:bb\n         Signal : 81%\n         Channel : 11\n"
        self.assertEqual(rd.parse_netsh(text), [{"ssid": "Cafe", "channel": 11, "band": "2.4",
                                                 "signal": 81, "current": False}])

    def test_system_profiler(self):
        data = {"SPAirPortDataType": [{"spairport_airport_interfaces": [{
            "spairport_current_network_information": {
                "_name": "Home", "spairport_network_channel": "6 (2GHz, 20MHz)",
                "spairport_signal_noise": "-55 dBm / -90 dBm"},
            "spairport_airport_other_local_wireless_networks": [
                {"_name": "Six", "spairport_network_channel": "37 (6GHz, 160MHz)"}],
        }]}]}
        nets = rd.parse_system_profiler(data)
        self.assertEqual(nets[0]["signal"], -55)
        self.assertTrue(nets[0]["current"])
        self.assertEqual(nets[1]["band"], "6")


class AnalysisTest(unittest.TestCase):
    def test_congestion_picks_clear_channel_and_skips_own(self):
        nets = [{"ssid": "me", "channel": 6, "band": "2.4", "signal": 90, "current": True}]
        nets += [{"ssid": f"n{i}", "channel": 6, "band": "2.4", "signal": 80, "current": False} for i in range(3)]
        nets += [{"ssid": "x", "channel": 1, "band": "2.4", "signal": 30, "current": False}]
        c = rd.congestion(nets)["2.4"]
        self.assertEqual(c["best"][0], 11)
        self.assertEqual(c["current_channel"], 6)
        self.assertAlmostEqual(c["scores"][6], 2.4, places=2)
        recs = rd.recommendations("wifi_link", rd.congestion(nets))
        self.assertTrue(any("channel 6 is crowded; channel 11" in r for r in recs))

    def test_verdict_order(self):
        self.assertEqual(rd.verdict(stats(45), stats(60), 20), "wifi_link")
        self.assertEqual(rd.verdict(stats(3, loss=5.0), stats(20), 20), "wifi_link")
        self.assertEqual(rd.verdict(stats(3), stats(120), 20), "isp_or_upstream")
        self.assertEqual(rd.verdict(stats(3), stats(20), 400), "dns")
        self.assertEqual(rd.verdict(stats(3), stats(20), 20), "healthy")
        silent = rd.link_stats([], 5)
        self.assertEqual(rd.verdict(silent, stats(20), 20), "healthy")  # router drops ping
        self.assertEqual(rd.verdict(silent, stats(120), 20), "isp_or_upstream")
        self.assertEqual(rd.verdict(silent, silent, None), "no_data")
        self.assertIn("home network", rd.recommendations("no_data", {})[0])

    def test_upstream_tells_user_router_is_not_the_problem(self):
        recs = rd.recommendations("isp_or_upstream", rd.congestion([]))
        self.assertIn("upstream", recs[0])

    def test_eero_advice_is_app_steps_without_channel_picks(self):
        on24 = {"ssid": "home", "channel": 6, "band": "2.4", "signal": 60, "current": True}
        recs = rd.eero_recommendations("wifi_link", on24)
        self.assertTrue(any("2.4 GHz" in r for r in recs))
        self.assertTrue(any("eero app" in r for r in recs))
        self.assertFalse(any("channel 1" in r or "channel 11" in r for r in recs))
        self.assertIn("speed test", rd.eero_recommendations("isp_or_upstream")[0])
        self.assertIn("home network", rd.eero_recommendations("no_data")[0])

    def test_watch_blames_wifi_when_router_spikes_with_internet(self):
        s = [{"gw": 3.0, "net": 15.0}] * 20
        s[5] = {"gw": 180.0, "net": 210.0}
        s[12] = {"gw": None, "net": None}
        out = rd.summarize_watch(s)
        self.assertEqual(out["cause"], "wifi_link")
        self.assertEqual(out["gateway"]["drops"], 1)
        self.assertEqual(out["internet"]["spikes"], 2)

    def test_watch_blames_upstream_when_router_is_clean(self):
        s = [{"gw": 3.0, "net": 15.0}] * 20
        s[5] = {"gw": 3.0, "net": 240.0}
        s[9] = {"gw": 3.0, "net": None}
        self.assertEqual(rd.summarize_watch(s)["cause"], "isp_or_upstream")

    def test_watch_stable_and_no_data(self):
        self.assertEqual(rd.summarize_watch([{"gw": 3.0, "net": 15.0}] * 10)["cause"], "stable")
        self.assertEqual(rd.summarize_watch([{"gw": None, "net": None}] * 3)["cause"], "no_data")
        self.assertEqual(rd.summarize_watch([])["cause"], "no_data")

    def test_keychain_cmd_never_takes_password_argument(self):
        for os_name in ("Darwin", "Linux", "Windows"):
            cmd = rd.keychain_cmd("admin", os_name)
            self.assertIn(rd.KEYCHAIN_SERVICE, cmd)
            self.assertNotIn("hunter2", cmd)
        self.assertTrue(rd.keychain_cmd("admin", "Darwin").endswith("-w"))


if __name__ == "__main__":
    unittest.main()
