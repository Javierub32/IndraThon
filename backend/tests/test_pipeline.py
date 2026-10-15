"""Run: python -m unittest discover -s backend/tests -v (from repository root)."""
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from processing import SegmentationConfig, analyze
from processing.geometry import clean_mask, extract_regions
from processing.segmentation import reconstruct
from processing.evaluation import evaluate_mask
from processing.io import read_rgb


class PipelineTests(unittest.TestCase):
    def test_reconstruction_rejects_unseeded_component(self):
        candidates = np.zeros((64, 64), bool)
        candidates[5:25, 5:25] = True
        candidates[40:50, 40:50] = True
        seeds = np.zeros_like(candidates)
        seeds[10, 10] = True
        result = reconstruct(seeds, candidates)
        self.assertTrue(result[20, 20])
        self.assertFalse(result[45, 45])

    def test_cleanup_preserves_large_holes_uncertainty_and_multiple_regions(self):
        mask = np.zeros((128, 128), bool)
        mask[5:65, 5:65] = True
        mask[80:120, 80:120] = True
        mask[20:45, 20:45] = False
        mask[10, 10] = False
        uncertain = np.zeros_like(mask)
        uncertain[50:55, 50:55] = True
        result = clean_mask(mask, np.ones_like(mask), uncertain,
                            SegmentationConfig(closing_radius=0, max_hole_fraction=.001))
        self.assertTrue(result[10, 10])
        self.assertFalse(result[30, 30])
        self.assertFalse(result[52, 52])
        self.assertTrue(result[90, 90])
        regions, _ = extract_regions(result, (256, 256))
        self.assertEqual(len(regions), 2)
        self.assertTrue(any(region['holes'] for region in regions))
        self.assertAlmostEqual(sum(r['area_original_pixels_estimated'] for r in regions), result.sum() * 4)

    def test_no_fire_and_detected_patch(self):
        swir = np.full((256, 256, 3), [50, 180, 40], dtype=np.uint8)
        true = np.full_like(swir, [80, 110, 60])
        config = SegmentationConfig(max_side=256, refine=False)
        empty = analyze(swir, true, config)
        self.assertEqual(empty['stats']['region_count'], 0)
        swir[70:150, 70:150] = [150, 65, 50]
        result = analyze(swir, true, config)
        self.assertEqual(result['stats']['region_count'], 1)
        self.assertTrue(result['mask'][100, 100])
        self.assertEqual(set(np.unique(result['labels'])), {0, 1})

    def test_mismatched_inputs_rejected(self):
        with self.assertRaises(ValueError):
            analyze(np.zeros((64, 64, 3), np.uint8), np.zeros((32, 32, 3), np.uint8))

    def test_decode_preserves_original_dimensions(self):
        buffer = io.BytesIO()
        Image.new('RGB', (800, 400), (120, 50, 40)).save(buffer, format='JPEG')
        rgb, size = read_rgb(buffer.getvalue(), max_side=256)
        self.assertEqual(size, (800, 400))
        self.assertEqual(rgb.shape, (128, 256, 3))
        with self.assertRaises(ValueError):
            read_rgb(b'not an image')

    def test_metrics_use_independent_reference_and_ignore_255(self):
        prediction = np.array([[1, 1], [0, 0]], dtype=np.uint8)
        reference = np.array([[1, 0], [1, 255]], dtype=np.uint8)
        metrics = evaluate_mask(prediction, reference)
        self.assertAlmostEqual(metrics['iou'], 1 / 3)
        self.assertAlmostEqual(metrics['dice'], .5)
        self.assertEqual(metrics['reference_valid_fraction'], .75)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main
        from fastapi.testclient import TestClient
        cls.main = main
        cls.client = TestClient(main.app)

    def test_health_validation_and_paths(self):
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        self.assertEqual(self.client.post('/api/scenes/unknown/analyze', json={}).status_code, 404)
        self.assertEqual(self.client.post('/api/scenes/niebla/analyze', json={'sensitivity': 2}).status_code, 422)
        self.assertEqual(self.client.get('/api/results/not-an-id/mask.png').status_code, 404)
        files = {'image1': ('bad.jpg', b'bad', 'image/jpeg'), 'image2': ('bad.jpg', b'bad', 'image/jpeg')}
        self.assertEqual(self.client.post('/api/process', files=files).status_code, 422)

    def test_upload_returns_downloadable_labels_and_geometry(self):
        swir = np.full((128, 128, 3), [50, 180, 40], np.uint8)
        swir[30:90, 30:90] = [150, 65, 50]
        visible = np.full_like(swir, [80, 110, 60])
        def png(array):
            buffer = io.BytesIO()
            Image.fromarray(array).save(buffer, format='PNG')
            return buffer.getvalue()
        files = {'image1': ('true.png', png(visible), 'image/png'), 'image2': ('swir.png', png(swir), 'image/png')}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            with patch.object(self.main, 'RESULTS', Path(directory)):
                response = self.client.post('/api/process', files=files, data={'max_side':256,'refine':'false'})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result['stats']['region_count'], 1)
                for url in result['assets'].values():
                    self.assertEqual(self.client.get(url).status_code, 200)
                mask = np.asarray(Image.open(io.BytesIO(self.client.get(result['assets']['labels']).content)))
                self.assertEqual(set(np.unique(mask)), {0, 1})
                self.assertEqual(self.client.get(result['assets']['regions']).json()['coordinate_system'], 'image_pixels')

    def test_original_size_mismatch_is_rejected_even_if_decode_sizes_match(self):
        def content(size):
            buffer = io.BytesIO()
            Image.new('RGB', size).save(buffer, format='PNG')
            return buffer.getvalue()
        files = {'image1': ('a.png', content((64,64)), 'image/png'),
                 'image2': ('b.png', content((128,128)), 'image/png')}
        self.assertEqual(self.client.post('/api/process', files=files).status_code, 422)

    def test_busy_analysis_is_explicit_and_result_deletion_is_bounded(self):
        from fastapi import HTTPException
        self.main.PROCESS_LOCK.acquire()
        try:
            with self.assertRaises(HTTPException) as caught:
                self.main.save_analysis(None, None, None, None, 'test')
            self.assertEqual(caught.exception.status_code, 409)
        finally:
            self.main.PROCESS_LOCK.release()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            root = Path(directory)
            (root / 'results').mkdir()
            outside = root / 'keep'
            outside.mkdir()
            with patch.object(self.main, 'RESULTS', root / 'results'):
                with self.assertRaises(ValueError):
                    self.main.remove_result(outside)
                self.assertTrue(outside.exists())


if __name__ == '__main__':
    unittest.main()
