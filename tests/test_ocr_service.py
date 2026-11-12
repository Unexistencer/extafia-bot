import os
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from service import ocr_service as ocr


class OptionParserTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        ocr._OCR_CACHE.clear()
        self.addCleanup(ocr._OCR_CACHE.clear)
        image = BytesIO()
        Image.new("RGB", (2, 2)).save(image, format="PNG")
        self.data = image.getvalue()
        self.client = Mock()
        self.client.responses.create.side_effect = [
            SimpleNamespace(output_text="Steak\n200g\n1200 yen\nChicken\nFish"),
            SimpleNamespace(output_text="1. Steak\n2. Chicken\n3. Fish"),
        ]
        client_patch = patch.object(ocr, "_get_client", return_value=self.client)
        client_patch.start()
        self.addCleanup(client_patch.stop)

    def run_parser(self, **kwargs):
        return ocr.extract_options_result_from_bytes(self.data, **kwargs)

    def test_default_ai_success_even_with_many_rule_options(self):
        with patch.object(ocr, "parse_options_from_text", wraps=ocr.parse_options_from_text) as parser:
            result = self.run_parser()
        self.assertEqual(result.options, ["Steak", "Chicken", "Fish"])
        self.assertEqual(result.source, "ai_parser")
        self.assertEqual(self.client.responses.create.call_count, 2)
        parser.assert_called_once_with("1. Steak\n2. Chicken\n3. Fish")
        self.assertIn("input_image", str(self.client.responses.create.call_args_list[0]))

    def test_disabled_makes_only_ocr_api_call(self):
        os.environ["CHOOSE_AI_PARSER_ENABLED"] = "false"
        result = self.run_parser()
        self.assertEqual(result.source, "rule_parser")
        self.assertEqual(len(result.options), 5)
        self.assertEqual(self.client.responses.create.call_count, 1)

    def test_boolean_configuration(self):
        self.assertTrue(ocr._get_ai_parser_enabled())
        for value, expected in [(" TRUE ", True), ("False", False), ("", False), ("invalid", False), ("1", False)]:
            with self.subTest(value=value):
                os.environ["CHOOSE_AI_PARSER_ENABLED"] = value
                self.assertEqual(ocr._get_ai_parser_enabled(), expected)

    def test_empty_or_noise_ai_falls_back(self):
        for value in ["", "---\n***"]:
            with self.subTest(value=value):
                ocr._OCR_CACHE.clear()
                self.client.responses.create.side_effect = [SimpleNamespace(output_text="Steak\nFish"), SimpleNamespace(output_text=value)]
                result = self.run_parser()
                self.assertEqual(result.source, "rule_parser_fallback")
                self.assertEqual(result.options, ["Steak", "Fish"])

    def test_ai_failure_falls_back(self):
        self.client.responses.create.side_effect = [SimpleNamespace(output_text="Steak\nFish"), RuntimeError("API failure")]
        result = self.run_parser()
        self.assertEqual(result.source, "rule_parser_fallback")
        self.assertEqual(result.options, ["Steak", "Fish"])

    def test_empty_ocr_skips_ai(self):
        self.client.responses.create.side_effect = [SimpleNamespace(output_text="  \n")]
        result = self.run_parser()
        self.assertEqual(result.options, [])
        self.assertEqual(result.source, "rule_parser")
        self.assertEqual(self.client.responses.create.call_count, 1)

    def test_short_ocr_still_uses_ai(self):
        self.client.responses.create.side_effect = [SimpleNamespace(output_text="Tea"), SimpleNamespace(output_text="Tea")]
        self.assertEqual(self.run_parser().source, "ai_parser")
        self.assertEqual(self.client.responses.create.call_count, 2)

    def test_cache_mode_isolation_and_reuse(self):
        ai = self.run_parser()
        self.assertTrue(self.run_parser().cache_hit)
        os.environ["CHOOSE_AI_PARSER_ENABLED"] = "false"
        self.client.responses.create.side_effect = [SimpleNamespace(output_text="Steak\n200g\nFish")]
        rule = self.run_parser()
        self.assertFalse(rule.cache_hit)
        self.assertEqual(rule.source, "rule_parser")
        self.assertTrue(self.run_parser().cache_hit)
        os.environ["CHOOSE_AI_PARSER_ENABLED"] = "true"
        self.assertEqual(self.run_parser().options, ai.options)
        self.assertTrue(self.run_parser().cache_hit)
        self.assertEqual(self.client.responses.create.call_count, 3)

    def test_model_configuration_isolates_cache(self):
        original = ocr._cache_key("image")
        os.environ["OPEN_AI_FALLBACK_MODEL"] = "another-model"
        self.assertNotEqual(original, ocr._cache_key("image"))
        original = ocr._cache_key("image")
        os.environ["OPEN_AI_MODEL"] = "another-ocr-model"
        self.assertNotEqual(original, ocr._cache_key("image"))

    def test_legacy_opt_out_and_environment_precedence(self):
        self.run_parser()
        self.client.responses.create.side_effect = [SimpleNamespace(output_text="Steak\nFish")]
        result = self.run_parser(force_ai_fallback=False)
        self.assertFalse(result.cache_hit)
        self.assertEqual(result.source, "rule_parser")
        self.assertEqual(self.client.responses.create.call_count, 3)
        os.environ["CHOOSE_AI_PARSER_ENABLED"] = "false"
        self.assertTrue(self.run_parser(force_ai_fallback=True).cache_hit)
        self.assertFalse(ocr.should_use_ai_fallback("Tea", [], True))

    def test_compatibility_helper_ignores_option_count(self):
        self.assertTrue(ocr.should_use_ai_fallback("Tea", ["a", "b", "c"], True))
        self.assertFalse(ocr.should_use_ai_fallback("Tea", [], False))
        self.assertFalse(ocr.should_use_ai_fallback(" ", [], True))

    def test_ocr_failure_still_propagates(self):
        self.client.responses.create.side_effect = RuntimeError("OCR failure")
        with self.assertRaisesRegex(RuntimeError, "OCR failure"):
            self.run_parser()
        self.assertFalse(ocr._OCR_CACHE)


if __name__ == "__main__":
    unittest.main()
