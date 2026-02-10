"""
Facebook Graph API Helper
สำหรับสร้าง Facebook Post พร้อมปุ่ม CTA

⚠️ หมายเหตุ: ปุ่ม CTA ไม่สามารถสร้างได้ด้วย Open Graph meta tags ธรรมดา
ต้องใช้ Facebook Graph API หรือ Ads Manager เท่านั้น
"""

import requests
from typing import Optional, Dict, Any


class FacebookPostCreator:
    """Helper class สำหรับสร้าง Facebook Post พร้อมปุ่ม CTA"""
    
    # ประเภทปุ่ม CTA ที่รองรับ
    CTA_TYPES = [
        "LEARN_MORE",      # เรียนรู้เพิ่มเติม
        "SHOP_NOW",        # ซื้อเลย
        "SIGN_UP",         # สมัครเลย
        "BOOK_TRAVEL",     # จองเลย
        "CONTACT_US",      # ติดต่อเรา
        "DOWNLOAD",        # ดาวน์โหลด
        "GET_QUOTE",       # ขอใบเสนอราคา
    ]
    
    def __init__(self, page_id: str, page_access_token: str, api_version: str = "v18.0"):
        """
        Initialize Facebook Post Creator
        
        Args:
            page_id: Facebook Page ID
            page_access_token: Page Access Token (ต้องมี pages_manage_posts permission)
            api_version: Facebook Graph API version (default: v18.0)
        """
        self.page_id = page_id
        self.page_access_token = page_access_token
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{api_version}"
    
    def create_post_with_cta(
        self,
        message: str,
        link: str,
        cta_type: str = "LEARN_MORE",
        published: bool = True
    ) -> Dict[str, Any]:
        """
        สร้าง Facebook Post พร้อมปุ่ม CTA
        
        Args:
            message: ข้อความโพสต์
            link: URL ของลิงก์ (ควรเป็น domain จริง ไม่ใช่ ngrok)
            cta_type: ประเภทปุ่ม CTA (LEARN_MORE, SHOP_NOW, SIGN_UP, etc.)
            published: True = โพสต์ทันที, False = Draft (Dark Post)
        
        Returns:
            dict: Response จาก Facebook API
                - success: True/False
                - post_id: ID ของโพสต์ที่สร้าง (ถ้าสำเร็จ)
                - error: ข้อความ error (ถ้าเกิดข้อผิดพลาด)
        
        Example:
            >>> creator = FacebookPostCreator("page_id", "access_token")
            >>> result = creator.create_post_with_cta(
            ...     message="ข้อความโพสต์",
            ...     link="https://your-domain.com/slug",
            ...     cta_type="LEARN_MORE"
            ... )
            >>> if result["success"]:
            ...     print(f"Post created: {result['post_id']}")
        """
        if cta_type not in self.CTA_TYPES:
            return {
                "success": False,
                "error": f"Invalid CTA type. Must be one of: {', '.join(self.CTA_TYPES)}"
            }
        
        url = f"{self.base_url}/{self.page_id}/feed"
        
        params = {
            "message": message,
            "link": link,
            "call_to_action": {
                "type": cta_type,
                "value": {
                    "link": link
                }
            },
            "published": published,
            "access_token": self.page_access_token
        }
        
        try:
            response = requests.post(url, json=params)
            response.raise_for_status()
            data = response.json()
            
            return {
                "success": True,
                "post_id": data.get("id"),
                "data": data
            }
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                except:
                    pass
            
            return {
                "success": False,
                "error": error_msg
            }
    
    def create_dark_post(
        self,
        message: str,
        link: str,
        cta_type: str = "LEARN_MORE"
    ) -> Dict[str, Any]:
        """
        สร้าง Dark Post (โพสต์ที่ไม่แสดงใน timeline แต่ใช้สำหรับโฆษณา)
        
        Args:
            message: ข้อความโพสต์
            link: URL ของลิงก์
            cta_type: ประเภทปุ่ม CTA
        
        Returns:
            dict: Response จาก Facebook API
        """
        return self.create_post_with_cta(
            message=message,
            link=link,
            cta_type=cta_type,
            published=False
        )


def create_facebook_post_with_cta(
    page_id: str,
    page_access_token: str,
    message: str,
    link: str,
    cta_type: str = "LEARN_MORE",
    published: bool = True
) -> Dict[str, Any]:
    """
    Function helper สำหรับสร้าง Facebook Post พร้อมปุ่ม CTA
    
    Args:
        page_id: Facebook Page ID
        page_access_token: Page Access Token
        message: ข้อความโพสต์
        link: URL ของลิงก์
        cta_type: ประเภทปุ่ม CTA (default: LEARN_MORE)
        published: True = โพสต์ทันที, False = Draft
    
    Returns:
        dict: Response จาก Facebook API
    
    Example:
        >>> result = create_facebook_post_with_cta(
        ...     page_id="123456789",
        ...     page_access_token="your_token",
        ...     message="ข้อความโพสต์",
        ...     link="https://your-domain.com/slug",
        ...     cta_type="LEARN_MORE"
        ... )
        >>> print(result)
    """
    creator = FacebookPostCreator(page_id, page_access_token)
    return creator.create_post_with_cta(message, link, cta_type, published)


def create_cta_post(
    page_id: str,
    access_token: str,
    link_url: str,
    image_url: str,
    title: str,
    message: str,
    cta_type: str = "APPLY_NOW",
    api_version: str = "v19.0",
) -> Dict[str, Any]:
    """
    ตัวอย่าง helper แบบ raw ตามโค้ดที่คุณให้มา

    Args:
        page_id: Facebook Page ID
        access_token: Page Access Token (ต้องมี pages_manage_posts)
        link_url: ลิงก์ปลายทาง (ลิงก์หน้ากากของคุณ)
        image_url: URL รูปภาพ (เช่น รูป Grid 4 ช่องที่ตัดต่อแล้ว)
        title: ชื่อที่จะโชว์ใน Preview
        message: ข้อความโพสต์
        cta_type: ประเภทปุ่ม CTA (เช่น APPLY_NOW, LEARN_MORE, SHOP_NOW)
        api_version: เวอร์ชัน Graph API (default: v19.0)

    Returns:
        dict: JSON response ดิบจาก Facebook API
    """
    url = f"https://graph.facebook.com/{api_version}/{page_id}/feed"

    call_to_action = {
        "type": cta_type,
        "value": {
            "link": link_url,
        },
    }

    payload = {
        "message": message,
        "link": link_url,
        "picture": image_url,
        "name": title,
        "call_to_action": call_to_action,
        "access_token": access_token,
    }

    # Graph API ส่วนใหญ่คาดหวัง form-encoded; ถ้าอยากตรงกับโค้ดเดิมใช้ json=payload ก็ได้
    resp = requests.post(url, json=payload)
    try:
        return resp.json()
    except ValueError:
        return {"error": "Invalid JSON response", "status_code": resp.status_code, "text": resp.text}


# ตัวอย่างการใช้งาน
if __name__ == "__main__":
    # ⚠️ ใส่ค่าเหล่านี้จาก Facebook Developer Console
    PAGE_ID = "your_page_id"
    PAGE_ACCESS_TOKEN = "your_page_access_token"
    
    # สร้าง Post พร้อมปุ่ม CTA
    result = create_facebook_post_with_cta(
        page_id=PAGE_ID,
        page_access_token=PAGE_ACCESS_TOKEN,
        message="ข้อความโพสต์ของคุณ",
        link="https://your-domain.com/your-slug",
        cta_type="LEARN_MORE"
    )
    
    if result["success"]:
        print(f"✅ Post created successfully!")
        print(f"Post ID: {result['post_id']}")
    else:
        print(f"❌ Error: {result['error']}")

