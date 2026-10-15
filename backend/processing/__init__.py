"""Classical segmentation of rendered Sentinel-2 composites."""

from .pipeline import analyze
from .segmentation import SegmentationConfig

__all__ = ["analyze", "SegmentationConfig"]
