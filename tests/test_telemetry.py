import unittest

import main


class TelemetryTests(unittest.TestCase):
    def test_system_telemetry_shape(self):
        telemetry = main.get_system_telemetry()

        self.assertIn("cpu", telemetry)
        self.assertIn("memory", telemetry)
        self.assertIn("swap", telemetry)
        self.assertIn("ollama_processes", telemetry)
        self.assertGreaterEqual(telemetry["cpu"]["cores"], 1)
        self.assertGreaterEqual(telemetry["memory"]["total"], 0)
        self.assertGreaterEqual(telemetry["memory"]["used"], 0)
        self.assertGreaterEqual(telemetry["ollama_processes"], 0)


if __name__ == "__main__":
    unittest.main()
