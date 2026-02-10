# คู่มือการสร้างปุ่ม CTA ใน Facebook Post

## ⚠️ ข้อจำกัดของ Meta Tags

**ปุ่ม CTA (Apply Now, Learn More, Shop Now) ไม่สามารถสร้างได้ด้วย Open Graph meta tags ธรรมดา**

Facebook ไม่รองรับ meta tag สำหรับปุ่ม CTA โดยตรง การแสดงปุ่มต้องใช้:
- Facebook Graph API
- Facebook Ads Manager
- Facebook Business Manager

## 🛠 วิธีสร้างปุ่ม CTA ด้วย Facebook Graph API

### 1. เตรียมความพร้อม

#### 1.1 สร้าง Facebook App
1. ไปที่ https://developers.facebook.com/
2. สร้าง App ใหม่
3. เพิ่ม "Marketing API" product

#### 1.2 รับ Access Token
```bash
# ใช้ Graph API Explorer
https://developers.facebook.com/tools/explorer/

# หรือใช้ curl
curl -X GET "https://graph.facebook.com/v18.0/me?access_token=YOUR_ACCESS_TOKEN"
```

#### 1.3 รับ Page Access Token
```bash
# ต้องมี Page Admin permission
curl -X GET "https://graph.facebook.com/v18.0/me/accounts?access_token=YOUR_ACCESS_TOKEN"
```

### 2. สร้าง Post พร้อมปุ่ม CTA

#### 2.1 ใช้ Graph API Endpoint
```bash
POST https://graph.facebook.com/v18.0/{page-id}/feed
```

#### 2.2 Parameters ที่ต้องส่ง

```json
{
  "message": "ข้อความโพสต์ของคุณ",
  "link": "https://your-domain.com/your-slug",
  "call_to_action": {
    "type": "LEARN_MORE",
    "value": {
      "link": "https://your-domain.com/your-slug"
    }
  },
  "access_token": "YOUR_PAGE_ACCESS_TOKEN"
}
```

#### 2.3 ประเภทปุ่ม CTA ที่รองรับ

- `LEARN_MORE` - เรียนรู้เพิ่มเติม
- `SHOP_NOW` - ซื้อเลย
- `SIGN_UP` - สมัครเลย
- `BOOK_TRAVEL` - จองเลย
- `CONTACT_US` - ติดต่อเรา
- `DOWNLOAD` - ดาวน์โหลด
- `GET_QUOTE` - ขอใบเสนอราคา

### 3. ตัวอย่างโค้ด (Python)

```python
import requests

def create_facebook_post_with_cta(page_id, page_access_token, message, link, cta_type="LEARN_MORE"):
    """
    สร้าง Facebook Post พร้อมปุ่ม CTA
    
    Args:
        page_id: Facebook Page ID
        page_access_token: Page Access Token
        message: ข้อความโพสต์
        link: URL ของลิงก์
        cta_type: ประเภทปุ่ม CTA (LEARN_MORE, SHOP_NOW, SIGN_UP, etc.)
    
    Returns:
        dict: Response จาก Facebook API
    """
    url = f"https://graph.facebook.com/v18.0/{page_id}/feed"
    
    params = {
        "message": message,
        "link": link,
        "call_to_action": {
            "type": cta_type,
            "value": {
                "link": link
            }
        },
        "access_token": page_access_token
    }
    
    response = requests.post(url, json=params)
    return response.json()

# ตัวอย่างการใช้งาน
result = create_facebook_post_with_cta(
    page_id="YOUR_PAGE_ID",
    page_access_token="YOUR_PAGE_ACCESS_TOKEN",
    message="ข้อความโพสต์ของคุณ",
    link="https://your-domain.com/your-slug",
    cta_type="LEARN_MORE"
)

print(result)
```

### 4. ตัวอย่างโค้ด (JavaScript/Node.js)

```javascript
const axios = require('axios');

async function createFacebookPostWithCTA(pageId, pageAccessToken, message, link, ctaType = 'LEARN_MORE') {
    const url = `https://graph.facebook.com/v18.0/${pageId}/feed`;
    
    const params = {
        message: message,
        link: link,
        call_to_action: {
            type: ctaType,
            value: {
                link: link
            }
        },
        access_token: pageAccessToken
    };
    
    try {
        const response = await axios.post(url, params);
        return response.data;
    } catch (error) {
        console.error('Error creating Facebook post:', error.response.data);
        throw error;
    }
}

// ตัวอย่างการใช้งาน
createFacebookPostWithCTA(
    'YOUR_PAGE_ID',
    'YOUR_PAGE_ACCESS_TOKEN',
    'ข้อความโพสต์ของคุณ',
    'https://your-domain.com/your-slug',
    'LEARN_MORE'
).then(result => {
    console.log('Post created:', result);
});
```

### 5. ตัวอย่างโค้ด (cURL)

```bash
curl -X POST "https://graph.facebook.com/v18.0/{page-id}/feed" \
  -d "message=ข้อความโพสต์ของคุณ" \
  -d "link=https://your-domain.com/your-slug" \
  -d "call_to_action[type]=LEARN_MORE" \
  -d "call_to_action[value][link]=https://your-domain.com/your-slug" \
  -d "access_token=YOUR_PAGE_ACCESS_TOKEN"
```

## 📝 ข้อควรระวัง

### 1. Domain Verification
- Facebook ต้องการให้ domain ผ่านการยืนยัน (Verified Domain)
- Domain ที่ใช้ ngrok อาจไม่ทำงาน
- ควรใช้ domain จริงที่จดทะเบียนแล้ว

### 2. Permissions
- ต้องมี `pages_manage_posts` permission
- ต้องมี `pages_read_engagement` permission (ถ้าต้องการดู analytics)

### 3. Rate Limits
- Facebook มี rate limit สำหรับ API calls
- ตรวจสอบ rate limit ที่: https://developers.facebook.com/docs/graph-api/overview/rate-limiting

### 4. Access Token
- Page Access Token มีอายุจำกัด
- ต้อง refresh token เป็นระยะ
- ใช้ Long-lived Token สำหรับ production

## 🔗 เอกสารอ้างอิง

- [Facebook Graph API - Posts](https://developers.facebook.com/docs/graph-api/reference/page/feed)
- [Facebook Marketing API](https://developers.facebook.com/docs/marketing-apis)
- [Call-to-Action Buttons](https://developers.facebook.com/docs/graph-api/reference/page/feed#cta)

## 💡 Tips

1. **ใช้ Dark Post**: สร้างโพสต์แบบไม่แสดงใน timeline แต่ใช้สำหรับโฆษณา
2. **ทดสอบก่อน**: ใช้ Graph API Explorer เพื่อทดสอบก่อนเขียนโค้ด
3. **ตรวจสอบ Error**: ดู error response จาก Facebook API เพื่อ debug
4. **ใช้ Domain จริง**: เลิกใช้ ngrok และใช้ domain จริงเพื่อความน่าเชื่อถือ

