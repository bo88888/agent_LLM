from ultralytics import YOLO
import argparse
import numpy as np
import cv2
import os
from pathlib import Path
import json
from osgeo import gdal, osr
import torch
from PIL import Image

# ===================== 切片 ResNet 分类模型复用 =====================
# 优先使用当前算法服务目录下的 Slice_detection 权重；
# Docker 内一般是 /app/Slice_detection，本地仓库内一般是 ../Slice_detection。
_LOCAL_SLICE_MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Slice_detection"))
if os.path.isdir(_LOCAL_SLICE_MODEL_DIR):
    os.environ.setdefault("SLICE_MODEL_DIR", _LOCAL_SLICE_MODEL_DIR)

try:
    from Slice_detection.resnet_infer import get_slice_model
except Exception:
    try:
        from services.algorithm_service.Slice_detection.resnet_infer import get_slice_model
    except Exception:
        get_slice_model = None


# 计算左上和右下的经纬度
def get_tif_corners_latlon(tif_path):
    ds = gdal.Open(tif_path)
    if ds is None:
        raise ValueError(f"无法打开文件：{tif_path}")
    gt = ds.GetGeoTransform()
    width = ds.RasterXSize
    height = ds.RasterYSize

    # 原始的两个角点坐标
    # 左上
    ulx = gt[0]
    uly = gt[3]
    # 右下
    lrx = gt[0] + width * gt[1] + height * gt[2]
    lry = gt[3] + width * gt[4] + height * gt[5]

    # 如果原始不是WGS84则转为WGS84
    proj = ds.GetProjection()
    if proj:
        src_srs = osr.SpatialReference()
        src_srs.ImportFromWkt(proj)

        # 如果图像已经是地理坐标系（如WGS84），直接返回，避免 GDAL 坐标转换报错
        if src_srs.IsGeographic():
            ul_lon, ul_lat = ulx, uly
            lr_lon, lr_lat = lrx, lry
        else:
            tgt_srs = osr.SpatialReference()
            tgt_srs.ImportFromEPSG(4326)

            # 兼容 GDAL 3.x，防止经纬度反转
            src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            tgt_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

            try:
                transform = osr.CoordinateTransformation(src_srs, tgt_srs)
                ul_lon, ul_lat, _ = transform.TransformPoint(ulx, uly)
                lr_lon, lr_lat, _ = transform.TransformPoint(lrx, lry)
            except Exception as e:
                print(f"[警告] 坐标转换失败，使用原始坐标代替: {e}")
                ul_lon, ul_lat = ulx, uly
                lr_lon, lr_lat = lrx, lry
    else:
        ul_lon, ul_lat = ulx, uly
        lr_lon, lr_lat = lrx, lry

    ds = None
    return [ul_lat, ul_lon, lr_lat, lr_lon]


# --------------------------
# 旋转框（四边形）IOU计算
# --------------------------
def polygon_iou(poly1, poly2):
    """
    计算两个四边形的交并比（IOU）
    poly1, poly2: 形状为(4,2)的numpy数组，代表四边形的四个顶点坐标
    """
    inter_area = cv2.intersectConvexConvex(poly1.astype(np.float32), poly2.astype(np.float32))[0]
    if inter_area <= 0:
        return 0.0

    area1 = cv2.contourArea(poly1)
    area2 = cv2.contourArea(poly2)
    if area1 <= 0 or area2 <= 0:
        return 0.0

    union_area = area1 + area2 - inter_area
    return inter_area / union_area


# --------------------------
# 旋转框NMS
# --------------------------
def rotated_nms(detections, iou_threshold=0.5):
    """
    对旋转框执行非极大值抑制（NMS）
    detections: 检测结果列表，每个元素包含'corners'和'confidence'
    iou_threshold: IOU阈值，超过此值的重叠框会被过滤
    """
    if not detections:
        return []

    sorted_dets = sorted(detections, key=lambda x: x["confidence"], reverse=True)
    keep = []

    for i in range(len(sorted_dets)):
        current = sorted_dets[i]
        current_corners = current["corners"]
        keep_flag = True

        for j in keep:
            compare_corners = sorted_dets[j]["corners"]
            iou = polygon_iou(current_corners, compare_corners)
            if iou > iou_threshold:
                keep_flag = False
                break

        if keep_flag:
            keep.append(i)

    return [sorted_dets[i] for i in keep]


# --------------------------
# 水平框NMS
# --------------------------
def horizontal_nms(detections, iou_threshold=0.5):
    """水平框非极大值抑制"""
    if not detections:
        return []

    sorted_dets = sorted(detections, key=lambda x: x["confidence"], reverse=True)
    keep = []

    for i in range(len(sorted_dets)):
        current = sorted_dets[i]
        x1, y1, x2, y2 = current["xyxy"]
        keep_flag = True

        for j in keep:
            j_x1, j_y1, j_x2, j_y2 = sorted_dets[j]["xyxy"]

            inter_x1 = max(x1, j_x1)
            inter_y1 = max(y1, j_y1)
            inter_x2 = min(x2, j_x2)
            inter_y2 = min(y2, j_y2)

            inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
            area1 = (x2 - x1) * (y2 - y1)
            area2 = (j_x2 - j_x1) * (j_y2 - j_y1)

            iou = inter_area / (area1 + area2 - inter_area + 1e-6)

            if iou > iou_threshold:
                keep_flag = False
                break

        if keep_flag:
            keep.append(i)

    return [sorted_dets[i] for i in keep]


# ===================== 裁剪保存函数：仅保存 YOLO 原始检测裁剪图 =====================
def crop_and_save_targets(img, detections, img_name, save_root):
    """
    根据检测框裁剪目标并保存。
    未启用 ResNet 二次分类时使用。
    """
    if not save_root or not detections:
        return

    os.makedirs(save_root, exist_ok=True)

    for idx, det in enumerate(detections):
        corners = det["corners"]

        x_coords = corners[:, 0]
        y_coords = corners[:, 1]

        x1 = int(np.floor(np.min(x_coords)))
        y1 = int(np.floor(np.min(y_coords)))
        x2 = int(np.ceil(np.max(x_coords)))
        y2 = int(np.ceil(np.max(y_coords)))

        h, w = img.shape[:2]

        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        crop_img = img[y1:y2, x1:x2]

        cls_name = det["class_name"]
        conf = det["confidence"]

        save_name = f"{img_name}_{idx}_{cls_name}_{conf:.4f}.jpg"
        save_path = os.path.join(save_root, save_name)

        cv2.imwrite(save_path, crop_img)

    print(f"已裁剪并保存 {len(detections)} 个目标至: {save_root}")


# ===================== ResNet 二次分类工具函数 =====================
def crop_target_patch(img, det):
    """
    根据检测框裁剪单个目标 patch。
    与 crop_and_save_targets 的裁剪逻辑一致，但这里会返回裁剪图供 ResNet 分类。
    """
    corners = det["corners"]

    x_coords = corners[:, 0]
    y_coords = corners[:, 1]

    x1 = int(np.floor(np.min(x_coords)))
    y1 = int(np.floor(np.min(y_coords)))
    x2 = int(np.ceil(np.max(x_coords)))
    y2 = int(np.ceil(np.max(y_coords)))

    h, w = img.shape[:2]

    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    crop_img = img[y1:y2, x1:x2]

    return crop_img, (x1, y1, x2, y2)


def save_crop_patch(crop_img, img_name, idx, cls_name, conf, save_root):
    """
    保存经过 ResNet 二次分类后的目标裁剪图。
    """
    if not save_root:
        return

    os.makedirs(save_root, exist_ok=True)

    save_name = f"{img_name}_{idx}_{cls_name}_{conf:.4f}.jpg"
    save_path = os.path.join(save_root, save_name)

    cv2.imwrite(save_path, crop_img)


def load_slice_classifier(payload_type, object_type):
    """
    加载 Slice_detection 里的切片分类模型。

    实际会根据 payload_type + object_type 自动选择：
    OPTICAL-ship    -> best_slice_opt_ship.pth
    OPTICAL-plane   -> best_slice_opt_plane.pth
    OPTICAL-vehicle -> best_slice_opt_vehicle.pth
    SAR-ship        -> best_slice_sar_ship.pth
    """
    if get_slice_model is None:
        raise ImportError(
            "无法导入 Slice_detection.resnet_infer.get_slice_model，"
            "请检查 PYTHONPATH 是否包含 /app 或仓库根目录。"
        )

    (
        model,
        transform,
        index_to_class_name,
        ignored_indices,
        normalized_payload_type,
        model_target_class,
    ) = get_slice_model(
        payload_type=payload_type,
        target_class=object_type
    )

    return {
        "model": model,
        "transform": transform,
        "index_to_class_name": index_to_class_name,
        "ignored_indices": ignored_indices,
        "payload_type": normalized_payload_type,
        "model_target_class": model_target_class,
    }


def resnet_infer_patch(crop_bgr_img, slice_classifier):
    """
    对单个 YOLO 检测框裁剪出来的 patch 调用切片 ResNet 模型做细分类。
    """
    model = slice_classifier["model"]
    transform = slice_classifier["transform"]
    index_to_class_name = slice_classifier["index_to_class_name"]
    ignored_indices = slice_classifier["ignored_indices"]
    model_target_class = slice_classifier["model_target_class"]

    rgb_img = cv2.cvtColor(crop_bgr_img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_img)

    device = next(model.parameters()).device
    tensor = transform(pil_img).unsqueeze(0).to(device)

    model.eval()

    with torch.no_grad():
        outputs = model(tensor)

        # 与 Slice_detection/resnet_infer.py 保持一致：
        # 如果权重中还包含 xujing / other 等不输出类别，则推理时屏蔽。
        if ignored_indices:
            outputs = outputs.clone()
            for ignore_idx in ignored_indices:
                outputs[:, ignore_idx] = -1e9

        probs = torch.softmax(outputs, dim=1)
        conf, predicted = torch.max(probs, 1)

    cls_index = predicted.item()
    cls_name = index_to_class_name.get(cls_index, f"{model_target_class}_{cls_index}")
    score = float(conf.item())

    return cls_name, round(score, 6)


def reclassify_detections_by_slice_model(image, detections, img_name, slice_classifier, crop_dir=""):
    """
    将 YOLO 检测结果逐个裁剪，并用切片 ResNet 分类结果覆盖 YOLO 类别。
    检测框位置仍来自 YOLO，targetName / confidence 来自 ResNet。
    """
    if not detections:
        return []

    print(f"YOLO初步检测到 {len(detections)} 个目标，开始切片 ResNet 二次分类...")

    reclassified_dets = []

    for idx, det in enumerate(detections):
        crop_patch, _ = crop_target_patch(image, det)

        if crop_patch is None or crop_patch.size == 0:
            new_det = det.copy()
            reclassified_dets.append(new_det)
            continue

        res_cls, res_conf = resnet_infer_patch(
            crop_bgr_img=crop_patch,
            slice_classifier=slice_classifier
        )

        new_det = det.copy()

        # 关键：用 ResNet 分类结果覆盖 YOLO 原始类别
        new_det["class_name"] = res_cls
        new_det["confidence"] = res_conf

        save_crop_patch(
            crop_img=crop_patch,
            img_name=img_name,
            idx=idx,
            cls_name=res_cls,
            conf=res_conf,
            save_root=crop_dir
        )

        reclassified_dets.append(new_det)

    print(f"切片 ResNet 二次分类完成，最终有效目标 {len(reclassified_dets)} 个")
    return reclassified_dets


# =======================================================

def get_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", type=str, default="runs/1/weights/best.pt", help="模型权重路径")
    parser.add_argument("--source", type=str, default="test_images", help="输入图像/文件夹路径")
    parser.add_argument("--output_root", type=str, default="inference_results", help="推理结果根目录")
    parser.add_argument("--conf", type=float, default=0.2, help="置信度阈值")
    parser.add_argument("--nms_iou", type=float, default=0.3, help="NMS的IOU阈值")
    parser.add_argument("--tile_size", type=int, default=1024, help="切分图像的大小")
    parser.add_argument("--overlap", type=int, default=128, help="图像块之间的重叠像素数")
    parser.add_argument("--large_threshold", type=int, default=4096, help="判定为大图的阈值")
    parser.add_argument("--object_type", type=str, default="ship", help="目标类型：ship/plane/vehicle")
    parser.add_argument("--crop_save_dir", type=str, default="", help="目标裁剪保存目录，留空不执行裁剪")
    parser.add_argument(
        "--disable_slice_classification",
        action="store_true",
        help="关闭切片ResNet二次分类，仅输出YOLO检测结果"
    )

    return parser.parse_args()


def get_unique_dir_name(base_dir, base_name):
    dir_name = base_name
    counter = 1

    while os.path.exists(os.path.join(base_dir, dir_name)):
        dir_name = f"{base_name}_{counter}"
        counter += 1

    return dir_name


def split_image(image, tile_size=1024, overlap=128):
    img_height, img_width = image.shape[:2]
    tiles = []
    positions = []

    step = tile_size - overlap
    rows = (img_height + step - 1) // step
    cols = (img_width + step - 1) // step

    for i in range(rows):
        for j in range(cols):
            y1 = i * step
            x1 = j * step
            y2 = y1 + tile_size
            x2 = x1 + tile_size

            if y2 > img_height:
                y2 = img_height
                y1 = max(0, y2 - tile_size)

            if x2 > img_width:
                x2 = img_width
                x1 = max(0, x2 - tile_size)

            tile = image[y1:y2, x1:x2]
            tiles.append(tile)
            positions.append((x1, y1))

    return tiles, positions


def merge_detections(detections, img_width, img_height, nms_threshold=0.1, is_obb=True):
    if not detections:
        return []

    valid_detections = []

    for det in detections:
        # 过滤无效框
        if is_obb:
            x, y, w, h, angle_deg = det["box"]
            if w < 1 or h < 1:
                continue
        else:
            x1, y1, x2, y2 = det["xyxy"]
            if (x2 - x1) < 1 or (y2 - y1) < 1:
                continue

        valid_detections.append(det)

    if not valid_detections:
        print("未检测到有效目标，跳过NMS")
        return []

    # 根据模型类型选择NMS
    if is_obb:
        return rotated_nms(valid_detections, iou_threshold=nms_threshold)
    else:
        return horizontal_nms(valid_detections, iou_threshold=nms_threshold)


def draw_boxes(image, detections, is_obb=True):
    """统一绘制框：支持旋转框和水平框"""
    img_copy = image.copy()
    color = (0, 255, 0)

    for det in detections:
        corners = det["corners"]
        conf = det["confidence"]
        class_name = det["class_name"]

        # 绘制轮廓
        cv2.drawContours(img_copy, [np.int32(corners)], 0, color, 2)

        # 绘制文本
        text = f"{class_name}: {conf:.2f}"
        text_x, text_y = int(corners[0][0]), int(corners[0][1]) - 10
        text_y = text_y if text_y > 10 else int(corners[0][1]) + 20

        cv2.rectangle(img_copy, (text_x, text_y - 20), (text_x + len(text) * 12, text_y), color, -1)
        cv2.putText(
            img_copy,
            text,
            (text_x, text_y - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            2
        )

    return img_copy


def pixel_to_latlon(x, y, img_width, img_height, lat0, lon0, lat1, lon1):
    lat = lat0 + (lat1 - lat0) * (y / img_height)
    lon = lon0 + (lon1 - lon0) * (x / img_width)
    return round(lat, 6), round(lon, 6)


def pixel_to_percent(x, y, img_width, img_height):
    x_percent = x / img_width
    y_percent = y / img_height
    return round(x_percent, 6), round(y_percent, 6)


def numpy_serializer(obj):
    if isinstance(obj, np.floating):
        return float(obj)

    if isinstance(obj, np.integer):
        return int(obj)

    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def process_image(
    model,
    image_path,
    conf_threshold,
    nms_iou,
    tile_size,
    overlap,
    large_threshold,
    class_names,
    output_root,
    lat0,
    lon0,
    lat1,
    lon1,
    is_obb=True,
    crop_dir="",
    slice_classifier=None
):
    image = cv2.imread(image_path)
    if image is None:
        print(f"无法读取图像: {image_path}")
        return None

    img_height, img_width = image.shape[:2]
    all_detections = []

    img_name = os.path.splitext(os.path.basename(image_path))[0]

    os.makedirs(output_root, exist_ok=True)
    result_dir = os.path.join(output_root, get_unique_dir_name(output_root, img_name))
    os.makedirs(result_dir, exist_ok=True)

    print(f"处理图像: {image_path} (尺寸: {img_width}x{img_height})")
    print(f"模型类型: {'OBB(旋转框)' if is_obb else 'HBB(水平框)'}")
    print(f"结果保存至: {result_dir}")

    if img_width > large_threshold or img_height > large_threshold:
        tiles, positions = split_image(image, tile_size, overlap)
        print(f"切分为 {len(tiles)} 个 {tile_size}x{tile_size} 块")

        for tile, (x_offset, y_offset) in zip(tiles, positions):
            results = model(tile, conf=conf_threshold, verbose=False)

            for result in results:
                if is_obb:
                    # ========== OBB旋转框处理 ==========
                    for obb in result.obb:
                        try:
                            xy_tensor = obb.xyxyxyxy[0].cpu()
                            xy_array = xy_tensor.numpy()
                            xy_list = xy_array.flatten().tolist()

                            if len(xy_list) != 8:
                                continue
                        except Exception:
                            continue

                        corners_tile = [
                            (xy_list[0], xy_list[1]),
                            (xy_list[2], xy_list[3]),
                            (xy_list[4], xy_list[5]),
                            (xy_list[6], xy_list[7])
                        ]

                        # 坐标偏移
                        corners = [(x + x_offset, y + y_offset) for x, y in corners_tile]
                        corners_np = np.array(corners, dtype=np.float32)

                        try:
                            rect = cv2.minAreaRect(corners_np)
                            (cx, cy), (w, h), angle_deg = rect

                            if w < h:
                                angle_deg += 90

                            angle_deg %= 180
                        except Exception:
                            continue

                        conf = float(obb.conf[0].cpu())
                        cls_id = int(obb.cls[0].cpu())

                        if cls_id < 0 or cls_id >= len(class_names):
                            continue

                        all_detections.append({
                            "box": (cx, cy, w, h, round(angle_deg, 4)),
                            "corners": corners_np,
                            "confidence": conf,
                            "class_id": cls_id,
                            "class_name": class_names[cls_id]
                        })

                else:
                    # ========== HBB水平框处理 ==========
                    for box in result.boxes:
                        try:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            conf = float(box.conf[0].cpu())
                            cls_id = int(box.cls[0].cpu())
                        except Exception:
                            continue

                        if cls_id < 0 or cls_id >= len(class_names):
                            continue

                        # 偏移坐标
                        x1 += x_offset
                        y1 += y_offset
                        x2 += x_offset
                        y2 += y_offset

                        corners_np = np.array(
                            [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                            dtype=np.float32
                        )
                        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

                        all_detections.append({
                            "xyxy": (x1, y1, x2, y2),
                            "box": (cx, cy, x2 - x1, y2 - y1, 0.0),
                            "corners": corners_np,
                            "confidence": conf,
                            "class_id": cls_id,
                            "class_name": class_names[cls_id]
                        })

        merged = merge_detections(
            all_detections,
            img_width,
            img_height,
            nms_threshold=nms_iou,
            is_obb=is_obb
        )

    else:
        # 小图直接推理
        results = model(image, conf=conf_threshold, verbose=False)
        merged = []

        if is_obb:
            for result in results:
                for obb in result.obb:
                    try:
                        xy_tensor = obb.xyxyxyxy[0].cpu()
                        xy_list = xy_tensor.numpy().flatten().tolist()

                        if len(xy_list) != 8:
                            continue
                    except Exception:
                        continue

                    corners = [
                        (xy_list[0], xy_list[1]),
                        (xy_list[2], xy_list[3]),
                        (xy_list[4], xy_list[5]),
                        (xy_list[6], xy_list[7])
                    ]
                    corners_np = np.array(corners, dtype=np.float32)

                    try:
                        rect = cv2.minAreaRect(corners_np)
                        (cx, cy), (w, h), angle_deg = rect

                        if w < h:
                            angle_deg += 90

                        angle_deg %= 180
                    except Exception:
                        continue

                    conf = float(obb.conf[0].cpu())
                    cls_id = int(obb.cls[0].cpu())

                    if cls_id < 0 or cls_id >= len(class_names):
                        continue

                    merged.append({
                        "box": (cx, cy, w, h, round(angle_deg, 4)),
                        "corners": corners_np,
                        "confidence": conf,
                        "class_id": cls_id,
                        "class_name": class_names[cls_id]
                    })

        else:
            for result in results:
                for box in result.boxes:
                    try:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        conf = float(box.conf[0].cpu())
                        cls_id = int(box.cls[0].cpu())
                    except Exception:
                        continue

                    if cls_id < 0 or cls_id >= len(class_names):
                        continue

                    corners_np = np.array(
                        [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                        dtype=np.float32
                    )
                    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

                    merged.append({
                        "xyxy": (x1, y1, x2, y2),
                        "box": (cx, cy, x2 - x1, y2 - y1, 0.0),
                        "corners": corners_np,
                        "confidence": conf,
                        "class_id": cls_id,
                        "class_name": class_names[cls_id]
                    })

        merged = merge_detections(
            merged,
            img_width,
            img_height,
            nms_threshold=nms_iou,
            is_obb=is_obb
        )

    if slice_classifier is not None:
        # ========== YOLO检测框 -> 自动裁剪 -> 切片ResNet二次分类 ==========
        merged = reclassify_detections_by_slice_model(
            image=image,
            detections=merged,
            img_name=img_name,
            slice_classifier=slice_classifier,
            crop_dir=crop_dir
        )
    else:
        print(f"最终检测到 {len(merged)} 个有效目标")
        # 未启用二次分类时，只保存 YOLO 裁剪结果
        crop_and_save_targets(image, merged, img_name, crop_dir)

    # 保存结果图
    result_image = draw_boxes(image, merged, is_obb=is_obb)
    result_img_path = os.path.join(result_dir, f"{img_name}_result.jpg")
    cv2.imwrite(result_img_path, result_image)
    print(f"推理图保存: {result_img_path}")

    # 构建输出JSON
    output_data = {"data": []}

    for det in merged:
        corners = det["corners"]

        lt_x, lt_y = corners[0]
        rt_x, rt_y = corners[1]
        rb_x, rb_y = corners[2]
        lb_x, lb_y = corners[3]

        center_x_pix, center_y_pix = det["box"][0], det["box"][1]

        # 百分比坐标
        lt_x_per, lt_y_per = pixel_to_percent(lt_x, lt_y, img_width, img_height)
        lb_x_per, lb_y_per = pixel_to_percent(lb_x, lb_y, img_width, img_height)
        rt_x_per, rt_y_per = pixel_to_percent(rt_x, rt_y, img_width, img_height)
        rb_x_per, rb_y_per = pixel_to_percent(rb_x, rb_y, img_width, img_height)
        center_x_per, center_y_per = pixel_to_percent(center_x_pix, center_y_pix, img_width, img_height)

        # 经纬度
        lt_lat, lt_lon = pixel_to_latlon(lt_x, lt_y, img_width, img_height, lat0, lon0, lat1, lon1)
        lb_lat, lb_lon = pixel_to_latlon(lb_x, lb_y, img_width, img_height, lat0, lon0, lat1, lon1)
        rt_lat, rt_lon = pixel_to_latlon(rt_x, rt_y, img_width, img_height, lat0, lon0, lat1, lon1)
        rb_lat, rb_lon = pixel_to_latlon(rb_x, rb_y, img_width, img_height, lat0, lon0, lat1, lon1)
        center_lat, center_lon = pixel_to_latlon(center_x_pix, center_y_pix, img_width, img_height, lat0, lon0, lat1, lon1)

        angle_deg = det["box"][4]

        target_data = {
            "targetName": det["class_name"],
            "leftTopX": lt_x_per,
            "leftTopY": lt_y_per,
            "leftBotX": lb_x_per,
            "leftBotY": lb_y_per,
            "rightTopX": rt_x_per,
            "rightTopY": rt_y_per,
            "rightBotX": rb_x_per,
            "rightBotY": rb_y_per,
            "center_x": center_x_per,
            "center_y": center_y_per,
            "leftTopLon": lt_lon,
            "leftTopLat": lt_lat,
            "leftBotLon": lb_lon,
            "leftBotLat": lb_lat,
            "rightTopLon": rt_lon,
            "rightTopYLat": rt_lat,
            "rightBotXLon": rb_lon,
            "rightBotYLat": rb_lat,
            "center_Lon": center_lon,
            "center_Lat": center_lat,
            "confidence": round(det["confidence"], 6),
            "angle_deg": angle_deg
        }

        output_data["data"].append(target_data)

    # 保存JSON
    json_path = os.path.join(result_dir, f"{img_name}_detections.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4, default=numpy_serializer)

    print(f"JSON结果保存: {json_path}")
    print("-" * 50)

    return output_data


def main():
    args = get_parse()
    model = YOLO(args.model_path)

    # 自动判断模型类型：OBB/普通HBB
    is_obb = model.task == "obb"
    print(f"自动检测模型类型: {'旋转框OBB' if is_obb else '水平框HBB'}")

    # 类别配置
    if args.object_type == "ship":
        class_names = [
            "aircraft_carrier",
            "destroyer",
            "cruiser",
            "amphibious",
            "depot_ship",
            "HJship",
            "BHship",
            "minchuan",
            "other_junchuan",
            "huweijian"
        ]
    elif args.object_type == "plane":
        class_names = [
            "hongzhaji",
            "yunshuji",
            "Helicopter",
            "UAV",
            "airline",
            "fighter",
            "jiayouji",
            "other",
            "yujingji"
        ]
    elif args.object_type == "vehicle":
        class_names = ["ddfsc", "ldtxc"]
    else:
        raise ValueError(f"错误的目标类型：{args.object_type}")

    # 加载切片 ResNet 分类模型；默认启用二次分类。
    slice_classifier = None
    if not args.disable_slice_classification:
        slice_classifier = load_slice_classifier(
            payload_type="OPTICAL",
            object_type=args.object_type
        )
        print(
            f"✅ 切片ResNet分类模型加载完成: "
            f"{slice_classifier['payload_type']}-{slice_classifier['model_target_class']}"
        )

    # 获取图像路径
    image_paths = []
    if os.path.isdir(args.source):
        for ext in ["jpg", "jpeg", "png", "bmp", "tif", "tiff"]:
            image_paths.extend(Path(args.source).glob(f"*.{ext}"))
            image_paths.extend(Path(args.source).glob(f"*.{ext.upper()}"))
    else:
        image_paths = [args.source]

    total = len(image_paths)
    if total == 0:
        print("未找到图像文件")
        return

    print(f"找到 {total} 个图像文件，开始推理...")
    print("-" * 50)

    all_results = {}

    for i, img_path in enumerate(image_paths, 1):
        print(f"正在处理{img_path} - {i}/{total}:")

        [lat0, lon0, lat1, lon1] = get_tif_corners_latlon(str(img_path))

        img_result = process_image(
            model,
            str(img_path),
            args.conf,
            args.nms_iou,
            args.tile_size,
            args.overlap,
            args.large_threshold,
            class_names,
            args.output_root,
            lat0,
            lon0,
            lat1,
            lon1,
            is_obb=is_obb,
            crop_dir=args.crop_save_dir,
            slice_classifier=slice_classifier
        )

        if img_result:
            all_results[os.path.basename(img_path)] = img_result

    # 汇总保存
    summary_json_path = os.path.join(args.output_root, "all_detections_summary.json")
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4, default=numpy_serializer)

    print(f"所有结果汇总保存: {summary_json_path}")
    print(f"处理完成！结果目录: {args.output_root}")


def run_optical_detection(
    image_path,
    model_path,
    output_root,
    object_type,
    payload_type="optical",
    conf=0.2,
    nms_iou=0.3,
    tile_size=2048,
    overlap=400,
    large_threshold=4096,
    crop_save_dir="",
    use_slice_classification=True
):
    """
    光学大图检测入口函数。

    调度器仍然只需要调用这个函数。
    函数内部自动执行：
    1. 加载 YOLO 大图检测模型；
    2. 根据 payload_type + object_type 加载 Slice_detection 中的 ResNet 分类模型；
    3. YOLO 检测大图目标框；
    4. 自动裁剪每个检测框；
    5. ResNet 对裁剪 patch 二次分类；
    6. 用 ResNet 分类结果覆盖 YOLO 的 class_name / confidence。
    """
    model = YOLO(model_path)

    # 自动判断模型类型：OBB还是HBB
    is_obb = model.task == "obb"
    print(f"[{payload_type}] 检测任务启动，模型类型: {'旋转框OBB' if is_obb else '水平框HBB'}")

    # 获取 YOLO 检测类别
    if object_type == "ship":
        class_names = [
            "aircraft_carrier",
            "destroyer",
            "cruiser",
            "amphibious",
            "depot_ship",
            "HJship",
            "BHship",
            "minchuan",
            "other_junchuan",
            "huweijian"
        ]
    elif object_type == "plane":
        class_names = [
            "hongzhaji",
            "yunshuji",
            "Helicopter",
            "UAV",
            "airline",
            "fighter",
            "jiayouji",
            "other",
            "yujingji"
        ]
    elif object_type == "vehicle":
        class_names = ["ddfsc", "ldtxc"]
    else:
        raise ValueError(f"错误的目标类型：{object_type}")

    # 加载 Slice_detection 中的切片 ResNet 分类模型。
    # 调度器只需要继续调用 run_optical_detection，不需要单独再调切片接口。
    slice_classifier = None
    if use_slice_classification:
        slice_classifier = load_slice_classifier(
            payload_type=payload_type,
            object_type=object_type
        )
        print(
            f"[{payload_type}] 切片ResNet分类模型加载完成: "
            f"{slice_classifier['payload_type']}-{slice_classifier['model_target_class']}"
        )

    # 获取地理坐标
    [lat0, lon0, lat1, lon1] = get_tif_corners_latlon(image_path)

    output_data = process_image(
        model,
        image_path,
        conf,
        nms_iou,
        tile_size,
        overlap,
        large_threshold,
        class_names,
        output_root,
        lat0,
        lon0,
        lat1,
        lon1,
        is_obb=is_obb,
        crop_dir=crop_save_dir,
        slice_classifier=slice_classifier
    )

    return output_data


if __name__ == "__main__":
    main()


# 示例：
# python infer_OPT_SLD.py \
#   --model_path /home/air/Code/SLD_Yolo/Opt/runs/silei_ship_obb/weights/best.pt \
#   --source datasets/test_img/ \
#   --output_root infer_results/predict \
#   --object_type ship \
#   --crop_save_dir infer_results/crop
#
# 如需关闭 ResNet 二次分类：
# python infer_OPT_SLD.py \
#   --model_path /home/air/Code/SLD_Yolo/Opt/runs/silei_ship_obb/weights/best.pt \
#   --source datasets/test_img/ \
#   --output_root infer_results/predict \
#   --object_type ship \
#   --crop_save_dir infer_results/crop \
#   --disable_slice_classification