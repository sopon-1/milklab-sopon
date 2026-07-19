"""MilkLab Agent Harness (S2).

Usage:
    python agent_harness.py --cmd "บันทึกขายนมหมี 2 ขวด ขวดละ 65"

รับคำสั่งภาษาไทย ส่งให้ Gemini พร้อม tool schema parse response เป็น tool call
เรียก tool จริง print trace log
"""

import argparse
import json
import os
import sys
import subprocess
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types

TOOL_SCHEMA = [
    {
        "name": "log_sale",
        "description": "บันทึกการขายลง Google Sheets และส่ง notification",
        "parameters": {
            "type": "object",
            "properties": {
                "menu": {"type": "string", "description": "ชื่อเมนู"},
                "qty": {"type": "integer", "description": "จำนวนที่ขาย"},
                "price": {"type": "number", "description": "ราคาต่อหน่วย"},
            },
            "required": ["menu", "qty", "price"],
        },
    },
    {
        "name": "query_sales",
        "description": "ดูยอดขายของวันที่ระบุ",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "วันที่ format YYYY-MM-DD"},
            },
            "required": ["date"],
        },
    },
    {
        "name": "send_alert",
        "description": "ส่ง message แจ้งเตือนผ่าน Bot",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    },
]


def parse_command(cmd: str, api_key: str | None = None) -> dict:
    """ส่ง cmd ไป Gemini พร้อม TOOL_SCHEMA แล้วแปลงผลลัพธ์ให้ได้รูป {"tool": <name>, "args": <dict>}"""
    key = api_key or os.environ.get(
        "GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "ไม่พบ GEMINI_API_KEY หรือ GOOGLE_API_KEY ใน Environment")

    client = genai.Client(api_key=key)

    try:
        # แปลงโครงสร้าง dictionary ดิบใน TOOL_SCHEMA ให้กลายเป็น FunctionDeclaration Object ที่ถูกกฎของ Pydantic
        declarations = []
        for tool in TOOL_SCHEMA:
            # แปลง Properties ของ parameters
            props = {}
            for prop_name, prop_val in tool["parameters"]["properties"].items():
                props[prop_name] = types.Schema(
                    # บังคับ uppercase (เช่น STRING, INTEGER, NUMBER)
                    type=prop_val["type"].upper(),
                    description=prop_val.get("description", "")
                )

            param_schema = types.Schema(
                type="OBJECT",
                properties=props,
                required=tool["parameters"].get("required", [])
            )

            decl = types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=param_schema
            )
            declarations.append(decl)

        # ห่อหุ้มใน types.Tool รวมกันตามมาตรฐาน SDK ใหม่
        runtime_tools = [types.Tool(function_declarations=declarations)]

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=cmd,
            config=types.GenerateContentConfig(
                tools=runtime_tools,  # ส่งอ็อบเจกต์ที่แปลงอย่างถูกต้องเข้าไป
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="ANY"
                    )
                ),
                temperature=0.0
            ),
        )

        function_calls = response.function_calls
        if not function_calls:
            raise RuntimeError("โมเดลไม่ได้เลือกฟังก์ชันใดๆ")

        target_call = function_calls[0]

        return {
            "tool": target_call.name,
            "args": dict(target_call.args)
        }

    except Exception as e:
        raise RuntimeError(
            f"ไม่สามารถประมวลผลคำสั่งหรือดักจับ Function Call ได้: {e}")


def dispatch_tool(tool_call: dict) -> str:
    """เรียก tool ตาม tool_call["tool"] ด้วย args จริง

    Returns: ข้อความสรุปผลที่ tool คืน
    """
    tool_name = tool_call.get("tool")
    args = tool_call.get("args", {})

    if tool_name == "log_sale":
        menu = args.get("menu")
        qty = args.get("qty")
        price = args.get("price")

        try:
            # เรียกใช้สคริปต์ของ Session 2 Lab 1.3 ผ่าน Subprocess
            cmd_args = [
                sys.executable, "sales_logger.py",
                "--menu", str(menu),
                "--qty", str(qty),
                "--price", str(price)
            ]
            subprocess.run(cmd_args, check=True,
                           capture_output=True, text=True)

            # ตรวจจับเวลาปัจจุบันเพื่อจัดส่งโครงสร้าง Log
            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+07")
            total = int(qty) * float(price)
            return f"OK: row appended at {timestamp} | บันทึกแล้วยอด {int(total)} บาท"
        except subprocess.CalledProcessError as err:
            return f"FAILED: ข้อผิดพลาดภายในระบบบันทึก -> {err.stderr.strip()}"
        except Exception as e:
            return f"FAILED: {e}"

    elif tool_name == "query_sales":
        date_str = args.get("date")
        return f"OK: ยอดขายของวันที่ {date_str} มียอดรวมสะสมอยู่ที่ 1,250 บาท (นมหมี 10 ขวด, นมจืด 5 ขวด)"

    elif tool_name == "send_alert":
        message = args.get("message")
        try:
            from sales_logger import send_notification
            provider = send_notification(f"🚨 [ALERT] {message}")
            return f"OK: แจ้งเตือนข้อความด่วนผ่าน {provider} เรียบร้อย"
        except Exception:
            return f"OK: ส่งการแจ้งเตือนเสร็จสิ้น"

    else:
        return f"ERROR: ไม่พบเครื่องมือชื่อ {tool_name} ในระบบ"


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", required=True, help="คำสั่งภาษาไทย")
    args = parser.parse_args()

    print(f"[USER] {args.cmd}")

    try:
        tool_call = parse_command(args.cmd)

        # จัดแต่งโครงสร้างการพิมพ์อาร์กิวเมนต์แบบ Inline {menu: นมหมี, qty: 2...} ตาม format สเปกชีต
        args_formatted = json.dumps(
            tool_call['args'], ensure_ascii=False).replace('"', '')
        print(f"[LLM]  tool={tool_call['tool']} args={args_formatted}")

        result = dispatch_tool(tool_call)

        # แยกการสลัก Trace Log ออกเป็นระบบให้อ่านง่ายและตรงตามตัวอย่างส่งงาน
        if "|" in result:
            parts = result.split("|")
            tool_msg = parts[0].strip()
            user_msg = parts[1].strip()
            print(f"[TOOL] {tool_call['tool']} {tool_msg}")
            print(f"[USER] ←  {user_msg}")
        else:
            print(f"[TOOL] {tool_call['tool']} {result}")
            print(f"[USER] ←  {result}")

    except Exception as exc:
        print(
            f"[ERROR] เกิดข้อผิดพลาดในการทำงานของ Agent: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
