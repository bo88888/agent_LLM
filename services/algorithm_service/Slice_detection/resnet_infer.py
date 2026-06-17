import os
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import traceback

# ==========================================
# 1. 基础配置
# ==========================================
# DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# print(f"[切片算法] 当前使用的设备: {DEVICE}")

# 必须和训练集类别顺序保持完全一致！
CLASS_NAMES = ['BHship', 'HJship', 'aircraft_carrier', 'amphibious', 'cruiser', 'depot_ship', 'destroyer', 'huweijian', 'minchuan', 'other_junchuan', 'xujing']
NUM_CLASSES = len(CLASS_NAMES)

# ==========================================
# 2. 全局单例缓存（核心：只加载一次模型）
# ==========================================
_SLICE_MODEL = None
_SLICE_TRANSFORM = None

def get_slice_model():
    """模型懒加载，供内部推理函数调用"""
    global _SLICE_MODEL, _SLICE_TRANSFORM
    
    # 如果模型已经加载过，直接返回，不再重复读硬盘
    if _SLICE_MODEL is not None:
        return _SLICE_MODEL, _SLICE_TRANSFORM
        
    print(f"[切片算法] ⚡ 首次请求，正在初始化 ResNet50 模型...")
    
    # 搭建模型结构 (不加载官方预训练权重)
    model = models.resnet50(pretrained=False)
    model.fc = nn.Linear(2048, NUM_CLASSES)
    
    # 容器内的权重绝对路径（请确保你映射的目录里有这个文件）
    weight_path = "/app/Slice_detection/best_slice.pth"
    
    if os.path.exists(weight_path):
        model.load_state_dict(torch.load(weight_path, map_location=DEVICE))
        model.to(DEVICE)
        model.eval()
        print(f"[切片算法] ✅ 成功加载权重: {weight_path}")
    else:
        print(f"[切片算法] ❌ 致命错误: 未找到权重文件 {weight_path}")
        
    # 图像预处理管道 (和训练时保持一致)
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    _SLICE_MODEL = model
    _SLICE_TRANSFORM = transform
    return _SLICE_MODEL, _SLICE_TRANSFORM


# ==========================================
# 3. 专为 API 提供的主力干活函数
# ==========================================
def run_slice_batch_inference(slice_paths: list, tool_name: str) -> dict:
    """
    接收前端传来的路径列表，执行推理，直接返回字典格式的检测结果
    """
    all_detections = []
    
    try:
        # 获取单例模型
        model, transform = get_slice_model()
        
        # 遍历前端传来的所有切片路径
        for actual_path in slice_paths:
            if not os.path.exists(actual_path):
                print(f"[切片推理] ⚠️ 文件不存在，跳过: {actual_path}")
                continue
                
            # 1. 读取并预处理
            img = Image.open(actual_path).convert("RGB")
            img_tensor = transform(img).unsqueeze(0).to(DEVICE)
            
            # 2. 前向推理
            with torch.no_grad():
                outputs = model(img_tensor)
                probs = torch.softmax(outputs, dim=1)
                conf, predicted = torch.max(probs, 1)
                
            # 3. 解析结果
            cls_name = CLASS_NAMES[predicted.item()]
            score = conf.item()

            print(f"[切片推理] {os.path.basename(actual_path):30} | 类别: {cls_name:15} | 置信度: {score:.4f}")

            # 4. 组装调度器需要的标准业务字段
            all_detections.append({
                "targetName": cls_name,
                "score": round(score, 4),
                "fusionSource": tool_name,
                "fusionBasis": "切片视觉特征识别",
                "fusionInfo": "单源独立检出",
                "auxInterpretationInfo": "切片专属 ResNet50 算法检出"
            })
            
        # 批量处理完毕，返回最终格式
        return {
            "code": 200,
            "msg": f"batch success ({len(all_detections)} images processed)",
            "data": {"detections": all_detections}
        }
        
    except Exception as e:
        error_info = traceback.format_exc()
        print(f"[ERROR] 切片推理底层异常:\n{error_info}")
        return {"code": 500, "msg": f"Algorithm failed: {str(e)}", "data": {}}