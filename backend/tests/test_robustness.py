"""Regression controls; synthetic examples are not field accuracy evidence."""
import io
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from processing import SegmentationConfig, analyze
from processing.active_fire import detect_active_fire, ActiveFireConfig
from processing.evaluation import evaluate_mask, evaluate_components
from processing.features import extract_features
from processing.io import read_rgb
from processing.quality import inspect_pair
from processing.segmentation import segment


class RobustnessTests(unittest.TestCase):
    def test_uncertain_barrier_blocks_reconstruction(self):
        score = np.full((64, 64), .5, np.float32)
        score[10:15, 10:15] = .9
        unknown = np.zeros(score.shape, bool)
        unknown[:, 30:34] = True
        result = segment({'score': score, 'valid': np.ones_like(unknown), 'uncertain': unknown}, SegmentationConfig())
        self.assertTrue(result['grown'][20, 20])
        self.assertFalse(result['grown'][20, 45])
        self.assertFalse(result['candidates'][20, 31])

    def test_bright_soil_cannot_start_but_can_join_supported_scar(self):
        swir = np.full((64, 64, 3), [160, 65, 45], np.uint8)
        visible = np.full_like(swir, [200, 150, 100])
        config = SegmentationConfig(refine=False)
        first = segment(extract_features(swir, visible), config)
        self.assertFalse(first['grown'].any())
        visible[20:30, 20:30] = [75, 65, 50]
        second = segment(extract_features(swir, visible), config)
        self.assertTrue(second['grown'][45, 45])

    def test_common_background_palette_does_not_create_fire(self):
        # Paired illustrative colors, not learned labels for real land-cover classes.
        pairs = [([30, 150, 35], [50, 110, 40]), ([15, 20, 35], [20, 35, 65]),
                 ([150, 110, 80], [210, 170, 120]), ([180, 175, 170], [205, 205, 200]),
                 ([230, 230, 230], [245, 245, 245]), ([120, 150, 150], [180, 180, 180])]
        for swir_color, visible_color in pairs:
            with self.subTest(swir=swir_color):
                swir = np.full((128, 128, 3), [50, 180, 40], np.uint8)
                visible = np.full_like(swir, [80, 110, 60])
                swir[30:90, 30:90], visible[30:90, 30:90] = swir_color, visible_color
                result = analyze(swir, visible, SegmentationConfig(refine=False), active_fire=True)
                self.assertFalse(result['mask'].any())
                self.assertFalse(result['active_fire']['mask'].any())

    def test_uniform_red_scene_abstains_instead_of_claiming_all_burned(self):
        swir = np.full((128, 128, 3), [220, 50, 20], np.uint8)
        result = analyze(swir, np.full_like(swir, [100, 90, 70]), active_fire=True)
        self.assertTrue(result['uncertain'].all())
        self.assertFalse(result['mask'].any())
        self.assertFalse(result['active_fire']['mask'].any())
        self.assertEqual(result['quality']['status'], 'review_required')

    def test_context_rejects_uniform_red_and_keeps_small_hot_target(self):
        flat = np.full((128, 128, 3), [220, 80, 30], np.uint8)
        self.assertTrue(detect_active_fire(flat, config=ActiveFireConfig(contextual_filter=False))['mask'].all())
        self.assertFalse(detect_active_fire(flat)['mask'].any())
        swir = np.full_like(flat, [80, 70, 55])
        swir[60:63, 60:63] = [240, 100, 20]
        detected = detect_active_fire(swir)
        self.assertEqual(detected['stats']['hotspot_count'], 1)
        hidden = np.zeros((128, 128), bool)
        hidden[58:65, 58:65] = True
        self.assertFalse(detect_active_fire(swir, hidden)['mask'].any())

    def test_active_growth_is_bounded_to_two_four_neighbor_steps(self):
        swir = np.full((64, 64, 3), [80, 70, 55], np.uint8)
        swir[20:45, 20:45] = [120, 80, 50]
        swir[30:32, 30:32] = [230, 100, 20]
        result = detect_active_fire(swir)
        self.assertTrue(result['mask'][30, 28])
        self.assertFalse(result['mask'][30, 27])
        self.assertFalse(result['mask'][27, 27])

    def test_transparent_pixels_do_not_expose_hidden_rgb(self):
        rgba = np.full((64, 64, 4), [230, 60, 20, 0], np.uint8)
        rgba[10:20, 10:20, 3] = 255
        buffer = io.BytesIO()
        Image.fromarray(rgba).save(buffer, format='PNG')
        rgb, _ = read_rgb(buffer.getvalue())
        self.assertTrue((rgb[0, 0] == 0).all())
        self.assertTrue((rgb[15, 15] == [230, 60, 20]).all())

    def test_alignment_rejects_confident_spatial_shift(self):
        rng = np.random.default_rng(124)
        image = rng.integers(20, 230, (384, 384, 3), dtype=np.uint8)
        self.assertEqual(inspect_pair(image, image)['alignment']['status'], 'aligned')
        shifted = np.roll(image, 35, axis=1)
        with self.assertRaisesRegex(ValueError, 'desplazamiento'):
            inspect_pair(image, shifted)

    def test_metric_scale_uses_original_pixels_after_downsampling(self):
        swir = np.full((512, 512, 3), [50, 180, 40], np.uint8)
        swir[100:300, 100:300] = [150, 65, 50]
        visible = np.full_like(swir, [80, 110, 60])
        result = analyze(swir, visible, SegmentationConfig(max_side=256, refine=False), original_size=(1024, 1024))
        self.assertEqual(result['spatial_resolution']['analysis_pixel_m_x'], 80)
        expected = result['mask'].sum() * 16 * 400 / 10000
        self.assertAlmostEqual(result['stats']['affected_area_hectares_estimated'], expected, places=3)
        self.assertAlmostEqual(result['stats']['perimeter_m_estimated'], result['stats']['perimeter_original_pixels_estimated'] * 20, delta=.11)

    def test_metrics_reject_malformed_reference_and_score_disjoint_edges_zero(self):
        predicted = np.zeros((40, 40), np.uint8)
        predicted[5:12, 5:12] = 1
        reference = np.zeros_like(predicted)
        reference[25:32, 25:32] = 1
        self.assertEqual(evaluate_mask(predicted, reference)['boundary_f1'], 0)
        with self.assertRaises(ValueError):
            evaluate_mask(predicted, reference * 2)
        self.assertIsNone(evaluate_mask(predicted, np.full_like(reference, 255))['iou'])

    def test_component_matching_does_not_count_one_region_twice(self):
        predicted = np.zeros((40, 40), np.uint8)
        predicted[10:20, 5:30] = 1
        reference = np.zeros_like(predicted)
        reference[10:20, 5:12] = reference[10:20, 22:30] = 1
        metrics = evaluate_components(predicted, reference)
        self.assertEqual(metrics['matched'], 1)
        self.assertEqual(metrics['missed_components'], 1)
        self.assertEqual(evaluate_components(predicted, np.zeros_like(reference))['false_components'], 1)


if __name__ == '__main__':
    unittest.main()
