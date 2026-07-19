import os
import streamlit as st
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
from dotenv import load_dotenv

# โหลดค่าจากไฟล์ .env เข้าสู่ Environment Variables
load_dotenv()

# เช็กจาก Environment Variable (ที่ดึงมาจาก .env) หรือจาก st.secrets (สำหรับตอนขึ้น HF Spaces)
if os.environ.get("GEMINI_API_KEY"):
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
elif "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])


@st.cache_resource
def load_index():
    """TODO 1+2+3: โหลด menu_kb.md, split เป็น chunk, encode ด้วย sentence-transformers,
    สร้าง faiss index. Cache เพราะโหลด model ครั้งแรกใช้เวลา 30 วินาที

    Returns: (model, index, chunks_list)
    """
    # [TODO 1]: โหลดโมเดลสำหรับทำ Embedding (ตัวเล็ก, รองรับภาษาไทย/อังกฤษได้ดี)
    model = SentenceTransformer(
        'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

    # [TODO 2]: อ่านไฟล์ menu_kb.md และ Split เป็น chunks
    kb_path = "menu_kb.md"
    if not os.path.exists(kb_path):
        # Fallback ในกรณีที่หาไฟล์ไม่เจอ (เช่น พาธผิดพลาดบนระบบคลาวด์)
        raise FileNotFoundError(f"ไม่พบไฟล์ {kb_path} กรุณาตรวจสอบตำแหน่งไฟล์")

    with open(kb_path, "r", encoding="utf-8") as f:
        kb_text = f.read()

    # หั่น chunk ด้วยการขึ้นบรรทัดใหม่คู่ (\n\n) เพื่อแยกตามหัวข้อหรือเมนูย่อย
    chunks_list = [c.strip() for c in kb_text.split("\n\n") if c.strip()]

    # [TODO 3]: แปลง chunk เป็น embedding vectors และสร้าง FAISS Index
    embeddings = model.encode(chunks_list)
    dimension = embeddings.shape[1]

    # สร้าง IndexFlatL2 ของ FAISS และเพิ่มเวกเตอร์เข้าไป
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings).astype('float32'))

    return model, index, chunks_list


def retrieve_top_k(query: str, model, index, chunks: list[str], k: int = 3) -> list[str]:
    """TODO 4: encode query, search index, return top-k chunks"""
    # 1. แปลงคำถามของ User ให้เป็น Vector
    query_vector = model.encode([query]).astype('float32')

    # 2. ค้นหาใน FAISS index เพื่อหาชิ้นข้อมูลที่ใกล้เคียงที่สุดจำนวน k ตัว
    distances, indices = index.search(query_vector, k)

    # 3. ดึงข้อความดิบ (String) จากลิสต์ chunks ออกมาตามตำแหน่งดัชนีที่ค้นพบ
    retrieved_chunks = []
    for idx in indices[0]:
        if idx != -1 and idx < len(chunks):  # ป้องกันกรณี index หลุดขอบข่าย
            retrieved_chunks.append(chunks[idx])

    return retrieved_chunks


def generate_answer(query: str, context_chunks: list[str]) -> str:
    """TODO 5: ส่ง query + context ไป Gemini, return answer

    Hint: build prompt that says "ตอบจากข้อมูลต่อไปนี้เท่านั้น ถ้าไม่มีใน context ให้บอกว่าไม่รู้"
    """
    # 1. รวมเศษ chunk ทั้งหมดที่ดึงมาได้ให้กลายเป็นข้อความ Context ก้อนเดียว
    context_text = "\n---\n".join(context_chunks)

    # 2. ออกแบบ System Prompt บังคับให้ตอบเฉพาะในกรอบข้อมูล เพื่อเลี่ยงปัญหา AI มโน (Hallucination)
    prompt = f"""คุณคือ AI Assistant ประจำร้าน MilkLab หน้าที่ของคุณคือตอบคำถามลูกค้าอย่างสุภาพ 
และต้องตอบคำถามโดยใช้ข้อมูลจาก [Context] ที่กำหนดให้ด้านล่างนี้เท่านั้น 
หากไม่พบคำตอบใน Context ให้ตอบว่า "ขออภัยด้วยค่ะ ทางร้านยังไม่มีข้อมูลส่วนนี้ในระบบ" และห้ามคาดเดาหรือสร้างคำตอบขึ้นมาเองโดยเด็ดขาด

[Context]
{context_text}

[คำถามจากลูกค้า]
{query}
"""

    try:
        # 3. เรียกใช้งานโมเดล Gemini 1.5 Flash
        llm_model = genai.GenerativeModel("gemini-2.5-flash")
        response = llm_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"เกิดข้อผิดพลาดในการเชื่อมต่อกับ Gemini API: {str(e)}"


def main():
    st.set_page_config(page_title="MilkLab° RAG", page_icon="🥛")
    st.title("MilkLab° RAG Chatbot")
    st.caption("ถามอะไรเกี่ยวกับ MilkLab ได้ ตอบจาก menu_kb.md")

    try:
        model, index, chunks = load_index()
    except NotImplementedError as exc:
        st.error(f"TODO not implemented: {exc}")
        st.stop()
    except Exception as exc:
        st.error(f"Error loading RAG Index: {exc}")
        st.stop()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("ถามอะไรเกี่ยวกับ MilkLab"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("กำลังค้นข้อมูล..."):
                context = retrieve_top_k(prompt, model, index, chunks)
                answer = generate_answer(prompt, context)
            st.write(answer)
            with st.expander("Source chunks"):
                for i, c in enumerate(context, 1):
                    st.markdown(f"**[{i}]** {c}")
        st.session_state.messages.append(
            {"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
