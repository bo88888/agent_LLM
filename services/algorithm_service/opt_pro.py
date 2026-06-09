import cv2
import numpy as np
import rasterio

def percentile_contrast_stretch(band_data, clip_percent=2):
    """
    独立的百分比截断对比度拉伸函数（通用型）
    :param band_data: 单波段影像数据（2D数组）
    :param clip_percent: 截断百分比（0-10）
    :return: 拉伸后的单波段数据（CV_8U）
    """
    # 空值/极值防护：避免全0/全NaN/极值异常导致计算失败
    if np.all(band_data == band_data.flat[0]) or np.isnan(band_data).any():
        return band_data.astype(np.uint8)
    
    # 计算截断百分位（增加边界检查，避免percentile计算越界）
    clip_percent = np.clip(clip_percent, 0.1, 10.0)  # 限制截断范围0.1%-10%
    p_min = np.percentile(band_data[band_data > 0], clip_percent)  # 排除0值（黑边）
    p_max = np.percentile(band_data[band_data > 0], 100 - clip_percent)
    
    # 处理极值相等的情况（避免除以0）
    if p_min == p_max:
        return np.zeros_like(band_data, dtype=np.uint8)
    
    # 截断 + 线性拉伸到0-255
    band_stretched = np.clip(band_data, p_min, p_max)
    band_stretched = (band_stretched - p_min) / (p_max - p_min) * 255
    return band_stretched.astype(np.uint8)

def process_optical_rs_image(input_path, output_path, median_ksize=3, clip_percent=2):
    """
    光学遥感影像标准化处理流程（优化版）：
    1. 自动判断位深：8bit则跳过量化，16bit自动转8bit
    2. 中值滤波去噪（去除椒盐/脉冲噪声）
    3. 鲁棒性百分比截断对比度拉伸（兼容异常值/全0/NaN）
    :param input_path: 输入遥感影像路径（.tif等）
    :param output_path: 输出处理后影像路径
    :param median_ksize: 中值滤波核大小（奇数，3/5/7）
    :param clip_percent: 对比度拉伸截断百分比（默认2%，最常用）
    """
    # ========== 1. 读取遥感影像（增加异常捕获） ==========
    try:
        with rasterio.open(input_path) as src:
            img = src.read()  # 格式：(波段数, 高, 宽)
            profile = src.profile  # 保留地理信息
            bit_depth = src.dtypes[0]  # 获取数据类型/位深
            if img.size == 0:
                raise ValueError("输入影像为空，请检查文件路径或影像完整性！")
    except Exception as e:
        raise RuntimeError(f"读取影像失败：{str(e)}")
    
    # 调整维度为OpenCV格式：(高, 宽, 波段数)
    img = np.transpose(img, (1, 2, 0))
    # 复制原始图像，避免修改原数据
    img_process = img.copy().astype(np.float32)

    # ========== 2. 自动位深判断 + 16bit → 8bit 灰度量化 ==========
    # 判断是否已经是8bit图像
    is_8bit = 'uint8' in str(bit_depth)
    if not is_8bit:
        print(f"检测到输入为{bit_depth}图像，执行16bit → 8bit量化...")
        # 逐波段进行 2% 截断线性量化
        for band in range(img_process.shape[2]):
            band_data = img_process[:, :, band]
            # 调用独立的拉伸函数完成量化
            img_process[:, :, band] = percentile_contrast_stretch(band_data, clip_percent)
        # 转为8位无符号整型
        img_process = img_process.astype(np.uint8)
    else:
        print("检测到输入为8bit图像，跳过量化步骤~")
        img_process = img_process.astype(np.uint8)

    # ========== 3. 中值滤波去噪（光学专用） ==========
    print(f"执行中值滤波去噪，核大小：{median_ksize}")
    # 校验滤波核大小（必须为奇数）
    if median_ksize % 2 == 0:
        median_ksize = median_ksize + 1
        print(f"⚠️ 滤波核大小需为奇数，自动修正为：{median_ksize}")
    
    # 单波段/多波段通用中值滤波
    img_denoised = np.zeros_like(img_process)
    if len(img_process.shape) == 3:
        # 多波段：逐波段滤波
        for band in range(img_process.shape[2]):
            img_denoised[:, :, band] = cv2.medianBlur(img_process[:, :, band], median_ksize)
    else:
        # 单波段
        img_denoised = cv2.medianBlur(img_process, median_ksize)

    # ========== 4. 百分比截断对比度拉伸（调用优化后的函数） ==========
    print(f"执行{clip_percent}%截断对比度拉伸...")
    img_enhanced = np.zeros_like(img_denoised)
    for band in range(img_denoised.shape[2]):
        img_enhanced[:, :, band] = percentile_contrast_stretch(
            img_denoised[:, :, band], 
            clip_percent=clip_percent
        )

    # ========== 5. 保存结果（保留地理坐标信息） ==========
    # 维度转回 rasterio 格式：(波段数, 高, 宽)
    img_output = np.transpose(img_enhanced, (2, 0, 1))
    profile.update(
        dtype=rasterio.uint8, 
        count=img_output.shape[0],
        compress='lzw'  # 增加压缩，减小输出文件体积
    )

    try:
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(img_output)
    except Exception as e:
        raise RuntimeError(f"保存影像失败：{str(e)}")

    print(f"✅ P2 光学增强预处理完成！结果已保存至：{output_path}")
    return img_enhanced

# ====================== 调用示例 ======================
if __name__ == '__main__':
    # 输入你的16bit/8bit光学遥感影像路径
    INPUT_IMG = "Suaogang.tif"
    # 输出结果路径
    OUTPUT_IMG = "Suaogang_processed.tif"

    # 执行处理
    try:
        process_optical_rs_image(
            input_path=INPUT_IMG,
            output_path=OUTPUT_IMG,
            median_ksize=3,    # 中值滤波核（3/5/7）
            clip_percent=2     # 2%截断（遥感标准参数）
        )
    except Exception as e:
        print(f"❌ 处理失败：{str(e)}")
