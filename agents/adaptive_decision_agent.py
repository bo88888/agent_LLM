import math
import os
from typing import Any, Dict, List

import cv2
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import transform_bounds

from core.schema import ExecutionContext


VALID_MODES = {"auto", "force", "skip"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class AdaptiveDecisionAgent:
    """Generate explainable stage decisions before DecomposeAgent builds the DAG."""

    sample_size = 1024
    optical_low_contrast = _env_float("OPTICAL_LOW_CONTRAST", 0.20)
    optical_high_noise = _env_float("OPTICAL_HIGH_NOISE", 0.12)
    sar_high_speckle = _env_float("SAR_HIGH_SPECKLE", 0.55)

    @staticmethod
    def _mode(policy: Dict[str, Any], key: str) -> str:
        value = str(policy.get(key, "auto")).strip().lower()
        return value if value in VALID_MODES else "auto"

    @staticmethod
    def _bit_depth(dtype_name: str) -> int:
        try:
            return int(np.dtype(dtype_name).itemsize * 8)
        except TypeError:
            return 0

    @staticmethod
    def _sar_patch_cv(gray: np.ndarray) -> float:
        """Estimate speckle from relatively homogeneous 32x32 sample patches."""
        patch_size = 32
        candidates = []
        for y in range(0, gray.shape[0] - patch_size + 1, patch_size):
            for x in range(0, gray.shape[1] - patch_size + 1, patch_size):
                patch = gray[y:y + patch_size, x:x + patch_size].astype(np.float32)
                mean = float(np.mean(patch))
                if mean <= 5.0:
                    continue
                gradient = float(cv2.Laplacian(patch, cv2.CV_32F).var())
                cv = float(np.std(patch) / (mean + 1e-6))
                candidates.append((gradient, cv))
        if not candidates:
            return 0.0
        candidates.sort(key=lambda item: item[0])
        homogeneous = candidates[:max(1, len(candidates) // 3)]
        return float(np.median([item[1] for item in homogeneous]))

    def _inspect(self, path: str) -> Dict[str, Any]:
        with rasterio.open(path) as src:
            scale = max(
                src.width / self.sample_size,
                src.height / self.sample_size,
                1.0,
            )
            width = max(1, int(src.width / scale))
            height = max(1, int(src.height / scale))
            band_count = min(src.count, 3)
            image = src.read(
                indexes=list(range(1, band_count + 1)),
                out_shape=(band_count, height, width),
                resampling=Resampling.nearest,
                masked=True,
            ).filled(0).astype(np.float32)
            dtype_name = src.dtypes[0]
            source_width = src.width
            source_height = src.height
            has_crs = src.crs is not None
            has_transform = src.transform != Affine.identity()
            coordinates_valid = False
            bounds_wgs84 = None
            if has_crs and has_transform:
                try:
                    bounds_wgs84 = transform_bounds(
                        src.crs,
                        "EPSG:4326",
                        *src.bounds,
                        densify_pts=21,
                    )
                    left, bottom, right, top = bounds_wgs84
                    coordinates_valid = bool(
                        all(math.isfinite(v) for v in bounds_wgs84)
                        and -180 <= left < right <= 180
                        and -90 <= bottom < top <= 90
                    )
                except Exception:
                    bounds_wgs84 = None

        bit_depth = self._bit_depth(dtype_name)
        try:
            info = np.iinfo(np.dtype(dtype_name))
            dtype_range = float(info.max - info.min)
        except ValueError:
            dtype_range = 0.0

        contrast_values: List[float] = []
        normalized_bands = []
        for band in image:
            values = band[np.isfinite(band)]
            values = values[values != 0]
            if values.size < 32:
                continue
            p2, p98 = np.percentile(values, [2, 98])
            span = max(float(p98 - p2), 1e-6)
            denominator = dtype_range if dtype_range > 0 else max(abs(float(p98)), 1.0)
            contrast_values.append(min(span / denominator, 1.0))
            normalized_bands.append(
                np.clip((band - p2) / span * 255.0, 0, 255).astype(np.uint8)
            )

        if normalized_bands:
            gray = np.mean(np.stack(normalized_bands), axis=0).astype(np.uint8)
            median = cv2.medianBlur(gray, 3)
            residual = cv2.absdiff(gray, median)
            noise_score = float(np.percentile(residual, 90) / 255.0)
            sharpness = float(cv2.Laplacian(gray, cv2.CV_32F).var())
            speckle_cv = self._sar_patch_cv(gray)
        else:
            noise_score = 0.0
            sharpness = 0.0
            speckle_cv = 0.0

        return {
            "dtype": dtype_name,
            "bit_depth": bit_depth,
            "width": source_width,
            "height": source_height,
            "contrast_score": round(float(np.mean(contrast_values or [0.0])), 4),
            "noise_score": round(noise_score, 4),
            "sharpness_score": round(sharpness, 2),
            "speckle_cv": round(speckle_cv, 4),
            "has_crs": has_crs,
            "has_valid_transform": has_transform,
            "coordinates_valid": coordinates_valid,
            "bounds_wgs84": list(bounds_wgs84) if bounds_wgs84 else None,
            "geo_metadata_reliable": bool(has_crs and has_transform and coordinates_valid),
        }

    def _preprocess_decision(
        self,
        payloads: List[str],
        mode: str,
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        if mode == "force":
            return {"decision": "execute", "reason": "API策略强制执行预处理"}
        if mode == "skip":
            return {"decision": "skip", "reason": "API策略指定跳过预处理"}
        if not any(payload in {"OPTICAL", "SAR"} for payload in payloads):
            return {"decision": "skip", "reason": "当前载荷不需要视觉预处理"}

        reasons = []
        if metrics["bit_depth"] > 8:
            reasons.append(f"输入为{metrics['bit_depth']}bit，需要转换为检测模型输入")
        if "OPTICAL" in payloads:
            if metrics["contrast_score"] < self.optical_low_contrast:
                reasons.append(
                    f"对比度{metrics['contrast_score']:.4f}低于阈值{self.optical_low_contrast:.2f}"
                )
            if metrics["noise_score"] > self.optical_high_noise:
                reasons.append(
                    f"噪声{metrics['noise_score']:.4f}高于阈值{self.optical_high_noise:.2f}"
                )
        if "SAR" in payloads and metrics["speckle_cv"] > self.sar_high_speckle:
            reasons.append(
                f"相干斑系数{metrics['speckle_cv']:.4f}高于阈值{self.sar_high_speckle:.2f}"
            )

        return {
            "decision": "execute" if reasons else "skip",
            "reason": "；".join(reasons) if reasons else "位深、对比度和噪声满足直接检测条件",
        }

    @staticmethod
    def _geo_decision(
        mode: str,
        metrics: Dict[str, Any],
        need_spatial_fusion: bool,
    ) -> Dict[str, Any]:
        if mode == "force":
            return {"decision": "execute", "reason": "API策略强制执行几何精校正"}
        if mode == "skip":
            warning = ""
            if need_spatial_fusion and not metrics["geo_metadata_reliable"]:
                warning = "；当前坐标不可靠，空间融合结果需要复核"
            return {"decision": "skip", "reason": f"API策略指定跳过几何精校正{warning}"}
        if need_spatial_fusion and not metrics["geo_metadata_reliable"]:
            return {
                "decision": "execute",
                "reason": "任务要求空间融合，但CRS、仿射变换或经纬度范围不可靠",
            }
        return {"decision": "skip", "reason": "地理参考满足当前检测和融合要求"}

    def run(self, context: ExecutionContext) -> ExecutionContext:
        requirement = context.parsed_requirement
        policy = dict(requirement.get("execution_policy") or {})
        payloads = [str(item).upper() for item in requirement.get("payload_types", [])]
        need_spatial_fusion = bool(
            context.request.output_requirements.get("need_spatial_fusion", True)
        )

        try:
            metrics = self._inspect(context.request.tiff_path)
            error = ""
        except Exception as exc:
            metrics = {
                "bit_depth": 0,
                "contrast_score": 0.0,
                "noise_score": 0.0,
                "speckle_cv": 0.0,
                "geo_metadata_reliable": False,
            }
            error = str(exc)

        preprocess_mode = self._mode(policy, "preprocess")
        geo_mode = self._mode(policy, "geo_correction")
        preprocess = self._preprocess_decision(payloads, preprocess_mode, metrics)
        geometry = self._geo_decision(geo_mode, metrics, need_spatial_fusion)

        if error and preprocess_mode == "auto":
            preprocess = {
                "decision": "execute",
                "reason": f"影像评估失败，采用保守预处理策略：{error}",
            }
        if error and geo_mode == "auto" and need_spatial_fusion:
            geometry = {
                "decision": "execute",
                "reason": f"坐标评估失败且要求空间融合：{error}",
            }

        decisions = {
            "preprocess": preprocess,
            "geometry": geometry,
            "detection": {"decision": "execute", "reason": "目标检测为必选阶段"},
            "fusion": {
                "decision": "execute" if need_spatial_fusion else "skip",
                "reason": "任务要求空间融合" if need_spatial_fusion else "任务仅要求单源检测",
            },
        }
        requirement["stage_decisions"] = decisions
        context.metadata["image_assessment"] = metrics
        context.metadata["stage_decisions"] = decisions
        context.metadata["adaptive_policy"] = "quality_rule_v1"
        return context
