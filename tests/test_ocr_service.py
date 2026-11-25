import base64
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



def response(text, status="completed", reason=None):
    return SimpleNamespace(
        output_text=text,
        status=status,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        usage=SimpleNamespace(input_tokens=100, output_tokens=10, total_tokens=110),
    )


class ImageTilingTests(unittest.TestCase):
    def test_default_overlap_and_order(self):
        image = Image.new("RGB", (2160, 2880))
        tiles = list(ocr.iter_image_tiles(image))
        self.assertEqual([box for box, _ in tiles], [
            (0, 0, 1242, 1656), (918, 0, 2160, 1656),
            (0, 1224, 1242, 2880), (918, 1224, 2160, 2880),
        ])
        self.assertEqual([tile.size for _, tile in tiles], [(1242, 1656)] * 4)

    def test_odd_dimensions_coverage_and_bounds(self):
        image = Image.new("RGB", (11, 7))
        for overlap in (0, 0.15, 0.95):
            with self.subTest(overlap=overlap):
                tiles = list(ocr.iter_image_tiles(image, 2, 3, overlap))
                self.assertEqual(len(tiles), 6)
                covered = set()
                for (left, top, right, bottom), tile in tiles:
                    self.assertTrue(0 <= left < right <= 11)
                    self.assertTrue(0 <= top < bottom <= 7)
                    self.assertEqual(tile.size, (right - left, bottom - top))
                    covered.update((x, y) for x in range(left, right) for y in range(top, bottom))
                self.assertEqual(len(covered), 77)

    def test_grid_larger_than_image_is_rejected(self):
        with self.assertRaises(ValueError):
            list(ocr.iter_image_tiles(Image.new("RGB", (1, 2))))


class TiledOcrTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        ocr._OCR_CACHE.clear()
        self.addCleanup(ocr._OCR_CACHE.clear)
        self.client = Mock()
        client = patch.object(ocr, "_get_client", return_value=self.client)
        client.start()
        self.addCleanup(client.stop)
        self.create = self.client.responses.create
        self.image = Image.new("RGB", (240, 320))
        self.data = self.image_bytes(self.image)

    @staticmethod
    def image_bytes(image, **kwargs):
        buffer = BytesIO()
        image.save(buffer, "PNG", **kwargs)
        return buffer.getvalue()

    def request_images(self):
        for call in self.create.call_args_list:
            content = call.kwargs["input"][0]["content"]
            if isinstance(content, list):
                item = content[1]
                self.assertEqual(item["detail"], ocr.OCR_IMAGE_DETAIL)
                self.assertEqual(call.kwargs["max_output_tokens"], 2048)
                with Image.open(BytesIO(base64.b64decode(item["image_url"].split(",", 1)[1]))) as image:
                    yield image.copy()

    def test_single_request_and_downscale_flag(self):
        os.environ.update(CHOOSE_AI_PARSER_ENABLED="false", CHOOSE_OCR_MAX_IMAGE_SIZE="160")
        self.create.return_value = response(" Steak\nFish ")
        self.assertEqual(ocr.extract_options_result_from_bytes(self.data).ocr_text, "Steak\nFish")
        self.assertEqual(self.create.call_count, 1)
        self.assertEqual([image.size for image in self.request_images()], [(120, 160)])

        os.environ["CHOOSE_OCR_DOWNSCALE_ENABLED"] = "false"
        self.create.reset_mock()
        self.assertFalse(ocr.extract_options_result_from_bytes(self.data).cache_hit)
        self.assertEqual([image.size for image in self.request_images()], [(240, 320)])

    def test_tiling_precedes_resize_and_never_upscales(self):
        os.environ["CHOOSE_OCR_TILING_ENABLED"] = "true"
        self.create.return_value = response("Name")
        for enabled, limit, expected in [
            ("true", "92", (69, 92)),
            ("true", "200", (138, 184)),
            ("false", "92", (138, 184)),
        ]:
            with self.subTest(enabled=enabled, limit=limit):
                self.create.reset_mock()
                os.environ.update(CHOOSE_OCR_DOWNSCALE_ENABLED=enabled, CHOOSE_OCR_MAX_IMAGE_SIZE=limit)
                ocr.extract_text_from_pil(self.image)
                self.assertEqual([image.size for image in self.request_images()], [expected] * 4)

    def test_exif_and_rgb_before_tiling(self):
        image = Image.new("L", (4, 2), 255)
        image.paste(0, (0, 0, 2, 2))
        exif = image.getexif()
        exif[274] = 6
        data = self.image_bytes(image, exif=exif)
        os.environ.update(CHOOSE_OCR_TILING_ENABLED="true", CHOOSE_OCR_TILE_ROWS="2",
                          CHOOSE_OCR_TILE_COLS="1", CHOOSE_OCR_TILE_OVERLAP="0",
                          CHOOSE_AI_PARSER_ENABLED="false")
        self.create.return_value = response("Name")
        ocr.extract_options_result_from_bytes(data)
        tiles = list(self.request_images())
        self.assertEqual([(tile.mode, tile.size) for tile in tiles], [("RGB", (2, 2))] * 2)
        self.assertEqual([tile.getpixel((0, 0)) for tile in tiles], [(0, 0, 0), (255, 255, 255)])

    def test_merge_is_verbatim_and_parser_runs_once(self):
        os.environ["CHOOSE_OCR_TILING_ENABLED"] = "true"
        texts = [" Steak\nFish ", "", "Tea\n" + "x" * 3100, "Soup"]
        self.create.side_effect = [response(text) for text in texts] + [response("Steak\nFish\nSteak")]
        result = ocr.extract_options_result_from_bytes(self.data)
        self.assertEqual(self.create.call_count, 5)
        self.assertEqual(len(list(self.request_images())), 4)
        self.assertEqual(result.ocr_text, "\n\n".join(texts))
        self.assertEqual(self.create.call_args.kwargs["input"][1]["content"], result.ocr_text)
        self.assertEqual(result.options, ["Steak", "Fish"])

    def test_parser_disabled_and_fallback_preserve_exact_deduplication(self):
        os.environ["CHOOSE_OCR_TILING_ENABLED"] = "true"
        for enabled, calls, source in [
            ("false", 4, "rule_parser"),
            ("true", 5, "rule_parser_fallback"),
        ]:
            with self.subTest(enabled=enabled):
                os.environ["CHOOSE_AI_PARSER_ENABLED"] = enabled
                self.create.reset_mock()
                self.create.side_effect = [response(name) for name in ("Steak", "Tea", "Steak", "Fish")]
                if enabled == "true":
                    self.create.side_effect = [response("Steak\nTea")] * 4 + [RuntimeError("parser failure")]
                result = ocr.extract_options_result_from_bytes(self.data)
                self.assertEqual(self.create.call_count, calls)
                self.assertEqual(result.source, source)
                self.assertEqual(result.options, ["Steak", "Tea", "Fish"] if enabled == "false" else ["Steak", "Tea"])

    def test_failed_tile_stops_without_parsing_or_caching(self):
        os.environ["CHOOSE_OCR_TILING_ENABLED"] = "true"
        for failure in (RuntimeError("API failure"), response("partial", "incomplete", "max_output_tokens")):
            with self.subTest(failure=failure):
                self.create.reset_mock()
                self.create.side_effect = [response("Steak"), failure]
                with self.assertLogs(ocr.logger, level="INFO") as logs:
                    with self.assertRaisesRegex(ocr.IncompleteTiledOcrError, "tile=2/4"):
                        ocr.extract_options_result_from_bytes(self.data)
                self.assertIn("succeeded=1 empty=0 failed=1 unattempted=2", "\n".join(logs.output))
                self.assertEqual(self.create.call_count, 2)
                self.assertFalse(ocr._OCR_CACHE)
        self.create.side_effect = [response("Fish")] * 5
        self.assertFalse(ocr.extract_options_result_from_bytes(self.data).cache_hit)

    def test_cache_isolation_for_each_preprocessing_setting(self):
        os.environ["CHOOSE_AI_PARSER_ENABLED"] = "false"
        self.create.return_value = response("Name")
        for settings, calls in [
            ({}, 1),
            ({"CHOOSE_OCR_TILING_ENABLED": "true"}, 4),
            ({"CHOOSE_OCR_TILE_ROWS": "3"}, 6),
            ({"CHOOSE_OCR_TILE_COLS": "3"}, 9),
            ({"CHOOSE_OCR_TILE_OVERLAP": "0"}, 9),
            ({"CHOOSE_OCR_DOWNSCALE_ENABLED": "false"}, 9),
            ({"CHOOSE_OCR_MAX_IMAGE_SIZE": "160"}, 9),
        ]:
            with self.subTest(settings=settings):
                os.environ.update(settings)
                self.create.reset_mock()
                self.assertFalse(ocr.extract_options_result_from_bytes(self.data).cache_hit)
                self.assertTrue(ocr.extract_options_result_from_bytes(self.data).cache_hit)
                self.assertEqual(self.create.call_count, calls)

    def test_invalid_configuration_rejected_before_api_call(self):
        for name, values in {
            "CHOOSE_OCR_TILE_ROWS": ["0", "1.5", "5"],
            "CHOOSE_OCR_TILE_COLS": ["-1", "bad"],
            "CHOOSE_OCR_TILE_OVERLAP": ["-0.1", "1", "nan", "inf"],
            "CHOOSE_OCR_MAX_IMAGE_SIZE": ["0", "-1", "bad"],
        }.items():
            for value in values:
                with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}):
                    with self.assertRaises(ValueError):
                        ocr.extract_options_result_from_bytes(self.data)
        self.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
