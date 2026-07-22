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

    def test_load_payload_includes_runtime_options_when_provided(self):
        payload = main.build_load_payload("llama3.2:3b", {"num_ctx": 8192})

        self.assertEqual(payload["model"], "llama3.2:3b")
        self.assertEqual(payload["prompt"], "")
        self.assertEqual(payload["keep_alive"], -1)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["options"], {"num_ctx": 8192})

    def test_load_payload_omits_empty_runtime_options(self):
        payload = main.build_load_payload("llama3.2:3b", {})

        self.assertNotIn("options", payload)

    def test_runtime_options_accept_model_context_up_to_hard_limit(self):
        options = main.RuntimeOptions(
            temperature=None,
            top_p=None,
            top_k=None,
            repeat_penalty=None,
            num_ctx=262144,
            seed=None,
        )

        self.assertEqual(options.num_ctx, 262144)

    def test_runtime_options_reject_unbounded_context(self):
        with self.assertRaises(Exception):
            main.RuntimeOptions(
                temperature=None,
                top_p=None,
                top_k=None,
                repeat_penalty=None,
                num_ctx=262145,
                seed=None,
            )

    def test_extract_context_length_from_model_info(self):
        show = {
            "model_info": {
                "llama.context_length": 4096,
                "general.architecture": "llama",
            }
        }

        result = main.extract_model_context_length(show)

        self.assertEqual(result["context_length"], 4096)
        self.assertEqual(result["context_source"], "model_info.llama.context_length")

    def test_extract_context_length_finds_architecture_specific_key(self):
        show = {
            "model_info": {
                "qwen2.context_length": 32768,
                "general.architecture": "qwen2",
            }
        }

        result = main.extract_model_context_length(show)

        self.assertEqual(result["context_length"], 32768)
        self.assertEqual(result["context_source"], "model_info.qwen2.context_length")

    def test_extract_context_length_returns_none_when_unknown(self):
        result = main.extract_model_context_length({"model_info": {}})

        self.assertIsNone(result["context_length"])
        self.assertEqual(result["context_source"], "unknown")

    def test_build_model_metadata_response_includes_context(self):
        show = {"model_info": {"llama.context_length": 8192}}

        result = main.build_model_metadata_response(11434, "llama3.2:3b", show)

        self.assertEqual(result["port"], 11434)
        self.assertEqual(result["model"], "llama3.2:3b")
        self.assertEqual(result["context_length"], 8192)
        self.assertEqual(result["context_source"], "model_info.llama.context_length")


if __name__ == "__main__":
    unittest.main()
