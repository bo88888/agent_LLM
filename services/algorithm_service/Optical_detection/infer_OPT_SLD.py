from ultralytics import YOLO
import argparse
import numpy as np
import cv2
import os
from pathlib import Path
import json
from osgeo import gdal, osr

# 计算左上和右下的经纬度
def get_tif_corners_latlon(tif_path):
    ds = gdal.Open(tif_path)
    if ds is None:
        raise ValueError(f"无法打开文件：{tif_path}")
    gt = ds.GetGeoTransform()
    width = ds.RasterXSize
    height = ds.RasterYSize

    # 原始的两个角点坐标
    # 坐上
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


# --------------------------
# 新增：旋转框（四边形）IOU计算
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
# 新增：自定义旋转框NMS
# --------------------------
def rotated_nms(detections, iou_threshold=0.5):
    """
    对旋转框执行非极大值抑制（NMS）
    detections: 检测结果列表，每个元素包含'corners'和'confidence'
    iou_threshold: IOU阈值，超过此值的重叠框会被过滤
    """
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

def get_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model_path', type=str, default='runs/1/weights/best.pt', help='模型权重路径')
    parser.add_argument('--source', type=str, default='test_images', help='输入图像/文件夹路径')
    parser.add_argument('--output_root', type=str, default='inference_results', help='推理结果根目录')
    parser.add_argument('--conf', type=float, default=0.2, help='置信度阈值')
    parser.add_argument('--nms_iou', type=float, default=0.3, help='NMS的IOU阈值（旋转框）')
    parser.add_argument('--tile_size', type=int, default=1024, help='切分图像的大小')
    parser.add_argument('--overlap', type=int, default=128, help='图像块之间的重叠像素数')
    parser.add_argument('--large_threshold', type=int, default=4096, help='判定为大图的阈值')
    parser.add_argument('--object_type', type=str, default='ship', help='目标类型：ship/plane/vehicle')
    # parser.add_argument('--lat0', type=float, default=39.9042, help='图像左上角纬度')
    # parser.add_argument('--lon0', type=float, default=116.4074, help='图像左上角经度')
    # parser.add_argument('--lat1', type=float, default=39.9092, help='图像右下角纬度')
    # parser.add_argument('--lon1', type=float, default=116.4124, help='图像右下角经度')
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

def merge_detections(detections, img_width, img_height, nms_threshold=0.1):
    if not detections:
        return []

    valid_detections = []
    for det in detections:
        x, y, w, h, angle_deg = det['box']
        if w < 1 or h < 1:
            continue
        if x < 0 or x > img_width or y < 0 or y > img_height:
            continue
        valid_detections.append(det)

    if not valid_detections:
        print("未检测到有效目标，跳过NMS")
        return []

    return rotated_nms(valid_detections, iou_threshold=nms_threshold)

def draw_rotated_boxes(image, detections, class_names):
    colors = [(np.random.randint(0, 255), np.random.randint(0, 255), np.random.randint(0, 255))
             for _ in range(len(class_names))]
    img_copy = image.copy()

    for det in detections:
        corners = det['corners']
        conf = det['confidence']
        cls_id = det['class_id']
        class_name = det['class_name']
        angle_deg = det['box'][4]

        color = colors[cls_id % len(colors)]
        cv2.drawContours(img_copy, [np.int32(corners)], 0, color, 2)

        text = f"{class_name}: {conf:.2f} angle: {angle_deg:.4f}"
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

def process_image(model, image_path, conf_threshold, nms_iou, tile_size, overlap, large_threshold,
                 class_names, output_root, lat0, lon0, lat1, lon1):
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
    print(f"结果保存至: {result_dir}")

    if img_width > large_threshold or img_height > large_threshold:
        tiles, positions = split_image(image, tile_size, overlap)
        print(f"切分为 {len(tiles)} 个 {tile_size}x{tile_size} 块")

        for tile, (x_offset, y_offset) in zip(tiles, positions):
            results = model(tile, conf=conf_threshold)

            for result in results:
                for obb in result.obb:
                    try:
                        xy_tensor = obb.xyxyxyxy[0].cpu()
                        xy_array = xy_tensor.numpy()
                        xy_list = xy_array.flatten().tolist()

                        if len(xy_list) != 8:
                            print(f"角点数量错误，跳过目标")
                            continue
                    except Exception as e:
                        print(f"提取角点失败: {e}，跳过目标")
                        continue

                    try:
                        corners_tile = [
                            (xy_list[0], xy_list[1]),
                            (xy_list[2], xy_list[3]),
                            (xy_list[4], xy_list[5]),
                            (xy_list[6], xy_list[7])
                        ]
                    except IndexError:
                        print(f"角点解析错误，跳过目标")
                        continue

                    corners = []
                    valid = True
                    for (x, y) in corners_tile:
                        if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
                            valid = False
                            break
                        if np.isnan(x) or np.isinf(x) or np.isnan(y) or np.isinf(y):
                            valid = False
                            break
                        corners.append((x + x_offset, y + y_offset))

                    if not valid:
                        print(f"无效角点坐标，跳过目标")
                        continue

                    corners_np = np.array(corners, dtype=np.float32)
                    if corners_np.shape != (4, 2):
                        print(f"角点形状错误，跳过目标")
                        continue

                    corners_unique = np.unique(corners_np, axis=0)
                    if len(corners_unique) < 2:
                        print(f"有效角点数量不足，跳过目标")
                        continue

                    try:
                        rect = cv2.minAreaRect(corners_unique)
                        (cx, cy), (w, h), angle_deg = rect
                        # 判断长短边
                        if w < h:
                            angle_deg = angle_deg + 90
                        angle_deg = angle_deg % 180

                    except cv2.error as e:
                        print(f"计算最小外接矩形失败：{e}，跳过目标")
                        continue

                    try:
                        conf = float(obb.conf[0].cpu())
                        cls_id = int(obb.cls[0].cpu())
                    except Exception as e:
                        print(f"提取置信度/类别失败: {e}，跳过目标")
                        continue

                    if cls_id < 0 or cls_id >= len(class_names):
                        print(f"跳过未知类别ID: {cls_id}")
                        continue

                    all_detections.append({
                        'box': (cx, cy, w, h, round(angle_deg, 4)),# 现在的angle_deg是长边与水平方向的夹角，范围0-180
                        'corners': corners_np,
                        'confidence': conf,
                        'class_id': cls_id,
                        'class_name': class_names[cls_id]
                    })

        merged = merge_detections(all_detections, img_width, img_height, nms_threshold=nms_iou)
    else:
        results = model(image, conf=conf_threshold)
        merged = []
        for result in results:
            for obb in result.obb:
                try:
                    xy_tensor = obb.xyxyxyxy[0].cpu()
                    xy_array = xy_tensor.numpy()
                    xy_list = xy_array.flatten().tolist()

                    if len(xy_list) != 8:
                        print(f"角点数量错误，跳过目标")
                        continue
                except Exception as e:
                    print(f"提取角点失败: {e}，跳过目标")
                    continue

                try:
                    corners = [
                        (xy_list[0], xy_list[1]),
                        (xy_list[2], xy_list[3]),
                        (xy_list[4], xy_list[5]),
                        (xy_list[6], xy_list[7])
                    ]
                except IndexError:
                    print(f"角点解析错误，跳过目标")
                    continue

                valid = True
                for (x, y) in corners:
                    if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
                        valid = False
                        break
                    if np.isnan(x) or np.isinf(x) or np.isnan(y) or np.isinf(y):
                        valid = False
                        break
                if not valid:
                    print(f"无效角点坐标，跳过目标")
                    continue

                corners_np = np.array(corners, dtype=np.float32)
                if corners_np.shape != (4, 2):
                    print(f"角点形状错误，跳过目标")
                    continue

                corners_unique = np.unique(corners_np, axis=0)
                if len(corners_unique) < 2:
                    print(f"有效角点数量不足，跳过目标")
                    continue

                try:
                    rect = cv2.minAreaRect(corners_unique)
                    (cx, cy), (w, h), angle_deg = rect
                except cv2.error as e:
                    print(f"计算最小外接矩形失败：{e}，跳过目标")
                    continue

                try:
                    conf = float(obb.conf[0].cpu())
                    cls_id = int(obb.cls[0].cpu())
                except Exception as e:
                    print(f"提取置信度/类别失败: {e}，跳过目标")
                    continue

                if cls_id < 0 or cls_id >= len(class_names):
                    print(f"跳过未知类别ID: {cls_id}")
                    continue

                merged.append({
                    'box': (cx, cy, w, h, angle_deg),
                    'corners': corners_np,
                    'confidence': conf,
                    'class_id': cls_id,
                    'class_name': class_names[cls_id]
                })

        merged = merge_detections(merged, img_width, img_height, nms_threshold=nms_iou)

    print(f"最终检测到 {len(merged)} 个有效目标")

    # 保存推理结果图片
    result_image = draw_rotated_boxes(image, merged, class_names)
    result_img_path = os.path.join(result_dir, f"{img_name}_result.jpg")
    cv2.imwrite(result_img_path, result_image)
    print(f"推理图保存: {result_img_path}")

    # 构建指定格式的结果数据
    output_data = {"data": []}
    for det in merged:

        corners = det['corners']
        lt_x, lt_y = corners[0]
        rt_x, rt_y = corners[1]
        rb_x, rb_y = corners[2]
        lb_x, lb_y = corners[3]

        center_x_pix, center_y_pix = det['box'][0], det['box'][1]

        # 百分比坐标
        lt_x_per, lt_y_per = pixel_to_percent(lt_x, lt_y, img_width, img_height)
        lb_x_per, lb_y_per = pixel_to_percent(lb_x, lb_y, img_width, img_height)
        rt_x_per, rt_y_per = pixel_to_percent(rt_x, rt_y, img_width, img_height)
        rb_x_per, rb_y_per = pixel_to_percent(rb_x, rb_y, img_width, img_height)
        center_x_per, center_y_per = pixel_to_percent(center_x_pix, center_y_pix, img_width, img_height)

        # 经纬度坐标
        lt_lat, lt_lon = pixel_to_latlon(lt_x, lt_y, img_width, img_height, lat0, lon0, lat1, lon1)
        lb_lat, lb_lon = pixel_to_latlon(lb_x, lb_y, img_width, img_height, lat0, lon0, lat1, lon1)
        rt_lat, rt_lon = pixel_to_latlon(rt_x, rt_y, img_width, img_height, lat0, lon0, lat1, lon1)
        rb_lat, rb_lon = pixel_to_latlon(rb_x, rb_y, img_width, img_height, lat0, lon0, lat1, lon1)
        center_lat, center_lon = pixel_to_latlon(center_x_pix, center_y_pix, img_width, img_height, lat0, lon0, lat1, lon1)

        # 旋转角度
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

    # 保存JSON结果
    json_path = os.path.join(result_dir, f"{img_name}_detections.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4, default=numpy_serializer)
    print(f"JSON结果保存: {json_path}")
    print("-" * 50)

    return output_data

def main():
    args = get_parse()
    model = YOLO(args.model_path)

    # class_names = [
    #     'b52', 'airliner', 'c130', 'helicopter', 'cv',
    #     'warcraft', 'other_boat', 'small_warcraft', 'submarine', 'cargo',
    #     'small_airliner', 'fighter', 'station', 'oil_tank', 'harbor',
    #     'playground', 'airport', 'bridge', 'ore-oil', 'digger'
    # ]
    if args.object_type == 'ship':
        class_names = [
            'aircraft_carrier', 'destroyer', 'cruiser', 'amphibious', 'depot_ship',
            'HJship', 'BHship', 'minchuan', 'other_junchuan', 'huweijian'
        ]
    elif args.object_type == 'plane':
        class_names = [
            'hongzhaji', 'yunshuji', 'Helicopter', 'UAV', 'airline',
            'fighter', 'jiayouji', 'other', 'yujingji'
        ]
    elif args.object_type == 'vehicle':
        class_names = [
            'ddfsc', 'ldtxc'
        ]
    else:
        raise ValueError(f"错误的目标类型：{args.object_type}")

    image_paths = []
    if os.path.isdir(args.source):
        for ext in ['jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff']:
            image_paths.extend(Path(args.source).glob(f'*.{ext}'))
            image_paths.extend(Path(args.source).glob(f'*.{ext.upper()}'))
    else:
        image_paths = [args.source]

    total = len(image_paths)
    if total == 0:
        print(f"在 {args.source} 未找到任何图像文件")
        return
    print(f"找到 {total} 个图像文件，开始推理...")
    print("-" * 50)

    all_results = {}
    for i, img_path in enumerate(image_paths, 1):
        print(f"正在处理{img_path} - {i}/{total}:")

        [lat0, lon0, lat1, lon1] = get_tif_corners_latlon(str(img_path))

        img_result = process_image(
            model, str(img_path), args.conf, args.nms_iou,
            args.tile_size, args.overlap, args.large_threshold,
            class_names, args.output_root, 
            lat0, lon0, lat1, lon1
        )
        if img_result:
            all_results[os.path.basename(img_path)] = img_result

    # 保存汇总JSON
    summary_json_path = os.path.join(args.output_root, "all_detections_summary.json")
    with open(summary_json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4, default=numpy_serializer)
    print(f"所有结果汇总保存: {summary_json_path}")
    print(f"所有处理完成！结果根目录: {args.output_root}")

    print("\n推理结果汇总:")
    print(json.dumps(all_results, ensure_ascii=False, indent=2, default=numpy_serializer))

# ==========================================
# 新增：提供给 app.py 调用的对外接口
# ==========================================
def run_optical_detection(image_path, model_path, output_root, object_type='ship', conf=0.2):
    # 初始化模型
    model = YOLO(model_path)
    
    # 获取类别
    if object_type == 'ship':
        class_names = [
            'aircraft_carrier', 'destroyer', 'cruiser', 'amphibious', 'depot_ship',
            'HJship', 'BHship', 'minchuan', 'other_junchuan', 'huweijian'
        ]
    elif object_type == 'plane':
        class_names = [
            'hongzhaji', 'yunshuji', 'Helicopter', 'UAV', 'airline',
            'fighter', 'jiayouji', 'other', 'yujingji'
        ]
    elif object_type == 'vehicle':
        class_names = ['ddfsc', 'ldtxc']
    else:
        raise ValueError(f"错误的目标类型：{object_type}")

    # 获取地理坐标
    [lat0, lon0, lat1, lon1] = get_tif_corners_latlon(image_path)
    
    # 调用原有的核心处理函数
    # nms_iou 默认给 0.3，切片大小 1024，重叠 128，大图阈值 4096
    output_data = process_image(
        model, image_path, conf, 0.3, 1024, 128, 4096,
        class_names, output_root, lat0, lon0, lat1, lon1
    )
    
    return output_data



if __name__ == '__main__':
    main()



# python infer_OPT_SLD.py --model_path /home/air/Code/SLD_Yolo/Opt/runs/silei_ship_obb/weights/best.pt --source datasets/test_img/ --output_root infer_results --object_type ship





