# frontend/main.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
from PIL import Image

# Load the image
logo = Image.open("frontend/image.jpg")

# Display the logo
st.image(logo, width=300)  # adjust width as needed

BACKEND_URL = "http://localhost:8008/run_tests"

st.set_page_config(page_title="LessHands", page_icon="🧪", layout="centered")

# ------------------ INPUT SECTION ------------------
st.title("🧪 AI Test Runner")

st.subheader("🔗 Enter Website / Web App URL")
url = st.text_input("Website URL", placeholder="https://example.com")

st.subheader("📝 Provide Test Cases")
test_case_input_type = st.selectbox("Choose input method:", ["Upload File", "Type Text"])

test_cases = None
if test_case_input_type == "Upload File":
    uploaded_file = st.file_uploader("Upload a .txt file with test cases", type="txt")
    if uploaded_file is not None:
        test_cases = uploaded_file.read().decode("utf-8")
elif test_case_input_type == "Type Text":
    test_cases = st.text_area("Enter test cases manually")

# Engine selection
st.subheader("⚙ Choose Code Generation Engine")
engine = st.selectbox("Engine", ["ollama", "openrouter"], index=0)
if engine == "openrouter":
    st.caption("Ensure the backend has OPENROUTER_API_KEY set.")

# RUN TESTS BUTTON
if st.button("🚀 Run Tests"):
    if not url:
        st.error("⚠ Please provide a website URL before proceeding.")
    elif not test_cases:
        st.error("⚠ Please provide test cases (file or text).")
    else:
        with st.spinner("Analyzing test cases and running with Playwright..."):
            try:
                payload = {
                    "url": url,
                    "test_cases_text": test_cases,
                    "engine": engine,
                    "max_test_seconds": 60
                }
                resp = requests.post(BACKEND_URL, json=payload)
                resp.raise_for_status()
                backend_response = resp.json()
                st.session_state.results = backend_response["results"]
                st.success("✅ Tests completed!")
            except Exception as e:
                st.error(f"Backend error: {e}")

# RESULTS SECTION
if "results" in st.session_state:
    results = st.session_state.results
    df = pd.DataFrame(results)

    # Convert execution time to numeric
    df["time_taken_num"] = df["time_taken"].str.replace("s", "").astype(int)

    total = len(df)
    passed = len(df[df["status"] == "Passed"])
    failed = len(df[df["status"] == "Failed"])

    # Summary
    st.subheader("📊 Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Tests", total)
    col2.metric("✅ Passed", passed)
    col3.metric("❌ Failed", failed)

    # Pie Chart (Pass/Fail ratio)
    st.subheader("📈 Pass vs Fail Ratio")
    fig1, ax1 = plt.subplots()
    ax1.pie([passed, failed], labels=["Passed", "Failed"], autopct="%1.1f%%", colors=["green", "red"])
    ax1.set_title("Pass vs Fail")
    st.pyplot(fig1)

    # Bar Chart (Execution Time)
    st.subheader("⏱ Execution Time per Test")
    fig2, ax2 = plt.subplots()
    ax2.bar(df["test_case"], df["time_taken_num"], color=df["status"].map({"Passed": "green", "Failed": "red"}))
    ax2.set_ylabel("Time (s)")
    ax2.set_xlabel("Test Case")
    ax2.set_title("Execution Time per Test Case")
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig2)

    # Detailed Table
    st.subheader("📋 Detailed Test Report")
    st.dataframe(df[["test_case", "status", "time_taken", "error"]])
