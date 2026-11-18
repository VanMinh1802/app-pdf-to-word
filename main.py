import os
import runpy

# File điều hướng chính cho Streamlit Cloud
# Nếu Streamlit Cloud chọn main.py làm Main file path, nó sẽ chuyển tiếp chạy app.py
current_dir = os.path.dirname(os.path.abspath(__file__))
app_path = os.path.join(current_dir, "app.py")

if __name__ == "__main__" or "streamlit" in globals() or os.getenv("STREAMLIT_SERVER_PORT"):
    runpy.run_path(app_path, run_name="__main__")
