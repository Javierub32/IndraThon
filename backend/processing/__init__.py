"""Classical segmentation of rendered Sentinel-2 composites."""

from .pipeline import analyze
from .active_fire import ActiveFireConfig, detect_active_fire
from .segmentation import SegmentationConfig

__all__ = ["ActiveFireConfig", "SegmentationConfig", "analyze", "detect_active_fire"]
