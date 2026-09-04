import os
from typing import Any, Dict, List

import cv2
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import transform_bounds

from core.schema import ExecutionContext


VALID_STAGE_MODES = {"auto", "force", "skip"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class ImageAssessmentAgent:
    """Lightweight, explainable image assessment used before DAG generation.

    It does not replace offline validation. Thresholds are deliberately exposed as
    environment variables so they can be calibrated with the project's images.
    """

    max_sample_size = 1024
    optical_low_contrast = _env_float("OPTICAL_LOW_CONTRAST", 0.20)
    optical_high_noise = _env_float("OPTICAL_HIGH_NOISE", 0.12)
    sar_high_speckle = _env_float("SAR_HIGH_SPECKLE", 0.55)

    @staticmethod
    def _normalize_mode(value: Any, default: str = "auto") -> str:
        value = str(value or default).strip().lower()
        return value if value in VALID_STAGE_MODES else default

    @staticmethod
    def _dtype_bit_depth(dtype_name: str) -> int:
        try:
            return int(np.dtype(dtype_name).itemsize * 8)
        except TypeError:
            return 0

    def _read_metrics(self, path: str) -> Dict[str, Any]:
        with rasterio.open(path) as src:
            source_width = src.width
            source_height = src.height
            sample_scale = max(
                src.width / self.max_sample_size,
                src.height / self.max_sample_size,
                1.0,
            )
            sample_width = max(1, int(src.width / sample_scale))
            sample_height = max(1, int(src.height / sample_scale))
            band_count = min(src.count, 3)
            image = src.read(
                indexes=list(range(1, band_count + 1)),
                out_shape=(band_count, sample_height, sample_width),
                resampling=Resampling.nearest,
                masked=True,
            ).filled(0).astype(np.float32)

            dtype_name = src.dtypes[0]
            bit_depth = self._dtype_bit_depth(dtype_name)
            transform = src.transform
            has_crs = src.crs is not None
            has_transform = transform != Affine.identity()
            bounds_wgs84 = None
            coordinates_valid = False

            if has_crs and has_transform:
                try:
                    bounds_wgs84 = transform_bounds(
                        src.crs,
                        "EPSG:4326",
                        *src.bounds,
                        densify_pts=21,
                    )
                    left, bottom, right, top = bounds_wgs84
                    coordinates_valid = (
                        np.all(np.isfinite(bounds_wgs84))
                        and -180 <= left < right <= 180
                        and -90 <= bottom < top <= 90
                    )
                except Exception:
                    bounds_wgs84 = None

        contrast_scores: List[float] = []
        saturation_scores: List[float] = []
        normalized_bands = []

        try:
            dtype_info = np.iinfo(np.dtype(dtype_name))
            dtype_range = float(dtype_info.max - dtype_info.min)
        except ValueError:
            dtype_range = 0.0

        for band in image:
            values = band[np.isfinite(band)]
            values = values[values != 0]
            if values.size < 32:
                continue

            p2, p98 = np.percentile(values, [2, 98])
            span = max(float(p98 - p2), 1e-6)
            denominator = dtype_range if dtype_range > 0 else max(abs(float(p98)), 1.0)
            contrast_scores.append(min(span / denominator, 1.0))
            saturation_scores.append(
                float(np.mean((values <= p2) | (values >= p98)))
            )
            normalized_bands.append(
                np.clip((band - p2) / span * 255.0, 0, 255).astype(np.uint8)
            )

        if normalized_bands:
            gray = np.mean(np.stack(normalized_bands), axis=0).astype(np.uint8)
            median = cv2.medianBlur(gray, 3)
            residual = cv2.absdiff(gray, median)
            noise_score = float(np.percentile(residual, 90) / 255.0)
            blur_score = float(cv2.Laplacian(gray, cv2.CV_32F).var())
        else:
            gray = np.zeros((8, 8), dtype=np.uint8)
            noise_score = 0.0
            blur_score = 0.0

        positive = gray[gray > 0].astype(np.float32)
        if positive.size >= 32 and float(np.mean(positive)) > 0:
            speckle_cv = float(np.std(positive) / np.mean(positive))
        else:
            speckle_cv = 0.0

        return {
            "path": path,
            "dtype": dtype_name,
            "bit_depth": bit_depth,
            "width": int(source_width),
            "height": int(source_height),
            "contrast_score": round(float(np.mean(contrast_scores or [0.0])), 4),
            "noise_score": round(noise_score, 4),
            "blur_score": round(blur_score, 2),
            "saturation_ratio": round(float(np.mean(saturation_scores or [0.0])), 4),
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
            return {"stage": "preprocess", "decision": "execute", "reason": "用户强制执行预处理"}
        if mode == "skip":
            return {"stage": "preprocess", "decision": "skip", "reason": "用户指定跳过预处理"}

        reasons = []
        operations = []
        if metrics["bit_depth"] > 8:
            operations.append("quantization")
            reasons.append(f"输入为{metrics['bit_depth']}bit，检测模型使用8bit输入")

        if "OPTICAL" in payloads:
            if metrics["contrast_score"] < self.optical_low_contrast:
                operations.append("contrast_stretch")
                reasons.append(f"光学对比度{metrics['contrast_score']:.4f}低于阈值{self.optical_low_contrast:.2f}")
            if metrics["noise_score"] > self.optical_high_noise:
                operations.append("median_denoise")
                reasons.append(f"光学噪声{metrics['noise_score']:.4f}高于阈值{self.optical_high_noise:.2f}")

        if "SAR" in payloads and metrics["speckle_cv"] > self.sar_high_speckle:
            operations.append("lee_filter")
            reasons.append(f"SAR相干斑系数{metrics['speckle_cv']:.4f}高于阈值{self.sar_high_speckle:.2f}")

        if operations:
            return {
                "stage": "preprocess",
                "decision": "execute",
                "operations": sorted(set(operations)),
                "reason": "；".join(reasons),
            }
        return {
            "stage": "preprocess",
            "decision": "skip",
            "operations": [],
            "reason": "位深、对比度和噪声指标满足直接检测条件",
        }

    def _geo_decision(
        self,
        mode: str,
        metrics: Dict[str, Any],
        require_spatial_fusion: bool,
    ) -> Dict[str, Any]:
        if mode == "force":
            return {"stage": "geometry", "decision": "execute", "reason": "用户强制执行几何精校正"}
        if mode == "skip":
            warning = ""
            if require_spatial_fusion and not metrics["geo_metadata_reliable"]:
                warning = "；但影像地理信息不可靠，融合坐标可能不可用"
            return {"stage": "geometry", "decision": "skip", "reason": f"用户指定跳过几何精校正{warning}"}

        if require_spatial_fusion and not metrics["geo_metadata_reliable"]:
            return {
                "stage": "geometry",
                "decision": "execute",
                "reason": "任务需要空间融合，但影像缺少可靠CRS、仿射变换或有效经纬度",
            }
        return {
            "stage": "geometry",
            "decision": "skip",
            "reason": "影像地理参考有效，满足当前空间定位要求",
        }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        req = context.parsed_requirement
        # 优先级：API显式策略 > 自然语言/LLM策略 > XML默认策略。
        policies = dict(req.get("execution_policy") or {})
        policies.update(context.request.execution_policy or {})
        constraints = req.get("constraints") or {}

        preprocess_mode = self._normalize_mode(
            policies.get("preprocess", constraints.get("preprocess_mode", "auto"))
        )
        legacy_need_geo = constraints.get("need_geo_correction")
        default_geo_mode = "force" if legacy_need_geo is True else "skip" if legacy_need_geo is False else "auto"
        geo_mode = self._normalize_mode(
            policies.get("geo_correction", constraints.get("geo_correction_mode", default_geo_mode))
        )
        require_spatial_fusion = bool(
            context.request.output_requirements.get("need_spatial_fusion", True)
        )

        try:
            metrics = self._read_metrics(context.request.tiff_path)
            assessment_error = ""
        except Exception as exc:
            metrics = {
                "bit_depth": 0,
                "contrast_score": 0.0,
                "noise_score": 0.0,
                "speckle_cv": 0.0,
                "geo_metadata_reliable": False,
            }
            assessment_error = str(exc)

        payloads = [str(item).upper() for item in req.get("payload_types", [])]
        preprocess = self._preprocess_decision(payloads, preprocess_mode, metrics)
        geometry = self._geo_decision(geo_mode, metrics, require_spatial_fusion)

        if assessment_error and preprocess_mode == "auto":
            preprocess = {
                "stage": "preprocess",
                "decision": "execute",
                "reason": f"影像质量评估失败，采用保守预处理策略：{assessment_error}",
            }
        if assessment_error and geo_mode == "auto" and require_spatial_fusion:
            geometry = {
                "stage": "geometry",
                "decision": "execute",
                "reason": f"地理信息评估失败且任务需要空间融合：{assessment_error}",
            }

        fusion = {
            "stage": "fusion",
            "decision": "execute" if require_spatial_fusion else "skip",
            "reason": (
                "任务要求执行空间先验/态势融合"
                if require_spatial_fusion
                else "任务仅要求单源目标检测"
            ),
        }
        decisions = {
            "preprocess": preprocess,
            "geometry": geometry,
            "detection": {
                "stage": "detection",
                "decision": "execute",
                "reason": "目标检测是当前任务的核心必选阶段",
            },
            "fusion": fusion,
        }
        req["execution_policy"] = {
            "preprocess": preprocess_mode,
            "geo_correction": geo_mode,
        }
        req["stage_decisions"] = decisions
        context.metadata["image_assessment"] = metrics
        context.metadata["stage_decisions"] = decisions
        context.metadata["assessment_agent"] = "image_assessment_v1"
        return context
