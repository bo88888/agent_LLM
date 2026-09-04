from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class ToolCapability:
    """Describes what a tool can do so agents can compose tasks by capability."""

    tool_name: str
    display_name: str
    stage: str
    modes: List[str]
    output_schema: List[str]
    payload_types: List[str] = field(default_factory=list)
    target_classes: List[str] = field(default_factory=list)
    input_key: str = ""
    requires_geo: bool = False
    optional: bool = False
    fallback_tools: List[str] = field(default_factory=list)
    failure_strategy: str = "fail"

    @property
    def capability_id(self) -> str:
        return self.tool_name


DEFAULT_TOOL_CAPABILITIES: List[ToolCapability] = [
    ToolCapability(
        tool_name="sar_denoise_service",
        display_name="SAR denoise",
        stage="preprocess",
        modes=["base_map"],
        payload_types=["SAR"],
        input_key="SAR",
        output_schema=["sar_denoised_path"],
        optional=True,
        failure_strategy="skip",
    ),
    ToolCapability(
        tool_name="optical_enhance_service",
        display_name="Optical enhancement",
        stage="preprocess",
        modes=["base_map"],
        payload_types=["OPTICAL"],
        input_key="OPTICAL",
        output_schema=["optical_enhanced_path"],
        optional=True,
        failure_strategy="skip",
    ),
    ToolCapability(
        tool_name="geo_correction_service",
        display_name="Geo correction",
        stage="geometry",
        modes=["base_map"],
        payload_types=["SAR", "OPTICAL"],
        output_schema=["geo_corrected_path", "target_resolution"],
        optional=True,
        failure_strategy="skip",
    ),
    ToolCapability(
        tool_name="sar_plane_service",
        display_name="SAR plane detection",
        stage="detect",
        modes=["base_map"],
        payload_types=["SAR"],
        target_classes=["plane"],
        requires_geo=False,
        output_schema=["detections"],
    ),
    ToolCapability(
        tool_name="sar_ship_service",
        display_name="SAR ship detection",
        stage="detect",
        modes=["base_map"],
        payload_types=["SAR"],
        target_classes=["ship"],
        requires_geo=False,
        output_schema=["detections"],
    ),
    ToolCapability(
        tool_name="sar_vehicle_service",
        display_name="SAR vehicle detection",
        stage="detect",
        modes=["base_map"],
        payload_types=["SAR"],
        target_classes=["vehicle"],
        requires_geo=False,
        output_schema=["detections"],
    ),
    ToolCapability(
        tool_name="optical_plane_service",
        display_name="Optical plane detection",
        stage="detect",
        modes=["base_map"],
        payload_types=["OPTICAL"],
        target_classes=["plane"],
        requires_geo=False,
        output_schema=["detections"],
    ),
    ToolCapability(
        tool_name="optical_ship_service",
        display_name="Optical ship detection",
        stage="detect",
        modes=["base_map"],
        payload_types=["OPTICAL"],
        target_classes=["ship"],
        requires_geo=False,
        output_schema=["detections"],
    ),
    ToolCapability(
        tool_name="optical_vehicle_service",
        display_name="Optical vehicle detection",
        stage="detect",
        modes=["base_map"],
        payload_types=["OPTICAL"],
        target_classes=["vehicle"],
        requires_geo=False,
        output_schema=["detections"],
    ),
    ToolCapability(
        tool_name="elint_detection_service",
        display_name="ELINT detection",
        stage="detect",
        modes=["base_map"],
        payload_types=["ELINT"],
        output_schema=["detections"],
        optional=True,
        failure_strategy="skip",
    ),
    ToolCapability(
        tool_name="slice_detection_service",
        display_name="Slice optical detection",
        stage="detect",
        modes=["slice"],
        payload_types=["OPTICAL"],
        output_schema=["detections"],
    ),
]


DEFAULT_TOOL_CAPABILITY_MAP: Dict[str, ToolCapability] = {
    capability.tool_name: capability for capability in DEFAULT_TOOL_CAPABILITIES
}

