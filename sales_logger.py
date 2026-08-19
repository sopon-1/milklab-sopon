"""MusicLab Sales Logger (S2).

Usage:
    python sales_logger.py --item "สายกีตาร์โปร่ง" --qty 2 --price 250

Reads GOOGLE_SHEETS_CREDENTIALS and TELEGRAM_BOT_TOKEN (or LINE_CHANNEL_TOKEN) from env.
Appends row [timestamp, item, qty, price, total] to a Google Sheet,
then sends a notification via Telegram or LINE bot.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import requests

from dotenv import load_dotenv
load_dotenv()


def append_to_sheet(item: str, qty: int, price: float) -> dict:
    """ใช้ gspread เปิด Sheet ของตัวเอง แล้ว append_row ด้วย [timestamp, item, qty, price, total]

    Returns dict {timestamp, item, qty, price, total} ที่ append แล้ว
    Raises RuntimeError ถ้า credentials ไม่มี หรือ Sheet ไม่ accessible
    """
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        raise RuntimeError("ไม่พบ GOOGLE_SHEETS_CREDENTIALS ใน Environment")

    try:
        # แปลง JSON string เป็น dict และตั้งสิทธิ์
        creds_data = json.loads(creds_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"
                  ]
        credentials = Credentials.from_service_account_info(
            creds_data, scopes=scopes)

        gc = gspread.authorize(credentials)
        sh = gc.open("sales-logger")
        worksheet = sh.get_worksheet(0)

        # คำนวณค่าเพื่อเตรียมบันทึก
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total = qty * price

        row_data = [timestamp, item, qty, price, total]
        worksheet.append_row(row_data)

        return {
            "timestamp": timestamp,
            "item": item,
            "qty": qty,
            "price": price,
            "total": total
        }
    except Exception as e:
        raise RuntimeError(f"ไม่สามารถเข้าถึงหรือบันทึก Sheet ได้: {e}")


def send_notification(message: str) -> str:
    """ส่ง message ไปยัง Telegram bot หรือ LINE Messaging API"""
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    line_token = os.environ.get("LINE_CHANNEL_TOKEN")
    line_user_id = os.environ.get("LINE_USER_ID")

    # 1. เช็กฝั่ง Telegram
    if telegram_token and telegram_chat_id:
        url = f"https://api.telegram.com/bot{telegram_token}/sendMessage"
        payload = {"chat_id": telegram_chat_id, "text": message}
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                return "telegram"
            else:
                raise RuntimeError(
                    f"Telegram API ส่งไม่สำเร็จ: {response.text}")
        except Exception as e:
            raise RuntimeError(f"เกิดข้อผิดพลาดในการเชื่อมต่อ Telegram: {e}")

    # 2. เช็กฝั่ง LINE Messaging API (Push Message)
    elif line_token and line_user_id:
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}"
        }
        payload = {
            "to": line_user_id,
            "messages": [
                {
                    "type": "text",
                    "text": message
                }
            ]
        }
        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                return "line"
            else:
                raise RuntimeError(f"LINE API ส่งไม่สำเร็จ: {response.text}")
        except Exception as e:
            raise RuntimeError(f"เกิดข้อผิดพลาดในการเชื่อมต่อ LINE: {e}")

    else:
        raise RuntimeError(
            "ไม่พบการตั้งค่าแจ้งเตือน (ต้องมี TELEGRAM_BOT_TOKEN+CHAT_ID หรือ LINE_CHANNEL_TOKEN+LINE_USER_ID)")


def main() -> int:
    parser = argparse.ArgumentParser(description="MusicLab Sales Logger")
    parser.add_argument("--item", required=True, help="ชื่อสินค้าหรือบริการ")
    parser.add_argument("--qty", type=int, required=True, help="จำนวน")
    parser.add_argument("--price", type=float,
                        required=True, help="ราคาต่อหน่วย")
    args = parser.parse_args()

    try:
        row = append_to_sheet(args.item, args.qty, args.price)
        total = row["total"]
    except Exception as exc:
        print(f"[ERROR] บันทึก Sheet ล้มเหลว: {exc}", file=sys.stderr)
        print("[HINT] ตรวจ GOOGLE_SHEETS_CREDENTIALS และ share Sheet กับ service account email", file=sys.stderr)
        return 1

    try:
        provider = send_notification(
            f"🎸 บันทึกยอดขาย MusicLab° สำเร็จ!\n📝 สินค้า/บริการ: {args.item}\n📦 จำนวน: {args.qty} ชิ้น\n💰 ยอดรวม: {total} บาท")
    except Exception as exc:
        print(
            f"[WARN] บันทึก Sheet สำเร็จแต่ส่งแจ้งเตือนล้มเหลว: {exc}", file=sys.stderr)
        raise exc

    print(f"[OK] บันทึกและแจ้งเตือนผ่าน {provider} เรียบร้อย ยอด {total} บาท")
    return 0


if __name__ == "__main__":
    sys.exit(main())
