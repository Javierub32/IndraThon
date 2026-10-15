import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluate import reference_metrics, run, stability


class EvaluatorTests(unittest.TestCase):
    def fixture(self):
        mask = np.zeros((32, 32), bool)
        mask[8:16, 8:16] = True
        return {'mask': mask, 'active_fire': {'mask': mask}, 'original_size': {'width':64,'height':64}, 'analysis_size': {'width':32,'height':32}}

    def test_declared_original_grid_is_resampled_and_hashed(self):
        result = self.fixture()
        reference = np.zeros((64, 64), np.uint8)
        reference[16:32, 16:32] = 1
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.fromarray(reference).save(root / 'reference.png')
            spec = {'references': {'affected': {'path':'reference.png','grid':'original'}}}
            metrics = reference_metrics(spec, root, result)
            self.assertEqual(metrics['affected']['pixel']['iou'], 1)
            self.assertEqual(len(metrics['affected']['reference_sha256']), 64)
            self.assertEqual(metrics['active']['status'], 'not_provided')

    def test_bad_reference_grid_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.fromarray(np.zeros((64, 64), np.uint8)).save(root / 'reference.png')
            with self.assertRaises(ValueError):
                reference_metrics({'references': {'active': {'path':'reference.png','grid':'analysis'}}}, root, self.fixture())

    def test_empty_stability_is_explicit(self):
        value = stability(np.zeros((32,32), bool), np.zeros((16,16), bool))
        self.assertEqual(value['iou_self_consistency'], 1)
        self.assertTrue(value['both_empty'])

    def test_unseen_manifest_scene_runs_without_known_scene_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            swir = np.full((64,64,3), [50,180,40], np.uint8)
            swir[16:40, 16:40] = [150,65,50]
            Image.fromarray(swir).save(root / 'swir.png')
            Image.fromarray(np.full_like(swir, [80,110,60])).save(root / 'visible.png')
            reference = np.zeros((64,64), np.uint8)
            reference[16:40, 16:40] = 1
            Image.fromarray(reference).save(root / 'reference.png')
            manifest = {'config': {'max_side':256,'refine':False,'closing_radius':0,'pixel_size_m':20},
                        'scenes':[{'id':'unseen-fixture','split':'holdout','swir':'swir.png','true_color':'visible.png',
                                   'references':{'affected':{'path':'reference.png','grid':'original'}}}]}
            path = root / 'manifest.json'
            path.write_text(json.dumps(manifest), encoding='utf-8')
            report = run(path, root / 'output')
            self.assertEqual(report['scenes'][0]['metrics']['affected']['pixel']['iou'], 1)
            self.assertEqual(report['scenes'][0]['metrics']['active']['status'], 'not_provided')
            self.assertTrue((root / 'output' / 'report.md').exists())


if __name__ == '__main__':
    unittest.main()
