"""
Grid Image Helper
สำหรับสร้างรูป Grid 2x2 สไตล์ Facebook Link Preview (1200x628)

ตัวอย่างการใช้งาน:

    from grid_image_helper import create_fb_grid_image

    imgs = ["pic1.jpg", "pic2.jpg", "pic3.jpg", "pic4.jpg"]
    create_fb_grid_image(imgs, output_path="final_grid.jpg")
"""

from typing import List, Optional

try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None


def create_fb_grid_image(
    image_paths: List[str],
    output_path: str = "final_grid.jpg",
    font_path: Optional[str] = "arial.ttf",
    extra_count: int = 9,
) -> str:
    """
    สร้างรูป Grid 2x2 สำหรับใช้เป็น Facebook Link Image (1200 x 628)

    Args:
        image_paths: list ของ path รูป (จะใช้สูงสุด 4 รูปแรก)
        output_path: path ไฟล์ที่ต้องการบันทึกผลลัพธ์
        font_path: path ของไฟล์ฟอนต์สำหรับเขียน "+9" (ถ้าไม่มีจะข้าม text)
        extra_count: จำนวนรูปเพิ่มเติมที่ต้องการแสดงใน "+9"

    Returns:
        str: path ของไฟล์รูปที่บันทึกแล้ว
    """
    if Image is None:
        raise RuntimeError("Pillow (PIL) ไม่ได้ถูกติดตั้ง ไม่สามารถสร้าง Grid Image ได้")

    if not image_paths:
        raise ValueError("image_paths ต้องมีอย่างน้อย 1 รูป")

    # ขนาดมาตรฐานสำหรับ Facebook Link Image (1200 x 628)
    canvas_width = 1200
    canvas_height = 628
    grid_img = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))

    # คำนวณขนาดแต่ละช่อง (2x2 Grid)
    box_w = canvas_width // 2
    box_h = canvas_height // 2

    for i, path in enumerate(image_paths[:4]):  # เอาแค่ 4 รูปแรก
        img = Image.open(path).convert("RGB")

        # Crop และ Resize ให้พอดีช่อง (รักษาอัตราส่วน)
        img_ratio = img.width / img.height
        target_ratio = box_w / box_h
        if img_ratio > target_ratio:
            # รูปกว้างเกิน -> crop ซ้าย/ขวา
            new_w = int(target_ratio * img.height)
            left = (img.width - new_w) // 2
            img = img.crop((left, 0, left + new_w, img.height))
        else:
            # รูปสูงเกิน -> crop บน/ล่าง
            new_h = int(img.width / target_ratio)
            top = (img.height - new_h) // 2
            img = img.crop((0, top, img.width, top + new_h))

        img = img.resize((box_w, box_h), Image.Resampling.LANCZOS)

        # วางรูปในตำแหน่งที่กำหนด
        x = (i % 2) * box_w
        y = (i // 2) * box_h
        grid_img.paste(img, (x, y))

        # ใส่ Effect +9 ในรูปที่ 4 (ช่องล่างขวา)
        if i == 3 and extra_count > 0:
            if ImageDraw is None:
                continue

            overlay = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 150))  # สีดำโปร่งแสง
            grid_img.paste(overlay, (x, y), overlay)
            draw = ImageDraw.Draw(grid_img)

            text = f"+{extra_count}"
            try:
                font = ImageFont.truetype(font_path, 100) if font_path else ImageFont.load_default()
            except Exception:
                # ถ้าหา font ไม่เจอ ใช้ default แทน
                font = ImageFont.load_default()

            text_w, text_h = draw.textsize(text, font=font)
            tx = x + (box_w - text_w) // 2
            ty = y + (box_h - text_h) // 2
            draw.text((tx, ty), text, fill=(255, 255, 255), font=font)

    grid_img.save(output_path, quality=95)
    return output_path


if __name__ == "__main__":
    # ตัวอย่างการใช้งานแบบ standalone
    sample_imgs = ["pic1.jpg", "pic2.jpg", "pic3.jpg", "pic4.jpg"]
    out = create_fb_grid_image(sample_imgs, output_path="final_grid.jpg")
    print(f"บันทึกไฟล์สำเร็จที่: {out}")


