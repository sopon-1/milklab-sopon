"""MilkLab Caption Generator (S1).

Usage:
    python caption_generator.py

Reads GOOGLE_API_KEY from env. Generates a Thai caption for a milk menu item.
"""

import os
import sys

from dotenv import load_dotenv
from google import genai


PROMPT_TEMPLATE = """\
คุณคือ social media manager ของร้าน MusicLab° ร้านขายเครื่องดนตรี อะไหล่ และบริการ Setup กีตาร์

จงเขียนแคปชั่นภาษาไทย 2 ถึง 3 ประโยคเพื่อโปรโมตสินค้าหรือบริการ: {menu}

เงื่อนไข:
- ใช้โทนตื่นเต้น เป็นมิตร เข้าใจความรู้สึกของนักดนตรี ใส่ emoji ที่เกี่ยวกับดนตรีได้ (เช่น 🎸, 🎶, ⚡)
- ต้องมี call-to-action ปิดท้าย เช่น ทักแชทสอบถาม หรือ จองคิวเลย
- ห้ามใช้ em dash
"""


def generate_caption(menu: str, api_key: str | None = None) -> str:
    """Generate a Thai caption for the given milk menu item."""
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("ไม่พบ GEMINI_API_KEY หรือ GOOGLE_API_KEY ใน Environment")
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=PROMPT_TEMPLATE.format(menu=menu),
    )
    return response.text or ""


def main() -> int:
    load_dotenv()
    menu = input("สินค้าหรือบริการที่จะโปรโมต (เช่น สายกีตาร์โปร่ง Ernie Ball): ").strip()
    if not menu:
        print("กรุณาใส่ชื่อเมนู")
        return 1
    caption = generate_caption(menu)
    print()
    print(caption)
    return 0


if __name__ == "__main__":
    sys.exit(main())
