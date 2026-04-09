import streamlit as st
import pdfplumber
import re
import io
import base64
import pandas as pd
import json
import csv
import time
import concurrent.futures
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
# HÀM AI - CẬP NHẬT LUẬT MỀM DẺO CHO BẢNG
# ==========================================
EDUCATIONAL_SYSTEM_PROMPT = """Bạn là một Chuyên gia Biên tập Đề thi và Tài liệu Giáo dục Tiếng Anh.
Nhiệm vụ của bạn là định dạng lại văn bản cực kỳ CHÍNH XÁC theo cấu trúc chuẩn.
LƯU Ý TỐI QUAN TRỌNG:
1. MARKDOWN: Dùng dấu sao đôi để in đậm (**chữ**). KHÔNG dùng thẻ HTML.
2. CÂU HỎI TRẮC NGHIỆM: 
   - Bắt buộc in đậm chữ Question và số (VD: **Question 1.**). KHÔNG in đậm nội dung câu hỏi.
   - Bắt buộc in đậm các chữ cái đáp án (VD: **A.**, **B.**, **C.**, **D.**).
   - Các đáp án phải nằm trên cùng một dòng.
3. BẢNG BIỂU: Xử lý số lượng cột, nội dung cột CHÍNH XÁC theo yêu cầu của người dùng. Hãy linh hoạt thêm, bớt hoặc làm trống nội dung theo đúng mệnh lệnh.
4. LỌC RÁC: Xóa các thông tin như Link web, số điện thoại, tên giáo viên ở đầu/cuối tài liệu.
5. ĐOẠN VĂN ĐỌC HIỂU: Giữ nguyên sự liền mạch, không tự ý ngắt dòng giữa câu.
6. KHÔNG giao tiếp, KHÔNG giải thích. CHỈ TRẢ VỀ văn bản đã được biên tập."""


def process_text_with_ai(raw_text, user_prompt):
    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)
    full_prompt = f"{EDUCATIONAL_SYSTEM_PROMPT}\n\nYÊU CẦU CỦA NGƯỜI DÙNG:\n{user_prompt}\n\nNỘI DUNG TÀI LIỆU GỐC:\n<document>\n{raw_text}\n</document>"
    return model.invoke(full_prompt).content


# --- Hàm phụ để xử lý từng lô (Batch) ---
def process_single_batch(batch_images, batch_index, total_batches, user_prompt):
    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)

    content = [
        {
            "type": "text",
            "text": f"{EDUCATIONAL_SYSTEM_PROMPT}\n\nYêu cầu: {user_prompt}\n(Đây là Phần {batch_index}/{total_batches})",
        }
    ]

    for img in batch_images:
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_str}"},
            }
        )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            return model.invoke([HumanMessage(content=content)]).content
        except Exception as e:
            if ("503" in str(e) or "429" in str(e)) and attempt < max_retries - 1:
                time.sleep(10 + attempt * 5)  # Nghỉ lâu hơn nếu bị lỗi
                continue
            return f"\n[Lỗi Phần {batch_index}: {e}]\n"


# --- Hàm chính xử lý song song ---
def process_vision_with_ai(images, user_prompt):
    # Cấu hình: 2 ảnh/lô và chạy tối đa 4 luồng song song
    batch_size = 2
    max_workers = 4

    batches = [images[i : i + batch_size] for i in range(0, len(images), batch_size)]
    total_batches = len(batches)

    # Dùng ThreadPoolExecutor để chạy song song
    results_map = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Gửi tất cả các phần đi xử lý
        future_to_batch = {
            executor.submit(
                process_single_batch, batches[i], i + 1, total_batches, user_prompt
            ): i
            for i in range(total_batches)
        }

        # Thu thập kết quả khi các luồng hoàn thành
        for future in concurrent.futures.as_completed(future_to_batch):
            batch_idx = future_to_batch[future]
            try:
                results_map[batch_idx] = future.result()
            except Exception:
                results_map[batch_idx] = (
                    f"\n[Lỗi nghiêm trọng ở phần {batch_idx + 1}]\n"
                )

    # Ghép kết quả theo đúng thứ tự từ đầu đến cuối
    full_result = ""
    for i in range(total_batches):
        full_result += results_map[i] + "\n\n"

    return full_result


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


def is_service_unavailable_error(error):
    """Detect Google 503-like errors without requiring google.api_core at import time."""
    error_name = error.__class__.__name__
    message = str(error).lower()
    return error_name == "ServiceUnavailable" or (
        "503" in message and ("unavailable" in message or "overload" in message)
    )


# ==========================================
# 5. HÀM GHI FILE WORD (THUẬT TOÁN BẢNG TÀNG HÌNH CHIA ĐỀU)
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

        # --- TẠO BẢNG TÀNG HÌNH ĐỂ ÉP CỘT TRẮC NGHIỆM A, B, C, D ĐỀU NHAU ---
        elif (
            "**A.**" in line
            and "**B.**" in line
            and "**C.**" in line
            and "**D.**" in line
        ):
            current_table = None

            # 1. Tìm vị trí của các đáp án
            idx_a = line.find("**A.**")
            idx_b = line.find("**B.**")
            idx_c = line.find("**C.**")
            idx_d = line.find("**D.**")

            # 2. Xử lý phần "Question" nếu AI lỡ viết dính liền trên cùng 1 dòng
            question_part = line[:idx_a].strip()
            if question_part:
                p_question = doc.add_paragraph()
                q_parts = re.split(r"\*\*(.*?)\*\*", question_part)
                for j, q_part in enumerate(q_parts):
                    run = p_question.add_run(q_part)
                    run.font.name = "Times New Roman"
                    run.font.size = Pt(12)
                    if j % 2 != 0:
                        run.bold = True

            # 3. Chia 4 đáp án
            parts_text = [
                line[idx_a:idx_b].strip(),
                line[idx_b:idx_c].strip(),
                line[idx_c:idx_d].strip(),
                line[idx_d:].strip(),
            ]

            # 4. Tạo bảng 1 hàng 4 cột (CHIA ĐỀU KÍCH THƯỚC)
            mc_table = doc.add_table(rows=1, cols=4)
            mc_table.autofit = False

            # Ép 4 cột rộng bằng nhau tăm tắp (1.6 inches mỗi cột)
            widths = [Inches(1.6), Inches(1.6), Inches(1.6), Inches(1.6)]
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
# 6. HÀM AI: TỰ ĐỘNG GIẢI ĐỀ & TRÍCH XUẤT JSON
# ==========================================
def extract_quiz_to_json(text):
    # Dùng 1.5-flash để tốc độ nhanh và chịu tải text dài tốt hơn
    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.1)

    prompt = f"""
    Đọc tài liệu sau và tìm TẤT CẢ các câu hỏi trắc nghiệm. 
    Nhiệm vụ của bạn là trích xuất dữ liệu theo CÁC QUY TẮC TUYỆT ĐỐI SAU:

    1. CÂU HỎI: 
       - NẾU LÀ CÂU HỘI THOẠI / ĐỌC HIỂU: Hãy tóm tắt lại hoặc gộp chúng thành 1 CÂU DUY NHẤT. 
       - NẾU LÀ BÀI ĐIỀN TỪ: Chỉ trích xuất đúng 1 câu văn chứa chỗ trống.
       - TUYỆT ĐỐI KHÔNG SỬ DỤNG KÝ TỰ XUỐNG DÒNG. Toàn bộ câu hỏi phải nằm trên 1 dòng thẳng tắp.
    2. ĐÁP ÁN: Trích xuất đúng 4 đáp án (XÓA BỎ các ký tự A., B., C., D. ở đầu).
    3. ĐÓNG VAI GIÁO VIÊN: Tự động giải đề để tìm ra đáp án đúng.
    
    TRẢ VỀ ĐÚNG ĐỊNH DẠNG JSON SAU (Không chứa text nào khác):
    [
        {{
            "question": "Nội dung câu hỏi (Tuyệt đối không có dấu xuống dòng)?",
            "answers": ["Đáp án 1", "Đáp án 2", "Đáp án 3", "Đáp án 4"],
            "correct_index": 1, 
            "correct_text": "COPY CHÍNH XÁC 100% text từ 1 trong 4 đáp án trên"
        }}
    ]
    
    TÀI LIỆU GỐC:
    {text}
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.invoke(prompt).content
            clean_json = response.replace("```json", "").replace("```", "").strip()

            # Cố gắng dịch cục text thành JSON
            return json.loads(clean_json)

        except Exception as e:
            error_msg = str(e)

            # Nếu gặp lỗi Google quá tải, đi ngủ 15s rồi thử lại
            if "503" in error_msg or "429" in error_msg:
                if attempt < max_retries - 1:
                    time.sleep(15)
                    continue

            # NẾU LỖI LÀ DO AI VIẾT SAI FORMAT JSON HOẶC LỖI KHÁC BẤT NGỜ
            import streamlit as st

            st.error(f"❌ Lỗi trích xuất dữ liệu ở lần thử {attempt + 1}: {error_msg}")

            # Phơi bày nguyên văn những gì AI đã viết để bạn soi xem nó ngo nguậy chỗ nào
            if "response" in locals():
                with st.expander(
                    "👀 Bấm vào đây để xem AI đã viết rác gì khiến hệ thống lỗi"
                ):
                    st.text(response)

            return None

    return None


# ==========================================
# 7. HÀM PYTHON: TẠO FILE CHO KAHOOT & BLOOKET (SIÊU TỐC)
# ==========================================
def generate_edtech_files(quiz_json):
    kahoot_data = []

    blooket_io = io.StringIO()
    blooket_io.write("Blooket Dummy Title,,,,,,,\n")
    fieldnames = [
        "Question #",
        "Question Text",
        "Answer 1",
        "Answer 2",
        "Answer 3",
        "Answer 4",
        "Time Limit (sec)",
        "Correct Answer(s)",
    ]
    writer = csv.DictWriter(blooket_io, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    # CHỈ DÙNG 1 VÒNG LẶP DUY NHẤT CHO CẢ 2 NỀN TẢNG
    for i, q in enumerate(quiz_json):
        ans_idx = q["correct_index"]
        ans_idx = 1 if ans_idx == 0 else (4 if ans_idx > 4 else ans_idx)

        # Dọn rác văn bản (Chỉ làm 1 lần)
        clean_q = str(q["question"]).replace("\n", " ").replace("\r", " ").strip()
        clean_a1 = str(q["answers"][0]).replace("\n", " ").strip()
        clean_a2 = str(q["answers"][1]).replace("\n", " ").strip()
        clean_a3 = str(q["answers"][2]).replace("\n", " ").strip()
        clean_a4 = str(q["answers"][3]).replace("\n", " ").strip()

        # 1. Đút dữ liệu vào mảng Kahoot
        kahoot_data.append(
            {
                "Question - max 120 characters": clean_q[:120],
                "Answer 1 - max 75 characters": clean_a1[:75],
                "Answer 2 - max 75 characters": clean_a2[:75],
                "Answer 3 - max 75 characters": clean_a3[:75],
                "Answer 4 - max 75 characters": clean_a4[:75],
                "Time limit (sec) - 5, 10, 20, 30, 60, 90, 120, or 240": 20,
                "Correct answer(s) - 1, 2, 3, or 4": ans_idx,
            }
        )

        # 2. Viết trực tiếp dữ liệu vào Blooket CSV
        writer.writerow(
            {
                "Question #": i + 1,
                "Question Text": clean_q,
                "Answer 1": clean_a1,
                "Answer 2": clean_a2,
                "Answer 3": clean_a3,
                "Answer 4": clean_a4,
                "Time Limit (sec)": 20,
                "Correct Answer(s)": ans_idx,
            }
        )

    # Đóng gói Excel cho Kahoot
    df_kahoot = pd.DataFrame(kahoot_data)
    kahoot_io = io.BytesIO()
    df_kahoot.to_excel(kahoot_io, index=False, engine="openpyxl")
    kahoot_io.seek(0)

    return kahoot_io, blooket_io.getvalue().encode("utf-8")


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

    # YÊU CẦU MẶC ĐỊNH (Người dùng có thể xóa đi gõ lại trên Web)
    default_user_prompt = """Biên tập tài liệu này theo đúng chuẩn form đề thi:
1. BẢNG TỪ VỰNG: CHỈ GIỮ LẠI ĐÚNG 2 CỘT là "Word" và "Meaning". ĐẶC BIỆT: Hãy XÓA SẠCH nội dung trong cột "Meaning" (để trống ô đó) để tạo bài tập điền từ. Lược bỏ tất cả các cột thừa (Synonym, Antonym...).
2. CÂU HỎI TRẮC NGHIỆM: Bôi đậm chữ Question, bôi đậm A, B, C, D và dàn đều trên 1 dòng."""

    user_prompt = st.text_area(
        "2. Yêu cầu xử lý:", value=default_user_prompt, height=250
    )
    process_btn = st.button(
        "🚀 Bắt đầu tạo Bản Nháp", type="primary", use_container_width=True
    )

if process_btn:
    if not uploaded_pdf:
        st.sidebar.error("Bạn chưa tải file PDF lên!")
    else:
        with st.status("Đang phân tích tài liệu...", expanded=True) as status:
            try:  # BẮT ĐẦU MẶC ÁO GIÁP
                st.write("Đang quét nội dung...")
                raw_text = extract_text_from_upload(uploaded_pdf)

                if not raw_text.strip():
                    st.write("Phát hiện PDF ảnh scan! Chuyển sang Mắt thần Vision...")
                    images = extract_images_from_upload(uploaded_pdf)

                    # BẪY UX: Cảnh báo nếu file quá dài (Tránh lỗi 503)
                    if len(images) > 6:
                        st.warning(
                            f"⚠️ Tài liệu này có {len(images)} trang ảnh. Gửi file quá lớn có thể khiến AI Google từ chối phục vụ (Lỗi 503). Khuyên dùng file dưới 6 trang."
                        )

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

            except Exception as e:
                if is_service_unavailable_error(e):
                    status.update(label="Lỗi máy chủ AI", state="error", expanded=False)
                    st.error(
                        "🤖 Máy chủ Google Gemini hiện đang quá tải (Lỗi 503) hoặc file của bạn quá nặng. Vui lòng cắt nhỏ file PDF ra hoặc chờ 1 phút rồi thử lại nhé!"
                    )
                else:
                    status.update(label="Lỗi hệ thống", state="error", expanded=False)
                    st.error(f"❌ Có lỗi xảy ra trong quá trình xử lý: {e}")
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

        # --- CẬP NHẬT GIAO DIỆN XUẤT FILE GAME ---
        st.divider()
        st.markdown("### 🎮 Xuất file Game (Kahoot/Blooket)")

        # Khởi tạo bộ nhớ tạm để giữ file không bị mất khi load lại trang
        if "game_files" not in st.session_state:
            st.session_state.game_files = None

        if st.button("🎲 Tự động Giải đề & Trích xuất File Game", type="secondary"):
            with st.spinner(
                "🤖 AI đang làm bài để tìm đáp án đúng và phân loại dữ liệu..."
            ):
                quiz_data = extract_quiz_to_json(st.session_state.draft_text)

                if quiz_data:
                    # Tạo file cực nhanh với hàm đã tối ưu
                    kahoot_file, blooket_file = generate_edtech_files(quiz_data)
                    # LƯU VÀO BỘ NHỚ
                    st.session_state.game_files = (kahoot_file, blooket_file)
                    st.success(
                        "Đã trích xuất thành công! Bạn có thể tải file bất cứ lúc nào bên dưới:"
                    )
                else:
                    st.error(
                        "❌ Không tìm thấy câu hỏi trắc nghiệm hoặc có lỗi xảy ra."
                    )

        # Hiển thị nút tải xuống MÀ KHÔNG BỊ PHỤ THUỘC VÀO NÚT BẤM BÊN TRÊN
        if st.session_state.game_files:
            k_file, b_file = st.session_state.game_files

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="🟣 Tải file Excel cho KAHOOT!",
                    data=k_file,
                    file_name="Kahoot_Template.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            with col2:
                st.download_button(
                    label="🟦 Tải file CSV cho BLOOKET",
                    data=b_file,
                    file_name="Blooket_Template.csv",
                    mime="text/csv",
                    use_container_width=True,
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
