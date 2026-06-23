from ultralytics import YOLO
import argparse
import numpy as np
import cv2
import os
from pathlib import Path
import json
from osgeo import gdal, osr
import torch
import torchvision
from torchvision import models, transforms
import torch.nn as nn
from PIL import Image

# ===================== 全局ResNet配置（二次分类用） =====================
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
val_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

def build_resnet_model(num_cls):
    model = models.resnet50(pretrained=False)
    model.fc = nn.Linear(2048, num_cls)
    return model

# ===================== ResNet类别【顺序必须和训练集文件夹完全一致】 =====================
def get_resnet_class_by_type(obj_type):
    if obj_type == "ship":
        # 严格对应 data/train/ship 子文件夹排序
        res_cls = [
            'BHship', 'HJship', 'aircraft_carrier', 'amphibious', 'cruiser',
            'depot_ship', 'destroyer', 'huweijian', 'minchuan', 'other_junchuan', 'xujing'
        ]
    elif obj_type == "plane":
        # 严格对应 data/train/plane 子文件夹排序
        res_cls = [
            'B52', 'C130', 'Helicopter', 'UAV', 'airline',
            'fighter', 'jiayouji', 'other', 'xujing', 'yujingji'
        ]
    elif obj_type == "vehicle":
        # 严格对应 data/train/vehicle 子文件夹排序
        res_cls = ['ddfsc', 'ldtxc', 'other', 'xujing']
    else:
        raise ValueError(f"不支持的目标类型：{obj_type}")
    return res_cls

# ===================== 地理坐标工具函数 =====================
def get_tif_corners_latlon(tif_path):
    ds = gdal.Open(tif_path)
    if ds is None:
        raise ValueError(f"无法打开文件：{tif_path}")
    gt = ds.GetGeoTransform()
    width = ds.RasterXSize
    height = ds.RasterYSize

    ulx = gt[0]
    uly = gt[3]
    lrx = gt[0] + width * gt[1] + height * gt[2]
    lry = gt[3] + width * gt[4] + height * gt[5]
    proj = ds.GetProjection()
    if proj:
        src_srs = osr.SpatialReference()
        src_srs.ImportFromWkt(proj)
        tgt_srs = osr.SpatialReference()
        tgt_srs.ImportFromEPSG(4326)
        transfrom = osr.CoordinateTransformation(src_srs, tgt_srs)
        ul_lon, ul_lat, _ = transfrom.TransformPoint(ulx, uly)
        lr_lon, lr_lat, _ = transfrom.TransformPoint(lrx, lry)
    else:
        ul_lon, ul_lat = ulx, uly
        lr_lon, lr_lat = lrx, lry
    ds = None
    return [ul_lat, ul_lon, lr_lat, lr_lon]

# ===================== 旋转框IOU、NMS、水平框NMS =====================
def polygon_iou(poly1, poly2):
    inter_area = cv2.intersectConvexConvex(poly1.astype(np.float32), poly2.astype(np.float32))[0]
    if inter_area <= 0:
        return 0.0
    area1 = cv2.contourArea(poly1)
    area2 = cv2.contourArea(poly2)
    if area1 <= 0 or area2 <= 0:
        return 0.0
    union_area = area1 + area2 - inter_area
    return inter_area / union_area

def rotated_nms(detections, iou_threshold=0.5):
    if not detections:
        return []
    sorted_dets = sorted(detections, key=lambda x: x['confidence'], reverse=True)
    keep = []
    for i in range(len(sorted_dets)):
        current = sorted_dets[i]
        current_corners = current['corners']
        keep_flag = True
        for j in keep:
            compare_corners = sorted_dets[j]['corners']
            iou = polygon_iou(current_corners, compare_corners)
            if iou > iou_threshold:
                keep_flag = False
                break
        if keep_flag:
            keep.append(i)
    return [sorted_dets[i] for i in keep]

def horizontal_nms(detections, iou_threshold=0.5):
    if not detections:
        return []
    sorted_dets = sorted(detections, key=lambda x: x['confidence'], reverse=True)
    keep = []
    for i in range(len(sorted_dets)):
        current = sorted_dets[i]
        x1, y1, x2, y2 = current['xyxy']
        keep_flag = True
        for j in keep:
            j_x1, j_y1, j_x2, j_y2 = sorted_dets[j]['xyxy']
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

# ===================== 目标裁剪 =====================
def crop_target_patch(img, det):
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
    return crop_img, (x1,y1,x2,y2)

def save_crop_patch(crop_img, img_name, idx, cls_name, conf, save_root):
    if not save_root:
        return
    os.makedirs(save_root, exist_ok=True)
    save_name = f"{img_name}_{idx}_{cls_name}_{conf:.4f}.jpg"
    save_path = os.path.join(save_root, save_name)
    cv2.imwrite(save_path, crop_img)

# ===================== ResNet单图推理（按训练顺序映射类别） =====================
def resnet_infer_patch(crop_bgr_img, resnet_model, class_names):
    rgb_img = cv2.cvtColor(crop_bgr_img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_img)
    tensor = val_transform(pil_img).unsqueeze(0).to(device)
    resnet_model.eval()
    with torch.no_grad():
        out = resnet_model(tensor)
        prob, pred_idx = torch.max(torch.softmax(out, dim=1), dim=1)
    cls_name = class_names[pred_idx.item()]
    conf = float(prob.item())
    return cls_name, round(conf, 6)

# ===================== 辅助工具 =====================
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
        if is_obb:
            x, y, w, h, angle_deg = det['box']
            if w < 1 or h < 1:
                continue
        else:
            x1, y1, x2, y2 = det['xyxy']
            if (x2-x1) < 1 or (y2-y1) <1:
                continue
        valid_detections.append(det)
    if not valid_detections:
        print("未检测到有效目标，跳过NMS")
        return []
    if is_obb:
        return rotated_nms(valid_detections, iou_threshold=nms_threshold)
    else:
        return horizontal_nms(valid_detections, iou_threshold=nms_threshold)

def draw_boxes(image, detections, is_obb=True):
    img_copy = image.copy()
    color = (0, 255, 0)
    for det in detections:
        corners = det['corners']
        conf = det['confidence']
        class_name = det['class_name']
        cv2.drawContours(img_copy, [np.int32(corners)], 0, color, 2)
        text = f"{class_name}: {conf:.2f}"
        text_x, text_y = int(corners[0][0]), int(corners[0][1]) - 10
        text_y = text_y if text_y > 10 else int(corners[0][1]) + 20
        cv2.rectangle(img_copy, (text_x, text_y - 20), (text_x + len(text)*12, text_y), color, -1)
        cv2.putText(img_copy, text, (text_x, text_y - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)
    return img_copy

def pixel_to_latlon(x, y, img_width, img_height, lat0, lon0, lat1, lon1):
    lat = lat0 + (lat1 - lat0) * (y / img_height)
    lon = lon0 + (lon1 - lon0) * (x / img_width)
    return round(lat, 6), round(lon, 6)

def pixel_to_percent(x, y, img_width, img_height):
    x_percent = (x / img_width)
    y_percent = (y / img_height)
    return round(x_percent, 6), round(y_percent, 6)

def numpy_serializer(obj):
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

# ===================== 核心推理：YOLO检测 -> 裁剪 -> ResNet重分类覆盖结果 =====================
def process_image(model, resnet_model, resnet_cls, image_path, conf_threshold, nms_iou, tile_size, overlap, large_threshold,
                 yolo_class_names, output_root, lat0, lon0, lat1, lon1, is_obb=True, crop_dir=''):
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
            results = model(tile, conf=conf_threshold)
            for result in results:
                if is_obb:
                    for obb in result.obb:
                        try:
                            xy_tensor = obb.xyxyxyxy[0].cpu()
                            xy_array = xy_tensor.numpy()
                            xy_list = xy_array.flatten().tolist()
                            if len(xy_list) != 8:
                                continue
                        except:
                            continue
                        corners_tile = [(xy_list[0], xy_list[1]), (xy_list[2], xy_list[3]),
                                        (xy_list[4], xy_list[5]), (xy_list[6], xy_list[7])]
                        corners = [(x+x_offset, y+y_offset) for x,y in corners_tile]
                        corners_np = np.array(corners, dtype=np.float32)
                        try:
                            rect = cv2.minAreaRect(corners_np)
                            (cx, cy), (w, h), angle_deg = rect
                            if w < h:
                                angle_deg += 90
                            angle_deg %= 180
                        except:
                            continue
                        conf = float(obb.conf[0].cpu())
                        cls_id = int(obb.cls[0].cpu())
                        if cls_id <0 or cls_id >= len(yolo_class_names):
                            continue
                        all_detections.append({
                            'box': (cx, cy, w, h, round(angle_deg,4)),
                            'corners': corners_np,
                            'confidence': conf,
                            'class_id': cls_id,
                            'class_name': yolo_class_names[cls_id]
                        })
                else:
                    for box in result.boxes:
                        try:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            conf = float(box.conf[0].cpu())
                            cls_id = int(box.cls[0].cpu())
                        except:
                            continue
                        if cls_id <0 or cls_id >= len(yolo_class_names):
                            continue
                        x1 += x_offset
                        y1 += y_offset
                        x2 += x_offset
                        y2 += y_offset
                        corners_np = np.array([[x1,y1], [x2,y1], [x2,y2], [x1,y2]], dtype=np.float32)
                        cx, cy = (x1+x2)/2, (y1+y2)/2
                        all_detections.append({
                            'xyxy': (x1,y1,x2,y2),
                            'box': (cx, cy, x2-x1, y2-y1, 0.0),
                            'corners': corners_np,
                            'confidence': conf,
                            'class_id': cls_id,
                            'class_name': yolo_class_names[cls_id]
                        })
        merged = merge_detections(all_detections, img_width, img_height, nms_threshold=nms_iou, is_obb=is_obb)
    else:
        results = model(image, conf=conf_threshold)
        merged = []
        if is_obb:
            for result in results:
                for obb in result.obb:
                    try:
                        xy_tensor = obb.xyxyxyxy[0].cpu()
                        xy_list = xy_tensor.numpy().flatten().tolist()
                        if len(xy_list)!=8: continue
                    except: continue
                    corners = [(xy_list[0], xy_list[1]), (xy_list[2], xy_list[3]),
                                (xy_list[4], xy_list[5]), (xy_list[6], xy_list[7])]
                    corners_np = np.array(corners, dtype=np.float32)
                    try:
                        rect = cv2.minAreaRect(corners_np)
                        (cx, cy), (w, h), angle_deg = rect
                        if w < h: angle_deg +=90
                        angle_deg %=180
                    except: continue
                    conf = float(obb.conf[0].cpu())
                    cls_id = int(obb.cls[0].cpu())
                    if cls_id <0 or cls_id >= len(yolo_class_names): continue
                    merged.append({
                        'box': (cx, cy, w, h, round(angle_deg,4)),
                        'corners': corners_np,
                        'confidence': conf,
                        'class_id': cls_id,
                        'class_name': yolo_class_names[cls_id]
                    })
        else:
            for result in results:
                for box in result.boxes:
                    try:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        conf = float(box.conf[0].cpu())
                        cls_id = int(box.cls[0].cpu())
                    except: continue
                    if cls_id <0 or cls_id >= len(yolo_class_names): continue
                    corners_np = np.array([[x1,y1], [x2,y1], [x2,y2], [x1,y2]], dtype=np.float32)
                    cx, cy = (x1+x2)/2, (y1+y2)/2
                    merged.append({
                        'xyxy': (x1,y1,x2,y2),
                        'box': (cx, cy, x2-x1, y2-y1, 0.0),
                        'corners': corners_np,
                        'confidence': conf,
                        'class_id': cls_id,
                        'class_name': yolo_class_names[cls_id]
                    })
        merged = merge_detections(merged, img_width, img_height, nms_threshold=nms_iou, is_obb=is_obb)

    print(f"YOLO初步检测到 {len(merged)} 个目标，开始ResNet二次重分类...")
    reclassified_dets = []
    for idx, det in enumerate(merged):
        crop_patch, _ = crop_target_patch(image, det)
        if crop_patch.size == 0:
            new_det = det.copy()
            reclassified_dets.append(new_det)
            continue
        res_cls, res_conf = resnet_infer_patch(crop_patch, resnet_model, resnet_cls)
        new_det = det.copy()
        new_det["class_name"] = res_cls
        new_det["confidence"] = res_conf
        save_crop_patch(crop_patch, img_name, idx, res_cls, res_conf, crop_dir)
        reclassified_dets.append(new_det)
    merged = reclassified_dets
    print(f"ResNet重分类完成，最终有效目标 {len(merged)} 个")

    result_image = draw_boxes(image, merged, is_obb=is_obb)
    result_img_path = os.path.join(result_dir, f"{img_name}_result.jpg")
    cv2.imwrite(result_img_path, result_image)
    print(f"推理图保存: {result_img_path}")

    output_data = {"data": []}
    for det in merged:
        corners = det['corners']
        lt_x, lt_y = corners[0]
        rt_x, rt_y = corners[1]
        rb_x, rb_y = corners[2]
        lb_x, lb_y = corners[3]
        center_x_pix, center_y_pix = det['box'][0], det['box'][1]

        lt_x_per, lt_y_per = pixel_to_percent(lt_x, lt_y, img_width, img_height)
        lb_x_per, lb_y_per = pixel_to_percent(lb_x, lb_y, img_width, img_height)
        rt_x_per, rt_y_per = pixel_to_percent(rt_x, rt_y, img_width, img_height)
        rb_x_per, rb_y_per = pixel_to_percent(rb_x, rb_y, img_width, img_height)
        center_x_per, center_y_per = pixel_to_percent(center_x_pix, center_y_pix, img_width, img_height)

        lt_lat, lt_lon = pixel_to_latlon(lt_x, lt_y, img_width, img_height, lat0, lon0, lat1, lon1)
        lb_lat, lb_lon = pixel_to_latlon(lb_x, lb_y, img_width, img_height, lat0, lon0, lat1, lon1)
        rt_lat, rt_lon = pixel_to_latlon(rt_x, rt_y, img_width, img_height, lat0, lon0, lat1, lon1)
        rb_lat, rb_lon = pixel_to_latlon(rb_x, rb_y, img_width, img_height, lat0, lon0, lat1, lon1)
        center_lat, center_lon = pixel_to_latlon(center_x_pix, center_y_pix, img_width, img_height, lat0, lon0, lat1, lon1)

        angle_deg = det['box'][4]
        target_data = {
            "targetName": det['class_name'],
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
            "confidence": round(det['confidence'], 6),
            "angle_deg": angle_deg
        }
        output_data["data"].append(target_data)

    json_path = os.path.join(result_dir, f"{img_name}_detections.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4, default=numpy_serializer)
    print(f"JSON结果保存: {json_path}")
    print("-" * 50)
    return output_data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model_path', type=str, default='runs/1/weights/best.pt', help='YOLO模型权重路径')
    parser.add_argument('--resnet_weights', type=str, default='pth/tomato/best_model.pth', help='ResNet分类权重路径')
    parser.add_argument('--source', type=str, default='test_images', help='输入图像/文件夹路径')
    parser.add_argument('--output_root', type=str, default='inference_results', help='推理结果根目录')
    parser.add_argument('--conf', type=float, default=0.2, help='YOLO置信度阈值')
    parser.add_argument('--nms_iou', type=float, default=0.3, help='NMS的IOU阈值')
    parser.add_argument('--tile_size', type=int, default=1024, help='切分图像的大小')
    parser.add_argument('--overlap', type=int, default=128, help='图像块之间的重叠像素数')
    parser.add_argument('--large_threshold', type=int, default=4096, help='判定为大图的阈值')
    parser.add_argument('--object_type', type=str, default='ship', choices=["ship","plane","vehicle"], help='目标类型：ship/plane/vehicle')
    parser.add_argument('--crop_save_dir', type=str, default='', help='目标裁剪保存目录，留空不执行裁剪')
    args = parser.parse_args()

    yolo_model = YOLO(args.model_path)
    is_obb = yolo_model.task == "obb"
    print(f"自动检测模型类型: {'旋转框OBB' if is_obb else '水平框HBB'}")

    resnet_class_names = get_resnet_class_by_type(args.object_type)
    resnet_num_classes = len(resnet_class_names)
    resnet_model = build_resnet_model(resnet_num_classes)
    resnet_model.load_state_dict(torch.load(args.resnet_weights, map_location=device))
    resnet_model.to(device)
    resnet_model.eval()
    print(f"✅ ResNet分类权重加载完成: {args.resnet_weights}")
    print(f"✅ ResNet类别列表(匹配训练集顺序): {resnet_class_names}")

    # YOLO内置类别
    if args.object_type == 'ship':
        yolo_class_names = [
            'aircraft_carrier', 'destroyer', 'cruiser', 'amphibious', 'depot_ship',
            'HJship', 'BHship', 'minchuan', 'other_junchuan', 'huweijian'
        ]
    elif args.object_type == 'plane':
        yolo_class_names = [
            'hongzhaji', 'yunshuji', 'Helicopter', 'UAV', 'airline',
            'fighter', 'jiayouji', 'other', 'yujingji'
        ]
    elif args.object_type == 'vehicle':
        yolo_class_names = ['ddfsc', 'ldtxc']
    else:
        raise ValueError(f"错误的目标类型：{args.object_type}")

    image_paths = []
    img_exts = {"jpg", "jpeg", "png", "bmp", "tif", "tiff"}
    if os.path.isdir(args.source):
        for root, _, files in os.walk(args.source):
            for filename in files:
                ext = filename.split(".")[-1].lower()
                if ext in img_exts:
                    img_full_path = Path(root) / filename
                    image_paths.append(img_full_path)
    else:
        image_paths = [args.source]

    total = len(image_paths)
    if total == 0:
        print(f"未找到图像文件")
        return
    image_paths = sorted(image_paths)
    print(f"找到 {total} 个图像文件，开始推理...")
    print("-" * 50)

    all_results = {}
    for i, img_path in enumerate(image_paths, 1):
        print(f"正在处理{img_path} - {i}/{total}:")
        try:
            [lat0, lon0, lat1, lon1] = get_tif_corners_latlon(str(img_path))
        except Exception as e:
            print(f"读取地理信息失败，跳过该图: {e}")
            continue
        img_result = process_image(
            model=yolo_model,
            resnet_model=resnet_model,
            resnet_cls=resnet_class_names,
            image_path=str(img_path),
            conf_threshold=args.conf,
            nms_iou=args.nms_iou,
            tile_size=args.tile_size,
            overlap=args.overlap,
            large_threshold=args.large_threshold,
            yolo_class_names=yolo_class_names,
            output_root=args.output_root,
            lat0=lat0, lon0=lon0, lat1=lat1, lon1=lon1,
            is_obb=is_obb,
            crop_dir=args.crop_save_dir
        )
        if img_result:
            all_results[os.path.basename(img_path)] = img_result

    summary_json_path = os.path.join(args.output_root, "all_detections_summary.json")
    with open(summary_json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4, default=numpy_serializer)
    print(f"所有结果汇总保存: {summary_json_path}")
    print(f"处理完成！结果目录: {args.output_root}")

if __name__ == '__main__':
    main()
# python infer_OPT_SLD_V3_add_classfly.py --model_path /home/air/Code/SLD_Yolo/Opt/runs/silei_plane_0617/weights/best.pt --source /home/air/Python/天基样例/OPT/plane/OPT-zone1.tif --output_root infer_results/pridict_plane --object_type plane --crop_save_dir infer_results/crop_plane --resnet_weights /home/air/Code/SLD_Yolo/resnet-50-master/pth/opt_plane/best_model.pth
