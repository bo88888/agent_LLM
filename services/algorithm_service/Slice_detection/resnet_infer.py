import os
import traceback
from typing import Dict, Any, Tuple

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image


# ==========================================
# 1. 基础配置
# ==========================================

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[切片算法] 当前使用设备: {DEVICE}")

# 模型目录
SLICE_MODEL_DIR = os.getenv("SLICE_MODEL_DIR", "/app/Slice_detection")


# ==========================================
# 2. 不同目标类别的类别表
# ==========================================
# 注意：
# 这里必须和各自模型训练时的类别顺序完全一致。
# ship 当前使用你已有的舰船类别。
# plane 和 vehicle 需要替换成你训练集真实类别顺序。

TARGET_CLASS_NAMES = {
    "ship": [
        "BHship",
        "HJship",
        "aircraft_carrier",
        "amphibious",
        "cruiser",
        "depot_ship",
        "destroyer",
        "huweijian",
        "minchuan",
        "other_junchuan",
        "xujing"
    ],

    # TODO：这里要换成你的飞机模型训练时的真实类别顺序
    "plane": [
        "plane"
        # 例如：
        # "fighter",
        # "bomber",
        # "transport",
        # "uav",
        # "helicopter"
    ],

    # TODO：这里要换成你的车辆模型训练时的真实类别顺序
    "vehicle": [
        "vehicle"
        # 例如：
        # "car",
        # "truck",
        # "tank",
        # "armored_vehicle",
        # "engineering_vehicle"
    ]
}


# ==========================================
# 3. 六个模型配置
# ==========================================

MODEL_CONFIGS = {
    ("OPTICAL", "plane"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_opt_plane.pth"),
        "class_names": TARGET_CLASS_NAMES["plane"]
    },
    ("OPTICAL", "ship"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_opt_ship.pth"),
        "class_names": TARGET_CLASS_NAMES["ship"]
    },
    ("OPTICAL", "vehicle"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_opt_vehicle.pth"),
        "class_names": TARGET_CLASS_NAMES["vehicle"]
    },

    ("SAR", "plane"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_sar_plane.pth"),
        "class_names": TARGET_CLASS_NAMES["plane"]
    },
    ("SAR", "ship"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_sar_ship.pth"),
        "class_names": TARGET_CLASS_NAMES["ship"]
    },
    ("SAR", "vehicle"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_sar_vehicle.pth"),
        "class_names": TARGET_CLASS_NAMES["vehicle"]
    }
}


# ==========================================
# 4. 全局模型缓存
# ==========================================
# key = ("SAR", "ship") / ("OPTICAL", "plane") 等
_SLICE_MODEL_CACHE = {}
_SLICE_TRANSFORM = None


def normalize_payload_type(payload_type: str) -> str:
    """
    统一载荷类型命名。
    """
    value = str(payload_type).strip().upper()

    if value in ["OPT", "OPTICAL", "VISIBLE", "EO"]:
        return "OPTICAL"

    if value in ["SAR", "RADAR"]:
        return "SAR"

    return value


def normalize_target_class(target_class: str) -> str:
    """
    统一目标类别命名。
    """
    value = str(target_class).strip().lower()

    if value in ["aircraft", "airplane", "plane", "planes"]:
        return "plane"

    if value in ["ship", "ships", "vessel", "boat"]:
        return "ship"

    if value in ["vehicle", "vehicles", "car", "truck"]:
        return "vehicle"

    return value


def get_transform():
    """
    图像预处理管道。
    和训练阶段保持一致。
    """
    global _SLICE_TRANSFORM

    if _SLICE_TRANSFORM is not None:
        return _SLICE_TRANSFORM

    _SLICE_TRANSFORM = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(
            [0.485, 0.456, 0.406],
            [0.229, 0.224, 0.225]
        )
    ])

    return _SLICE_TRANSFORM


def clean_state_dict(state_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    兼容 DataParallel 保存出来的 module.xxx 权重。
    """
    new_state_dict = {}

    for key, value in state_dict.items():
        if key.startswith("module."):
            new_key = key.replace("module.", "", 1)
        else:
            new_key = key

        new_state_dict[new_key] = value

    return new_state_dict


def load_checkpoint(weight_path: str) -> Dict[str, Any]:
    """
    兼容不同训练脚本保存格式。
    """
    checkpoint = torch.load(weight_path, map_location=DEVICE)

    if isinstance(checkpoint, dict):
        if "state_dict" in checkpoint:
            checkpoint = checkpoint["state_dict"]
        elif "model_state_dict" in checkpoint:
            checkpoint = checkpoint["model_state_dict"]

    checkpoint = clean_state_dict(checkpoint)

    return checkpoint


def get_slice_model(payload_type: str, target_class: str):
    """
    根据 payload_type + target_class 动态加载模型。

    例如：
    SAR + ship      -> best_slice_sar_ship.pth
    OPTICAL + plane -> best_slice_opt_plane.pth
    """

    payload_type = normalize_payload_type(payload_type)
    target_class = normalize_target_class(target_class)

    model_key = (payload_type, target_class)

    if model_key not in MODEL_CONFIGS:
        raise ValueError(
            f"不支持的切片模型组合: payloadType={payload_type}, "
            f"targetClass={target_class}, "
            f"当前支持: {list(MODEL_CONFIGS.keys())}"
        )

    # 如果该模型已经加载过，直接复用
    if model_key in _SLICE_MODEL_CACHE:
        model, class_names = _SLICE_MODEL_CACHE[model_key]
        return model, get_transform(), class_names, payload_type, target_class

    config = MODEL_CONFIGS[model_key]
    weight_path = config["weight_path"]
    class_names = config["class_names"]
    num_classes = len(class_names)

    if not os.path.exists(weight_path):
        raise FileNotFoundError(f"未找到切片模型权重文件: {weight_path}")

    print(
        f"[切片算法] ⚡ 首次加载模型: "
        f"payloadType={payload_type}, targetClass={target_class}, path={weight_path}"
    )

    # torchvision 新版本推荐 weights=None
    try:
        model = models.resnet50(weights=None)
    except TypeError:
        model = models.resnet50(pretrained=False)

    model.fc = nn.Linear(2048, num_classes)

    state_dict = load_checkpoint(weight_path)
    model.load_state_dict(state_dict, strict=True)

    model.to(DEVICE)
    model.eval()

    _SLICE_MODEL_CACHE[model_key] = (model, class_names)

    print(
        f"[切片算法] ✅ 模型加载成功: "
        f"{payload_type}-{target_class}, 类别数={num_classes}"
    )

    return model, get_transform(), class_names, payload_type, target_class


# ==========================================
# 5. API 推理函数
# ==========================================

def run_slice_batch_inference(
    slice_paths: list,
    tool_name: str,
    payload_type: str,
    target_class: str
) -> dict:
    """
    根据 payload_type + target_class 选择对应切片模型推理。
    """

    all_detections = []

    try:
        if not slice_paths:
            return {
                "code": 400,
                "msg": "pointPathList 为空，没有可推理的切片图像",
                "data": {}
            }

        model, transform, class_names, payload_type, target_class = get_slice_model(
            payload_type=payload_type,
            target_class=target_class
        )

        for actual_path in slice_paths:
            if not os.path.exists(actual_path):
                print(f"[切片推理] ⚠️ 文件不存在，跳过: {actual_path}")
                continue

            img = Image.open(actual_path).convert("RGB")
            img_tensor = transform(img).unsqueeze(0).to(DEVICE)

            with torch.no_grad():
                outputs = model(img_tensor)
                probs = torch.softmax(outputs, dim=1)
                conf, predicted = torch.max(probs, 1)

            cls_index = predicted.item()
            cls_name = class_names[cls_index]
            score = conf.item()

            print(
                f"[切片推理] {os.path.basename(actual_path):30} "
                f"| 载荷: {payload_type:8} "
                f"| 大类: {target_class:8} "
                f"| 细类: {cls_name:20} "
                f"| 置信度: {score:.4f}"
            )

            all_detections.append({
                "targetName": cls_name,
                "targetClass": target_class,
                "payloadType": payload_type,
                "score": round(score, 4),
                "fusionSource": tool_name,
                "fusionBasis": f"{payload_type}-{target_class} 切片视觉特征识别",
                "fusionInfo": "单源独立检出",
                "auxInterpretationInfo": f"切片专属 ResNet50 模型检出: {payload_type}-{target_class}",
                "slicePath": actual_path
            })

        return {
            "code": 200,
            "msg": f"batch success ({len(all_detections)} images processed)",
            "data": {
                "payloadType": payload_type,
                "targetClass": target_class,
                "detections": all_detections
            }
        }

    except Exception as e:
        error_info = traceback.format_exc()
        print(f"[ERROR] 切片推理底层异常:\n{error_info}")

        return {
            "code": 500,
            "msg": f"Algorithm failed: {str(e)}",
            "data": {}
        }