import streamlit as st
import PyPDF2
import re
import time

# Import thêm các class để phân biệt người dùng và AI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="AI Resume Pro", page_icon="🚀", layout="wide")
st.title("🚀 Hệ thống Tối ưu CV Toàn diện")


def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in pdf_reader.pages:
        if page.extract_text():
            text += page.extract_text() + "\n"
    return text


# --- KHỞI TẠO BỘ NHỚ CHO CHATBOT ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "cv_content" not in st.session_state:
    st.session_state.cv_content = ""

uploaded_file = st.file_uploader("Tải CV PDF của bạn", type=["pdf"])
job_role = st.text_input(
    "Vị trí ứng tuyển (VD: Web Developer, Full-stack...)",
    placeholder="Nhập vị trí để AI phân tích sát nhất",
)

if uploaded_file:
    current_cv_text = extract_text_from_pdf(uploaded_file)

    # Logic thông minh: Nếu bạn tải lên một file CV khác, hệ thống sẽ tự động xóa lịch sử chat cũ
    if current_cv_text != st.session_state.cv_content:
        st.session_state.cv_content = current_cv_text
        st.session_state.messages = []

    # CHIA GIAO DIỆN LÀM 3 TAB
    tab1, tab2, tab3 = st.tabs(
        ["📈 Chấm điểm ATS", "🎤 Giả lập Phỏng vấn", "💬 Chatbot Tư vấn CV"]
    )

    # ==========================================
    # TAB 1: CHẤM ĐIỂM ATS
    # ==========================================
    with tab1:
        st.markdown("### 📊 Đánh giá định lượng CV")
        if st.button("Bắt đầu Chấm điểm", type="primary", key="btn_ats"):
            with st.spinner("AI đang 'soi' CV và chấm điểm..."):
                model_ats = ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash", temperature=0.3
                )
                prompt_ats = f"""
                Bạn là một hệ thống ATS thông minh và chuyên gia HR. Phân tích CV cho vị trí: {job_role}.
                YÊU CẦU: Đầu bài đánh giá, cung cấp điểm theo định dạng:
                [OVERALL_SCORE]: (số từ 0-100)
                [SKILL_MATCH]: (số từ 0-100)
                [FORMAT_SCORE]: (số từ 0-100)
                Sau đó nhận xét chi tiết: Tại sao có điểm đó? Thiếu keyword gì? Sửa đổi phần nào?
                CV: {current_cv_text}
                """
                response_ats = model_ats.invoke(prompt_ats).content

                def get_score(tag, text):
                    pattern = rf"\[{tag}\]:\s*(\d+)"
                    match = re.search(pattern, text)
                    return int(match.group(1)) if match else 0

                overall, skill, fmt = (
                    get_score("OVERALL_SCORE", response_ats),
                    get_score("SKILL_MATCH", response_ats),
                    get_score("FORMAT_SCORE", response_ats),
                )

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Điểm Tổng quát", f"{overall}/100")
                    st.progress(overall / 100)
                with col2:
                    st.metric("Độ khớp Kỹ năng", f"{skill}/100")
                    st.progress(skill / 100)
                with col3:
                    st.metric("Điểm Trình bày", f"{fmt}/100")
                    st.progress(fmt / 100)

                st.divider()
                st.markdown(re.sub(r"\[.*?\]: \d+", "", response_ats).strip())

    # ==========================================
    # TAB 2: GIẢ LẬP PHỎNG VẤN
    # ==========================================
    with tab2:
        st.markdown("### 👨‍💻 Đối mặt với Tech Lead")
        if st.button("Tạo bộ câu hỏi Phỏng vấn", type="primary", key="btn_interview"):
            with st.spinner("Tech Lead đang chuẩn bị câu hỏi..."):
                model_interview = ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash", temperature=0.7
                )
                prompt_interview = f"""
                Bạn là Tech Lead phỏng vấn ứng viên cho vị trí: {job_role}.
                Dựa vào CV này: {current_cv_text}. Hãy tạo 5 câu hỏi (3 Chuyên môn, 2 Hành vi) xoáy sâu vào dự án và kỹ năng của họ.
                Dưới mỗi câu hỏi, cho một đoạn "Gợi ý cách trả lời ăn điểm".
                """
                st.markdown(model_interview.invoke(prompt_interview).content)

    # ==========================================
    # TAB 3: CHATBOT TƯ VẤN THỜI GIAN THỰC (TÍNH NĂNG "SÁT THỦ")
    # ==========================================
    with tab3:
        st.markdown("### 💬 Trợ lý AI đồng hành sửa CV")
        st.info(
            "Hãy thử yêu cầu AI viết lại một đoạn kinh nghiệm trong CV, hoặc hỏi xin tư vấn từ khóa cho một công ty cụ thể."
        )

        # Hiển thị các tin nhắn cũ
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Khung nhập liệu Chatbot
        if prompt := st.chat_input(
            "VD: Dựa vào CV của tôi, hãy viết lại dự án số 1..."
        ):
            # In tin nhắn user lên màn hình
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Xử lý luồng tư duy của AI
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""

                # Khởi tạo mô hình
                chat_model = ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash", temperature=0.5
                )

                # Xây dựng bộ nhớ (Truyền CV vào tiềm thức của AI + lịch sử chat)
                langchain_messages = [
                    SystemMessage(
                        content=f"Bạn là chuyên gia Mentor IT. Dưới đây là CV của ứng viên:\n{st.session_state.cv_content}\n"
                        f"Vị trí họ đang hướng tới: {job_role}. Hãy trả lời các câu hỏi để giúp họ tối ưu CV. "
                        f"Nếu họ yêu cầu viết lại, hãy đưa ra kết quả cụ thể, chuyên nghiệp."
                    )
                ]

                for m in st.session_state.messages:
                    if m["role"] == "user":
                        langchain_messages.append(HumanMessage(content=m["content"]))
                    else:
                        langchain_messages.append(AIMessage(content=m["content"]))

                # Kích hoạt chế độ Streaming nhả chữ thời gian thực
                for chunk in chat_model.stream(langchain_messages):
                    full_response += chunk.content
                    message_placeholder.markdown(full_response + "▌")

                # In hoàn chỉnh
                message_placeholder.markdown(full_response)

            # Lưu tin nhắn AI vào bộ nhớ
            st.session_state.messages.append(
                {"role": "assistant", "content": full_response}
            )

else:
    st.warning("Minh ơi, hãy tải file CV lên để bắt đầu sử dụng toàn bộ tính năng nhé!")
