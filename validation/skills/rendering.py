import os
from PIL import Image


def render_all_views(render_dir: str, cad) -> list:
    """
    使用 MCP Bridge 渲染 TOP、FRONT、RIGHT、ISO 四个视图并拼接成一张图。

    拼接布局（2x2）：
    ┌─────────┬─────────┐
    │   TOP   │  FRONT  │
    ├─────────┼─────────┤
    │  RIGHT  │   ISO   │
    └─────────┴─────────┘

    每个子图尺寸 1024x1024，拼接后总尺寸 2048x2048。
    背景统一为白色（处理透明通道）。

    参数：
        render_dir: 渲染输出目录
        cad: CAD_MCP 实例

    返回：
        图像内容列表（单张拼接图），格式为 OpenAI image_url 格式
    """
    views = ["top", "front", "right", "iso"]
    view_images = []
    single_size = 1024  # 单张图片尺寸

    # 1. 渲染四个视图
    for view_name in views:
        screenshot_path = os.path.join(render_dir, f"{view_name.upper()}.png")

        # 调用 MCP Bridge 导出视图
        response = cad.export_view(
            filepath=screenshot_path,
            width=single_size,
            height=single_size,
            orientation=view_name,
        )

        # 检查响应
        if not isinstance(response, dict) or response.get("success") is not True:
            raise RuntimeError(f"export_view failed for {view_name}: {response}")

        # 读取图像并确保白色背景
        img = Image.open(screenshot_path)

        # 如果有透明通道，将透明部分替换为白色
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            # 创建白色背景
            white_bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            # 将图像粘贴到白色背景上（透明部分变白）
            white_bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = white_bg
        else:
            img = img.convert("RGB")

        view_images.append(img)

    # 2. 拼接四张图片为 2x2 网格
    grid_size = 2
    combined_width = single_size * grid_size
    combined_height = single_size * grid_size
    combined_img = Image.new("RGB", (combined_width, combined_height), (255, 255, 255))

    # 布局：TOP, FRONT, RIGHT, ISO
    positions = [
        (0, 0),                      # TOP - 左上
        (single_size, 0),            # FRONT - 右上
        (0, single_size),            # RIGHT - 左下
        (single_size, single_size),  # ISO - 右下
    ]

    for img, pos in zip(view_images, positions):
        combined_img.paste(img, pos)

    # 3. 保存拼接图
    combined_path = os.path.join(render_dir, "combined_views.png")
    combined_img.save(combined_path, "PNG", quality=95)

    # 4. 返回拼接图路径
    return combined_path
