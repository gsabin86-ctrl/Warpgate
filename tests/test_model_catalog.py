import unittest

import main


class ModelCatalogTests(unittest.TestCase):
    def test_catalog_marks_target_installed_models(self):
        target = [
            {"name": "llama3.2:3b", "size": 2_000_000_000},
        ]
        by_port = {
            11434: target,
            11435: [{"name": "mistral:7b", "size": 4_400_000_000}],
        }
        catalog = main.build_model_catalog(11434, by_port, curated=["qwen2.5:7b"])
        by_name = {m["name"]: m for m in catalog["models"]}

        self.assertEqual(by_name["llama3.2:3b"]["availability"], "installed")
        self.assertTrue(by_name["llama3.2:3b"]["installed_on_target"])
        self.assertIn(11434, by_name["llama3.2:3b"]["available_ports"])

    def test_catalog_marks_models_not_on_target_as_needs_pull(self):
        by_port = {
            11434: [{"name": "llama3.2:3b", "size": 2_000_000_000}],
            11437: [],
        }
        catalog = main.build_model_catalog(11437, by_port, curated=["qwen2.5:7b"])
        by_name = {m["name"]: m for m in catalog["models"]}

        self.assertEqual(by_name["llama3.2:3b"]["availability"], "needs_pull")
        self.assertFalse(by_name["llama3.2:3b"]["installed_on_target"])
        self.assertIn(11434, by_name["llama3.2:3b"]["available_ports"])
        self.assertEqual(by_name["qwen2.5:7b"]["availability"], "needs_pull")
        self.assertEqual(by_name["qwen2.5:7b"]["available_ports"], [])

    def test_model_names_are_restricted_for_pull_endpoint(self):
        valid = [
            "llama3.2:3b",
            "fredrezones55/Qwen3.5-Uncensored-HauhauCS-Aggressive:4b",
            "hf.co/org/model:Q4_K_M",
        ]
        invalid = ["", "../bad", "bad model", "bad;rm -rf /", "http://example.com/model"]

        for name in valid:
            self.assertTrue(main.is_safe_model_name(name), name)
        for name in invalid:
            self.assertFalse(main.is_safe_model_name(name), name)


if __name__ == "__main__":
    unittest.main()
