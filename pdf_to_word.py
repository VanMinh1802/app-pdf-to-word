import streamlit as st
import pdfplumber
import re
import io
import base64
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml
from docx import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="AI PDF to Word", page_icon="📄", layout="wide")
st.title("📄 Trợ lý AI: Biên tập Đề Thi & Tài Liệu")


# ==========================================
# CÁC HÀM XỬ LÝ PDF
# ==========================================
def extract_text_from_upload(uploaded_file):
    text = ""
    try:
        uploaded_file.seek(0)
        pdf_buffer = io.BytesIO(uploaded_file.read())
        with pdfplumber.open(pdf_buffer) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
    except Exception as e:
        st.error(f"❌ Lỗi đọc chữ PDF: {e}")
    return text


def extract_images_from_upload(uploaded_file):
    images = []
    try:
        uploaded_file.seek(0)
        pdf_buffer = io.BytesIO(uploaded_file.read())
        with pdfplumber.open(pdf_buffer) as pdf:
            for page in pdf.pages:
                img = page.to_image(resolution=150).original
                images.append(img)
    except Exception as e:
        st.error(f"❌ Lỗi chuyển PDF thành ảnh: {e}")
    return images


# ==========================================
# HÀM AI - CẬP NHẬT LUẬT LÀM TRỐNG CỘT
# ==========================================
EDUCATIONAL_SYSTEM_PROMPT = """Bạn là một Chuyên gia Biên tập Đề thi và Tài liệu Giáo dục Tiếng Anh.
Nhiệm vụ của bạn là định dạng lại văn bản cực kỳ CHÍNH XÁC theo cấu trúc chuẩn.
LƯU Ý TỐI QUAN TRỌNG:
1. MARKDOWN: Dùng dấu sao đôi để in đậm (**chữ**). KHÔNG dùng thẻ HTML.
2. CÂU HỎI TRẮC NGHIỆM: 
   - Bắt buộc in đậm chữ Question và số (VD: **Question 1.**). KHÔNG in đậm nội dung câu hỏi.
   - Bắt buộc in đậm các chữ cái đáp án (VD: **A.**, **B.**, **C.**, **D.**).
   - Các đáp án phải nằm trên cùng một dòng.
3. BẢNG TỪ VỰNG: 
   - CHỈ ĐƯỢC TẠO BẢNG 2 CỘT là "Word" và "Meaning". Tuyệt đối XÓA BỎ các cột thừa (Synonym, Antonym...).
   - ĐẶC BIỆT: Bạn BẮT BUỘC phải XÓA SẠCH nội dung của cột "Meaning" (để trống hoàn toàn các ô ở cột Meaning) để học sinh tự điền.
4. ĐOẠN VĂN ĐỌC HIỂU: Giữ nguyên sự liền mạch, không tự ý ngắt dòng giữa câu.
5. KHÔNG giao tiếp, KHÔNG giải thích. CHỈ TRẢ VỀ văn bản đã được biên tập."""


def process_text_with_ai(raw_text, user_prompt):
    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)
    full_prompt = f"{EDUCATIONAL_SYSTEM_PROMPT}\n\nYÊU CẦU CỦA NGƯỜI DÙNG:\n{user_prompt}\n\nNỘI DUNG TÀI LIỆU GỐC:\n<document>\n{raw_text}\n</document>"
    return model.invoke(full_prompt).content


def process_vision_with_ai(images, user_prompt):
    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)
    content = [
        {
            "type": "text",
            "text": f"{EDUCATIONAL_SYSTEM_PROMPT}\n\nHãy đọc và gõ lại nội dung từ ảnh đính kèm theo ĐÚNG YÊU CẦU DƯỚI ĐÂY:\n{user_prompt}",
        }
    ]
    for img in images:
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_str}"},
            }
        )
    return model.invoke([HumanMessage(content=content)]).content


def refine_text_with_ai(current_text, refinement_prompt, image_bytes=None):
    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)
    if image_bytes:
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        content = [
            {
                "type": "text",
                "text": f"{EDUCATIONAL_SYSTEM_PROMPT}\n\nBẢN THẢO HIỆN TẠI:\n<draft>\n{current_text}\n</draft>\n\nYÊU CẦU SỬA LỖI:\n{refinement_prompt}\n\nHãy nhìn ảnh đính kèm để căn chỉnh lại cho giống với khoảng cách/định dạng trong ảnh.",
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
            },
        ]
        return model.invoke([HumanMessage(content=content)]).content
    else:
        full_prompt = f"{EDUCATIONAL_SYSTEM_PROMPT}\n\nBẢN THẢO HIỆN TẠI:\n<draft>\n{current_text}\n</draft>\n\nYÊU CẦU SỬA LỖI:\n{refinement_prompt}"
        return model.invoke(full_prompt).content


# ==========================================
# 5. HÀM GHI FILE WORD (THUẬT TOÁN BẢNG TÀNG HÌNH)
# ==========================================
def create_word_docx(processed_text):
    doc = Document()

    style = doc.styles["Normal"]
    font = style.font
    font.name = "Times New Roman"
    font.size = Pt(12)

    title = doc.add_heading("TÀI LIỆU ĐÃ ĐƯỢC AI BIÊN TẬP", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.runs[0].font.name = "Times New Roman"
    title.runs[0].font.color.rgb = RGBColor(30, 136, 229)
    doc.add_paragraph()

    lines = processed_text.split("\n")
    current_table = None
    is_first_row = False

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            current_table = None
            continue

        # --- XỬ LÝ BẢNG TỪ VỰNG CÓ VIỀN ---
        if line_stripped.startswith("|") and line_stripped.endswith("|"):
            # BẢN SỬA LỖI: Thêm dấu hai chấm (:) vào bộ lọc để chặn các dòng như |:---|:---|
            if re.match(r"^\|[\-\|\s:]+\|$", line_stripped):
                continue

            cols = [c.strip() for c in line_stripped.split("|")[1:-1]]

            if current_table is None:
                current_table = doc.add_table(rows=0, cols=len(cols))
                current_table.style = "Table Grid"
                is_first_row = True
            else:
                is_first_row = False

            row_cells = current_table.add_row().cells
            for i, col_text in enumerate(cols):
                if i < len(row_cells):
                    cell = row_cells[i]
                    p = cell.paragraphs[0]
                    p.alignment = (
                        WD_ALIGN_PARAGRAPH.CENTER
                        if is_first_row
                        else WD_ALIGN_PARAGRAPH.LEFT
                    )

                    if is_first_row:
                        shading_elm = parse_xml(
                            r'<w:shd {} w:fill="1E88E5"/>'.format(nsdecls("w"))
                        )
                        cell._tc.get_or_add_tcPr().append(shading_elm)

                    parts = re.split(r"\*\*(.*?)\*\*", col_text)
                    for j, part in enumerate(parts):
                        run = p.add_run(part)
                        run.font.name = "Times New Roman"
                        run.font.size = Pt(12)

                        if is_first_row:
                            run.font.color.rgb = RGBColor(255, 255, 255)
                            run.bold = True
                        else:
                            run.font.color.rgb = RGBColor(0, 0, 0)
                            if j % 2 != 0:
                                run.bold = True

        # --- TẠO BẢNG TÀNG HÌNH ĐỂ ÉP CỘT TRẮC NGHIỆM A, B, C, D ---
        elif (
            "**A.**" in line
            and "**B.**" in line
            and "**C.**" in line
            and "**D.**" in line
        ):
            current_table = None

            idx_b = line.find("**B.**")
            idx_c = line.find("**C.**")
            idx_d = line.find("**D.**")

            parts_text = [
                line[:idx_b].strip(),
                line[idx_b:idx_c].strip(),
                line[idx_c:idx_d].strip(),
                line[idx_d:].strip(),
            ]

            mc_table = doc.add_table(rows=1, cols=4)
            mc_table.autofit = False

            widths = [Inches(2.3), Inches(1.4), Inches(1.4), Inches(1.4)]
            for cell, width in zip(mc_table.rows[0].cells, widths):
                cell.width = width

            for i, p_text in enumerate(parts_text):
                cell = mc_table.cell(0, i)
                p = cell.paragraphs[0]

                bold_parts = re.split(r"\*\*(.*?)\*\*", p_text)
                for j, b_part in enumerate(bold_parts):
                    run = p.add_run(b_part)
                    run.font.name = "Times New Roman"
                    run.font.size = Pt(12)
                    if j % 2 != 0:
                        run.bold = True

        # --- XỬ LÝ VĂN BẢN BÌNH THƯỜNG ---
        else:
            current_table = None
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

            parts = re.split(r"\*\*(.*?)\*\*", line)
            for i, part in enumerate(parts):
                run = p.add_run(part)
                run.text = part
                run.font.name = "Times New Roman"
                run.font.size = Pt(12)
                if i % 2 != 0:
                    run.bold = True

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream


# ==========================================
# GIAO DIỆN STREAMLIT
# ==========================================
st.markdown(
    """
    <style>
    div[data-testid="stVerticalBlock"] > div { border-radius: 12px; }
    div[data-testid="stAlert"] { border-radius: 8px; font-weight: 500; }
    table { border-collapse: collapse; width: 100%; border-radius: 8px; overflow: hidden; }
    th { background-color: #1E88E5; color: white; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "draft_text" not in st.session_state:
    st.session_state.draft_text = ""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

with st.sidebar:
    st.header("⚙️ Thiết lập ban đầu")
    uploaded_pdf = st.file_uploader("1. Tải tài liệu lên", type=["pdf"])

    default_prompt = """Biên tập tài liệu này theo đúng chuẩn form đề thi:
1. BẢNG TỪ VỰNG: CHỈ GIỮ LẠI ĐÚNG 2 CỘT là "Word" và "Meaning". ĐẶC BIỆT: Hãy XÓA SẠCH nội dung trong cột "Meaning" (để trống ô đó) để tạo bài tập điền từ. Lược bỏ tất cả các cột thừa (Synonym, Antonym...).
2. CÂU HỎI TRẮC NGHIỆM:
   - Bôi đậm chữ "Question" và số (VD: **Question 1.**).
   - Bôi đậm các đáp án (VD: **A.**, **B.**, **C.**, **D.**).
   - Các đáp án phải nằm trên cùng 1 dòng.
3. LỌC RÁC: Xóa các thông tin như Link web, số điện thoại, tên giáo viên ở đầu/cuối tài liệu."""

    user_prompt = st.text_area("2. Yêu cầu xử lý:", value=default_prompt, height=350)
    process_btn = st.button(
        "🚀 Bắt đầu tạo Bản Nháp", type="primary", use_container_width=True
    )

if process_btn:
    if not uploaded_pdf:
        st.sidebar.error("Bạn chưa tải file PDF lên!")
    else:
        with st.status("Đang phân tích tài liệu...", expanded=True) as status:
            st.write("Đang quét nội dung...")
            raw_text = extract_text_from_upload(uploaded_pdf)

            if not raw_text.strip():
                st.write("Phát hiện PDF ảnh scan! Chuyển sang Mắt thần Vision...")
                images = extract_images_from_upload(uploaded_pdf)
                result = process_vision_with_ai(images, user_prompt)
            else:
                st.write("Đang định dạng theo chuẩn đề thi...")
                result = process_text_with_ai(raw_text, user_prompt)

            st.session_state.draft_text = result
            st.session_state.chat_history = [
                {
                    "role": "assistant",
                    "content": "Tài liệu đã được định dạng. Cột Meaning đã được làm trống. Sếp kiểm tra lại nhé!",
                }
            ]
            status.update(label="Hoàn tất xử lý!", state="complete", expanded=False)
        st.rerun()

if st.session_state.draft_text:
    col_preview, col_chat = st.columns([1.2, 1], gap="large")

    with col_preview:
        st.subheader("📑 Bản thảo hiện tại")
        docx_file = create_word_docx(st.session_state.draft_text)
        st.download_button(
            label="📥 TẢI FILE WORD (.DOCX)",
            data=docx_file,
            file_name="DeThi_HoanThien.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        st.container(height=500, border=True).markdown(st.session_state.draft_text)

    with col_chat:
        st.subheader("💬 Chat với Biên Tập Viên")
        chat_container = st.container(height=350, border=True)
        with chat_container:
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    if "image" in message and message["image"]:
                        st.image(message["image"], width=200)

        uploaded_chat_img = st.file_uploader(
            "📎 Kéo thả / Chọn ảnh minh họa lỗi vào đây", type=["png", "jpg", "jpeg"]
        )

        if prompt := st.chat_input("VD: Giãn cách đáp án A B C D ra như trong ảnh"):
            img_bytes = uploaded_chat_img.getvalue() if uploaded_chat_img else None
            user_msg_display = (
                prompt
                if not img_bytes
                else f"📎 *[Đã đính kèm ảnh minh họa]*\n\n{prompt}"
            )

            st.session_state.chat_history.append(
                {"role": "user", "content": user_msg_display, "image": img_bytes}
            )

            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)
                    if img_bytes:
                        st.image(img_bytes, width=200)

            with chat_container:
                with st.chat_message("assistant"):
                    with st.spinner("👀 Đang xử lý..."):
                        new_draft = refine_text_with_ai(
                            st.session_state.draft_text, prompt, img_bytes
                        )
                        st.session_state.draft_text = new_draft
                        reply = "Đã chỉnh sửa xong theo yêu cầu!"
                        st.markdown(reply)
                        st.session_state.chat_history.append(
                            {"role": "assistant", "content": reply}
                        )

            st.rerun()
elif not uploaded_pdf:
    st.info("👈 Hãy tải file PDF Đề thi lên thanh bên trái để bắt đầu!")
