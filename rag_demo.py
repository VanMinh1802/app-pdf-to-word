import streamlit as st
from PyPDF2 import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_classic.chains.question_answering import load_qa_chain
from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="RAG CV Chatbot", page_icon="🧠")
st.title("🧠 Chatbot RAG: 'Hỏi cung' CV của bạn")
st.markdown(
    "Hệ thống này không dùng trí nhớ ảo, nó tìm kiếm dữ liệu trực tiếp từ file PDF bạn tải lên bằng Vector Database (FAISS)."
)


# 1. Đọc file PDF
def get_pdf_text(pdf):
    text = ""
    pdf_reader = PdfReader(pdf)
    for page in pdf_reader.pages:
        if page.extract_text():
            text += page.extract_text()
    return text


# 2. Băm nhỏ văn bản (Text Splitter)
def get_text_chunks(text):
    # Cắt text thành các khối 1000 ký tự, phần giao nhau (overlap) là 200 ký tự để không bị đứt đoạn ngữ nghĩa
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_text(text)
    return chunks


# 3. Mã hóa và lưu vào Vector Database (FAISS)
def get_vector_store(text_chunks):
    # Dùng mô hình Embeddings của Google để biến chữ thành ma trận số
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    # Nạp các khối chữ và ma trận số vào FAISS database
    vector_store = FAISS.from_texts(text_chunks, embedding=embeddings)
    return vector_store


# 4. Cấu hình Prompt ép AI chỉ trả lời dựa trên tài liệu
def get_conversational_chain():
    prompt_template = """
    Trích xuất thông tin từ Ngữ cảnh (Context) được cung cấp dưới đây để trả lời câu hỏi.
    Nếu câu trả lời không có trong Ngữ cảnh, hãy nói "Tài liệu này không đề cập đến thông tin bạn hỏi", tuyệt đối KHÔNG ĐƯỢC BỊA RA CÂU TRẢ LỜI.

    Ngữ cảnh (Context):\n {context}?\n
    Câu hỏi:\n {question}\n

    Câu trả lời:
    """
    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)
    prompt = PromptTemplate(
        template=prompt_template, input_variables=["context", "question"]
    )
    chain = load_qa_chain(model, chain_type="stuff", prompt=prompt)
    return chain


# === GIAO DIỆN XỬ LÝ ===
uploaded_file = st.file_uploader("Tải CV PDF của bạn lên đây", type=["pdf"])

if uploaded_file is not None:
    # Chỉ xử lý vector 1 lần khi mới up file
    if "vector_store" not in st.session_state:
        with st.spinner("Đang băm nhỏ dữ liệu và xây dựng Vector Database..."):
            raw_text = get_pdf_text(uploaded_file)
            text_chunks = get_text_chunks(raw_text)
            st.session_state.vector_store = get_vector_store(text_chunks)
            st.success("Đã nạp CV vào Vector Database thành công!")

    user_question = st.text_input(
        "Hỏi bất cứ thông tin chi tiết nào có trong CV (VD: Ứng viên này biết dùng thư viện nào của UI?):"
    )

    if user_question:
        with st.spinner("Đang quét Vector tìm câu trả lời..."):
            # A. Lấy Embeddings để tìm kiếm
            embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

            # B. Tìm trong FAISS những đoạn văn (chunks) giống với câu hỏi nhất
            docs = st.session_state.vector_store.similarity_search(user_question)

            # C. Đưa các đoạn văn tìm được + Câu hỏi cho AI đọc và chắt lọc
            chain = get_conversational_chain()
            response = chain(
                {"input_documents": docs, "question": user_question},
                return_only_outputs=True,
            )

            st.markdown("### 🤖 Trả lời:")
            st.write(response["output_text"])

            # (Tùy chọn) In ra các đoạn văn bản thô mà thuật toán Vector tìm được để bạn hiểu bản chất
            with st.expander(
                "Bấm vào đây để xem hệ thống đã 'lôi' đoạn văn nào từ Database ra để đưa cho AI đọc"
            ):
                for i, doc in enumerate(docs):
                    st.info(f"Đoạn {i + 1}:\n{doc.page_content}")
