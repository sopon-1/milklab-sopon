import os
import streamlit as st
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
from dotenv import load_dotenv

# โหลดค่าจากไฟล์ .env เข้าสู่ Environment Variables
load_dotenv()

# เช็กจาก Environment Variable (ที่ดึงมาจาก .env) หรือจาก st.secrets (สำหรับตอนขึ้น HF Spaces / Streamlit Cloud)
if os.environ.get("GEMINI_API_KEY"):
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
elif "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])


@st.cache_resource
def load_index():
    """โหลด menu_kb.md, split เป็น chunk, encode ด้วย sentence-transformers,
    สร้าง faiss index. Cache เพราะโหลด model ครั้งแรกใช้เวลา

    Returns: (model, index, chunks_list)
    """
    model = SentenceTransformer(
        'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

    kb_path = "menu_kb.md"
    if not os.path.exists(kb_path):
        raise FileNotFoundError(f"ไม่พบไฟล์ {kb_path} กรุณาตรวจสอบตำแหน่งไฟล์")

    with open(kb_path, "r", encoding="utf-8") as f:
        kb_text = f.read()

    chunks_list = [c.strip() for c in kb_text.split("\n\n") if c.strip()]

    embeddings = model.encode(chunks_list)
    dimension = embeddings.shape[1]

    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings).astype('float32'))

    return model, index, chunks_list


def retrieve_top_k(query: str, model, index, chunks: list[str], k: int = 5) -> list[str]:
    """encode query, search index, return top-k chunks"""
    query_vector = model.encode([query]).astype('float32')
    distances, indices = index.search(query_vector, k)

    retrieved_chunks = []
    for idx in indices[0]:
        if idx != -1 and idx < len(chunks):
            retrieved_chunks.append(chunks[idx])

    return retrieved_chunks


def generate_answer(query: str, context_chunks: list[str]) -> str:
    """ส่ง query + context ไป Gemini, return answer"""
    context_text = "\n---\n".join(context_chunks)

    prompt = f"""คุณคือ "น้องมิลค์" AI สาวน้อยประจำร้าน MilkLab 🥛✨ 
บุคลิกน่ารัก สดใส เป็นกันเอง และพูดจาลงท้ายด้วย "นะคะ/ค่ะ" หรือคำว่า "น้า~" อย่างสุภาพและน่าเอ็นดู

หน้าที่ของคุณคือช่วยตอบคำถามลูกค้า โดยอ้างอิงข้อมูลจาก [Context] ด้านล่างนี้เท่านั้น:

[คำแนะนำในการตอบคำถาม]:
1. วิเคราะห์ความเชื่อมโยงของส่วนผสมอย่างชาญฉลาด เช่น:
   - "Lactose (แลคโตส)" คือน้ำตาลชนิดหนึ่งตามธรรมชาติในนมวัว หากลูกค้าถามถึง "น้ำตาล" หรือ "เมนูไม่มีน้ำตาล" ให้เชื่อมโยงข้อมูลเรื่อง Lactose มาตอบให้ลูกค้าเข้าใจด้วยนะคะ
   - หากลูกค้าถามเรื่องสารก่อภูมิแพ้หรือส่วนผสม ให้เชื่อมโยงคำที่เกี่ยวข้องจาก Context ได้ค่ะ (เช่น กลูเตน = แป้งสาลี)
2. หากไม่พบข้อมูลใน Context เลยจริงๆ ให้ตอบอย่างน่ารักว่า "ขออภัยด้วยน้าา ทางร้านยังไม่มีข้อมูลส่วนนี้ในระบบเลยค่ะ 🥺"
3. ห้ามมโนหรือคิดส่วนผสมขึ้นมาเองเด็ดขาดหากไม่มีใน Context

[Context]
{context_text}

[คำถามจากลูกค้า]
{query}
"""

    try:
        llm_model = genai.GenerativeModel("gemini-3.5-flash")
        response = llm_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"อุ๊ย! เกิดข้อผิดพลาดในการเชื่อมต่อกับ Gemini API ค่ะ: {str(e)}"


def main():
    st.set_page_config(page_title="MilkLab° RAG", page_icon="🥛")
    st.title("MilkLab° RAG Chatbot 🍓🥛")
    st.caption(
        "ถามอะไรเกี่ยวกับ MilkLab ได้เลยน้า~ น้องมิลค์พร้อมตอบจาก menu_kb.md ค่ะ!")

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

    if prompt := st.chat_input("ถามน้องมิลค์ได้เลยนะคะ..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("น้องมิลค์กำลังเปิดสมุดค้นข้อมูลให้นะคะ... ✨"):
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
