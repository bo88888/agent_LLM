import os
import traceback
from typing import Dict, Any, List

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
# 这里必须和各自模型训练时的有效类别顺序完全一致。
# 前端传入的 targetClass 可以是大类，也可以是细分类。
# 若传入细分类，例如 destroyer / B52 / ddfsc，后端会先反推出大类模型，再用模型分类确认。


def get_resnet_class_by_type(obj_type: str) -> List[str]:
    """
    根据目标大类返回 ResNet 有效细分类别表。
    这里不包含前端不会传入的 xujing、other。
    """
    obj_type = str(obj_type).strip().lower()

    if obj_type == "ship":
        return [
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
        ]

    if obj_type == "plane":
        return [
            "B52",
            "C130",
            "Helicopter",
            "UAV",
            "airline",
            "fighter",
            "jiayouji",
            "yujingji",
        ]

    if obj_type == "vehicle":
        return [
            "ddfsc",
            "ldtxc",
        ]

    raise ValueError(f"不支持的 ResNet 切片目标大类: {obj_type}")


TARGET_CLASS_NAMES = {
    "ship": get_resnet_class_by_type("ship"),
    "plane": get_resnet_class_by_type("plane"),
    "vehicle": get_resnet_class_by_type("vehicle"),
}

FULL_CLASS_COUNT_BY_TARGET = {
    "ship": 11,
    "plane": 10,
    "vehicle": 4,
}

IGNORED_CLASS_INDEX_BY_TARGET = {
    "ship": [10],
    "plane": [7, 8],
    "vehicle": [2, 3],
}

TARGET_ALIASES = {
    "ship": ["ship", "ships", "vessel", "vessels", "boat", "boats"],
    "plane": ["plane", "planes", "aircraft", "airplane", "airplanes", "flight"],
    "vehicle": ["vehicle", "vehicles", "car", "cars", "truck", "trucks"],
}


# ==========================================
# 3. 六个模型配置
# ==========================================

MODEL_CONFIGS = {
    ("OPTICAL", "plane"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_opt_plane.pth"),
        "class_names": TARGET_CLASS_NAMES["plane"],
    },
    ("OPTICAL", "ship"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_opt_ship.pth"),
        "class_names": TARGET_CLASS_NAMES["ship"],
    },
    ("OPTICAL", "vehicle"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_opt_vehicle.pth"),
        "class_names": TARGET_CLASS_NAMES["vehicle"],
    },
    ("SAR", "plane"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_sar_plane.pth"),
        "class_names": TARGET_CLASS_NAMES["plane"],
    },
    ("SAR", "ship"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_sar_ship.pth"),
        "class_names": TARGET_CLASS_NAMES["ship"],
    },
    ("SAR", "vehicle"): {
        "weight_path": os.path.join(SLICE_MODEL_DIR, "best_slice_sar_vehicle.pth"),
        "class_names": TARGET_CLASS_NAMES["vehicle"],
    },
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


def normalize_label(value: str) -> str:
    """
    统一细分类别命名，便于大小写、空格、横线兼容。
    """
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def resolve_existing_slice_path(input_path: str) -> str:
    """
    解析切片图片在容器内的真实路径。

    兼容两类前端传参：
    1. 直接传容器内路径：/app/data/xxx.png；
    2. 传宿主机绝对路径：/home/air/codeV1/agent_code/data/xxx.png。

    如果宿主机路径在容器内不可见，会自动尝试映射为 /app/data/xxx.png 或 /workspace/data/xxx.png。
    """
    raw_path = str(input_path).strip()
    if not raw_path:
        return ""

    normalized_path = raw_path.replace("\\", "/")
    candidates = [raw_path]

    data_marker = "/data/"
    if data_marker in normalized_path:
        data_suffix = normalized_path.split(data_marker, 1)[1]
        candidates.extend([
            os.path.join("/app/data", data_suffix),
            os.path.join("/workspace/data", data_suffix),
        ])

    unique_candidates = []
    for candidate in candidates:
        if candidate and candidate not in unique_candidates:
            unique_candidates.append(candidate)

    for candidate in unique_candidates:
        if os.path.exists(candidate):
            if candidate != raw_path:
                print(f"[切片推理] 🔁 路径自动映射: {raw_path} -> {candidate}")
            return candidate

    print(
        f"[切片推理] ⚠️ 文件不存在，已尝试路径: "
        f"{unique_candidates}"
    )
    return ""


def resolve_model_target_class(target_class: str) -> str:
    """
    根据前端传入的类别反推出应该使用的模型大类。

    例如：
    destroyer -> ship
    B52       -> plane
    ddfsc     -> vehicle
    plane     -> plane
    """
    target_norm = normalize_label(target_class)

    if not target_norm:
        raise ValueError("targetClass 为空，无法选择切片分类模型")

    # 1. 当前端直接传入大类时，直接返回大类。
    for major_class, aliases in TARGET_ALIASES.items():
        if target_norm in {normalize_label(alias) for alias in aliases}:
            return major_class

    # 2. 当前端传入细类时，根据类别表反推大类。
    matched_major_classes = []
    for major_class, class_names in TARGET_CLASS_NAMES.items():
        if target_norm in {normalize_label(name) for name in class_names}:
            matched_major_classes.append(major_class)

    if len(matched_major_classes) == 1:
        return matched_major_classes[0]

    if len(matched_major_classes) > 1:
        raise ValueError(
            f"targetClass={target_class} 同时匹配多个大类: {matched_major_classes}，"
            f"请前端额外传入明确大类，或保证细分类名称全局唯一。"
        )

    raise ValueError(
        f"无法根据前端传入类别选择切片模型: targetClass={target_class}，"
        f"请检查 get_resnet_class_by_type 中是否配置了该类别。"
    )


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
    elif hasattr(checkpoint, "state_dict"):
        checkpoint = checkpoint.state_dict()
    else:
        raise TypeError(f"不支持的模型权重格式: {type(checkpoint)}")

    checkpoint = clean_state_dict(checkpoint)

    return checkpoint


def infer_num_classes_from_state_dict(state_dict: Dict[str, Any]) -> int:
    """
    从权重文件中的分类头自动推断输出类别数。
    ResNet50 常见分类头为 fc.weight / fc.bias。
    """
    fc_weight = state_dict.get("fc.weight")
    if fc_weight is not None and hasattr(fc_weight, "shape") and len(fc_weight.shape) == 2:
        return int(fc_weight.shape[0])

    fc_bias = state_dict.get("fc.bias")
    if fc_bias is not None and hasattr(fc_bias, "shape") and len(fc_bias.shape) == 1:
        return int(fc_bias.shape[0])

    return 0


def build_model(num_classes: int):
    """
    搭建和训练时一致的 ResNet50 结构。
    不加载官方预训练权重，只替换最后一层全连接层。
    """
    try:
        model = models.resnet50(weights=None)
    except TypeError:
        model = models.resnet50(pretrained=False)

    model.fc = nn.Linear(2048, num_classes)
    return model


def get_ignored_indices(model_target_class: str, num_classes: int) -> List[int]:
    """
    仅当权重输出类别数仍为原始完整类别数时，屏蔽前端不会传入的类别索引。
    如果模型已经重新训练为有效类别数，则不屏蔽。
    """
    full_count = FULL_CLASS_COUNT_BY_TARGET.get(model_target_class)
    if full_count != num_classes:
        return []

    return [
        idx for idx in IGNORED_CLASS_INDEX_BY_TARGET.get(model_target_class, [])
        if 0 <= idx < num_classes
    ]


def build_index_to_class_name(
    model_target_class: str,
    num_classes: int,
    ignored_indices: List[int]
) -> Dict[int, str]:
    """
    构建模型输出索引到有效细分类别名的映射。
    当权重中存在被屏蔽索引时，会跳过这些索引，保证最终不输出无效类别。
    """
    class_names = get_resnet_class_by_type(model_target_class)
    ignored_set = set(ignored_indices)

    # 模型已按有效类别重新训练时，类别数应与有效类别表一致。
    if not ignored_set and num_classes == len(class_names):
        return {idx: name for idx, name in enumerate(class_names)}

    index_to_name = {}
    class_iter = iter(class_names)

    for idx in range(num_classes):
        if idx in ignored_set:
            continue

        try:
            index_to_name[idx] = next(class_iter)
        except StopIteration:
            index_to_name[idx] = f"{model_target_class}_{idx}"

    return index_to_name


def get_slice_model(payload_type: str, target_class: str):
    """
    根据 payload_type + 前端传入类别动态加载模型。

    例如：
    targetClass=destroyer -> modelTargetClass=ship -> best_slice_xxx_ship.pth
    targetClass=B52       -> modelTargetClass=plane -> best_slice_xxx_plane.pth
    targetClass=ddfsc     -> modelTargetClass=vehicle -> best_slice_xxx_vehicle.pth
    targetClass=ship      -> modelTargetClass=ship -> best_slice_xxx_ship.pth
    """
    payload_type = normalize_payload_type(payload_type)
    model_target_class = resolve_model_target_class(str(target_class).strip())

    model_key = (payload_type, model_target_class)

    if model_key not in MODEL_CONFIGS:
        raise ValueError(
            f"不支持的切片模型组合: payloadType={payload_type}, "
            f"modelTargetClass={model_target_class}, "
            f"当前支持: {list(MODEL_CONFIGS.keys())}"
        )

    # 如果该模型已经加载过，直接复用
    if model_key in _SLICE_MODEL_CACHE:
        model, index_to_class_name, ignored_indices = _SLICE_MODEL_CACHE[model_key]
        return (
            model,
            get_transform(),
            index_to_class_name,
            ignored_indices,
            payload_type,
            model_target_class,
        )

    config = MODEL_CONFIGS[model_key]
    weight_path = config["weight_path"]

    if not os.path.exists(weight_path):
        raise FileNotFoundError(f"未找到切片模型权重文件: {weight_path}")

    print(
        f"[切片算法] ⚡ 首次加载模型: "
        f"payloadType={payload_type}, targetClass={target_class}, "
        f"modelTargetClass={model_target_class}, path={weight_path}"
    )

    state_dict = load_checkpoint(weight_path)
    num_classes = infer_num_classes_from_state_dict(state_dict)

    if num_classes <= 0:
        num_classes = len(config["class_names"])

    if num_classes <= 0:
        raise ValueError(f"无法确定模型类别数，请检查模型权重和类别表: {weight_path}")

    ignored_indices = get_ignored_indices(model_target_class, num_classes)
    index_to_class_name = build_index_to_class_name(
        model_target_class=model_target_class,
        num_classes=num_classes,
        ignored_indices=ignored_indices,
    )

    model = build_model(num_classes)
    model.load_state_dict(state_dict, strict=True)

    model.to(DEVICE)
    model.eval()

    _SLICE_MODEL_CACHE[model_key] = (model, index_to_class_name, ignored_indices)

    print(
        f"[切片算法] ✅ 模型加载成功: "
        f"{payload_type}-{model_target_class}, 类别数={num_classes}, "
        f"有效类别={list(index_to_class_name.values())}, 屏蔽索引={ignored_indices}"
    )

    return (
        model,
        get_transform(),
        index_to_class_name,
        ignored_indices,
        payload_type,
        model_target_class,
    )


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
    最终只返回前端需要展示的类别识别字段。
    """

    all_detections = []

    try:
        if not slice_paths:
            return {
                "code": 400,
                "msg": "pointPath 为空，没有可推理的切片图像",
                "data": {}
            }

        (
            model,
            transform,
            index_to_class_name,
            ignored_indices,
            payload_type,
            model_target_class,
        ) = get_slice_model(
            payload_type=payload_type,
            target_class=target_class
        )

        for item in slice_paths:
            # 兼容两种输入：
            # 1. ["/path/1.png", "/path/2.png"]
            # 2. [{"id": "1", "path": "/path/1.png"}]
            if isinstance(item, dict):
                raw_path = item.get("path", "")
                slice_id = item.get("id", "")
            else:
                raw_path = item
                slice_id = ""

            raw_path = str(raw_path).strip()

            if not raw_path:
                print(f"[切片推理] ⚠️ 空路径，跳过: {item}")
                continue

            actual_path = resolve_existing_slice_path(raw_path)
            if not actual_path:
                continue

            img = Image.open(actual_path).convert("RGB")
            img_tensor = transform(img).unsqueeze(0).to(DEVICE)

            with torch.no_grad():
                outputs = model(img_tensor)

                # 若权重仍包含前端不会传入的类别索引，则屏蔽这些索引。
                if ignored_indices:
                    outputs = outputs.clone()
                    for ignore_idx in ignored_indices:
                        outputs[:, ignore_idx] = -1e9

                probs = torch.softmax(outputs, dim=1)
                conf, predicted = torch.max(probs, 1)

            cls_index = predicted.item()
            cls_name = index_to_class_name.get(cls_index, f"{model_target_class}_{cls_index}")
            score = conf.item()

            print(
                f"[切片推理] {os.path.basename(actual_path):30} "
                f"| 载荷: {payload_type:8} "
                f"| 大类: {model_target_class:8} "
                f"| 细类: {cls_name:20} "
                f"| 置信度: {score:.4f}"
            )

            detection = {
                "targetName": cls_name,
                "targetClass": model_target_class,
                "payloadType": payload_type,
                "score": round(score, 4),
                "fusionSource": tool_name,
                "fusionBasis": f"{payload_type}-{model_target_class} 切片视觉特征识别",
                "fusionInfo": "单源独立检出",
                "auxInterpretationInfo": f"切片专属 ResNet50 模型检出: {payload_type}-{model_target_class}",
            }

            if slice_id:
                detection["id"] = slice_id

            all_detections.append(detection)

        return {
            "code": 200,
            "msg": f"batch success ({len(all_detections)} images processed)",
            "data": {
                "payloadType": payload_type,
                "targetClass": model_target_class,
                "detections": all_detections,
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