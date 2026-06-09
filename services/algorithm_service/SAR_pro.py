import numpy as np
import rasterio
import cv2

def lee_filter(img, kernel_size=3):
    """
    SAR 专用 Lee 滤波 - 去除相干斑噪声（乘性噪声）
    :param img: 输入单波段图像 (float32)
    :param kernel_size: 滤波窗口大小，默认 3x3
    :return: 去噪后图像
    """
    img = img.astype(np.float32)
    # 局部均值
    mean = cv2.blur(img, (kernel_size, kernel_size))
    # 局部方差
    mean_sq = cv2.blur(img ** 2, (kernel_size, kernel_size))
    var = mean_sq - mean ** 2

    # 计算噪声方差（整图全局方差）
    noise_var = np.var(img)

    # Lee 滤波核心公式
    weight = var / (var + noise_var + 1e-8)
    img_denoised = mean + weight * (img - mean)

    # 限制数值范围，防止溢出
    img_denoised = np.clip(img_denoised, 0, 255)
    return img_denoised

def sar_contrast_adjustment(img, n_std=2):
    """
    适配 L2 级 SAR 影像的对比度调整（参考 quantitative_processing.py 均值-标准差拉伸）
    基于均值±n倍标准差裁剪，再线性拉伸至 0-255，更适配 SAR L2 级影像辐射特性
    :param img: 输入单/多波段图像 (uint8/float32)
    :param n_std: 标准差倍数，默认 2（覆盖95%有效信息）
    :return: 对比度调整后图像 (uint8)
    """
    img_out = np.zeros_like(img, dtype=np.uint8)
    h, w, c = img.shape

    for band in range(c):
        I = img[:, :, band].astype(np.float32)
        
        # 计算均值和标准差（核心调整逻辑）
        mean_val = np.mean(I)
        std_val = np.std(I)
        
        # 基于均值±n倍标准差裁剪极值（适配 L2 级 SAR 影像噪声分布）
        low_val = mean_val - n_std * std_val
        high_val = mean_val + n_std * std_val
        
        # 线性拉伸到 0-255
        I_clipped = np.clip(I, low_val, high_val)
        I_stretched = (I_clipped - low_val) / (high_val - low_val + 1e-8) * 255
        img_out[:, :, band] = I_stretched.astype(np.uint8)

    return img_out

def process_sar_image(input_path, output_path, kernel_size=3, clip_quant=2, n_std=2):
    """
    SAR L2 级影像完整预处理流程（适配原始L2 TIFF输入）
    1. 读取影像（保留地理信息）
    2. 自动位深判断 + 16bit→8bit 量化
    3. Lee 滤波去相干斑噪声
    4. 适配 L2 级的对比度调整（均值-标准差拉伸）
    5. 保存带地理信息的 TIFF 输出
    """
    # ========== 1. 读取 L2 级 SAR 影像（保留地理元数据） ==========
    with rasterio.open(input_path) as src:
        img = src.read()  # (波段数, 高, 宽)
        profile = src.profile  # 保留地理信息（投影、仿射变换等）
        dtype = src.dtypes[0]
        print(f"读取 L2 级 SAR 影像：位深={dtype}，波段数={src.count}，尺寸={src.height}x{src.width}")

    # 转格式：(高, 宽, 波段数)
    img = np.transpose(img, (1, 2, 0))
    img_process = img.copy().astype(np.float32)
    h, w, bands = img_process.shape

    # ========== 2. 自动位深判断 + 8bit 量化（适配 L2 级影像动态范围） ==========
    is_8bit = 'uint8' in str(dtype)
    if not is_8bit:
        print(f"检测到 16bit L2 SAR 影像 → 执行 8bit 量化（{clip_quant}% 截断）")
        for b in range(bands):
            I = img_process[:, :, b]
            p_min = np.percentile(I, clip_quant)
            p_max = np.percentile(I, 100 - clip_quant)
            I = np.clip(I, p_min, p_max)
            I = (I - p_min) / (p_max - p_min + 1e-8) * 255
            img_process[:, :, b] = I
        img_process = img_process.astype(np.uint8)
    else:
        print("检测到 8bit L2 影像 → 跳过量化")
        img_process = img_process.astype(np.uint8)

    # ========== 3. Lee 滤波去噪（逐波段处理 SAR 相干斑） ==========
    print(f"执行 Lee 滤波，窗口 {kernel_size}x{kernel_size}")
    img_denoised = np.zeros_like(img_process)
    for b in range(bands):
        img_denoised[:, :, b] = lee_filter(img_process[:, :, b], kernel_size)

    # ========== 4. 对比度调整（适配 L2 级 SAR 影像） ==========
    print(f"执行 L2 级 SAR 对比度调整（均值±{n_std}倍标准差拉伸）")
    img_enhanced = sar_contrast_adjustment(img_denoised, n_std=n_std)

    # ========== 5. 保存预处理结果（保留 L2 影像地理信息） ==========
    img_out = np.transpose(img_enhanced, (2, 0, 1))  # 转回 rasterio 要求的 (波段, 高, 宽)
    # 更新输出配置（保证地理信息不变，仅更新数据类型）
    profile.update(
        dtype=rasterio.uint8,
        count=bands,
        compress='lzw'  
    )

    with rasterio.open(output_path, 'w', **profile) as dst:
        dst.write(img_out)

    print(f"✅ P1 SAR去噪 预处理完成！输出路径：{output_path}")
    return img_enhanced

# ====================== L2 影像调用示例 ======================
if __name__ == '__main__':
    # 替换为你的 L2 级 SAR 输入/输出路径
    INPUT_L2_SAR = "IMAGE_PRSC-S1_SAR_WH0731_06221709102025_001064_S15_I01_GEC_1_HH_clip.tif"
    OUTPUT_PROCESSED = "IMAGE_PRSC-S1_SAR_WH0731_06221709102025_001064_S15_I01_GEC_1_HH_clip_processed.tif"

    # 预处理参数（针对 L2 影像优化）
    process_sar_image(
        input_path=INPUT_L2_SAR,
        output_path=OUTPUT_PROCESSED,
        kernel_size=3,    # Lee 滤波窗口（3x3 适配多数 SAR 分辨率）
        clip_quant=2,     # 16bit→8bit 量化裁剪百分比
        n_std=2           # 对比度调整：均值±2倍标准差（核心参数）
    )
