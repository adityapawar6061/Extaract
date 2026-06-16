import streamlit as st
import pandas as pd
import tempfile
import os
import re
import requests
from io import StringIO

try:
    API_KEY = st.secrets["docstrange"]["api_key"]
except:
    API_KEY = "76a50770-6832-4756-b160-20d8f5dade76"

API_URL = "https://extraction-api.nanonets.com/api/v1/extract/sync"

st.title("Image to CSV Table Extractor")
st.write(f"Using key: ...{API_KEY[-6:]}")

uploaded_files = st.file_uploader(
    "Upload images or PDFs",
    type=['png', 'jpg', 'jpeg', 'pdf'],
    accept_multiple_files=True
)

def extract_tables_from_markdown(markdown_text):
    """Parse markdown tables into DataFrames"""
    tables = []
    lines = markdown_text.strip().split('\n')
    table_lines = []

    for line in lines:
        if '|' in line:
            table_lines.append(line)
        else:
            if table_lines:
                tables.append(table_lines)
                table_lines = []
    if table_lines:
        tables.append(table_lines)

    dfs = []
    for table in tables:
        rows = []
        for line in table:
            if re.match(r'^\s*\|[-| :]+\|\s*$', line):
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            rows.append(cells)
        if rows:
            dfs.append(pd.DataFrame(rows))

    return dfs

if uploaded_files:
    all_dfs = []

    for uploaded_file in uploaded_files:
        st.subheader(f"📄 {uploaded_file.name}")
        ext = uploaded_file.name.split('.')[-1].lower()

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        try:
            with st.spinner(f"Extracting from {uploaded_file.name}..."):
                with open(tmp_path, "rb") as f:
                    response = requests.post(
                        API_URL,
                        headers={"Authorization": f"Bearer {API_KEY}"},
                        files={"file": (uploaded_file.name, f)},
                        data={"output_format": "markdown"}
                    )

            if response.status_code != 200:
                st.error(f"API Error {response.status_code}: {response.text}")
                continue

            result = response.json()
            markdown_content = result.get("result", {}).get("markdown", {}).get("content", "")

            if not markdown_content:
                st.warning(f"No content extracted from {uploaded_file.name}")
                st.write("Raw response:", result)
                continue

            st.text_area("Raw Markdown", markdown_content, height=150)

            dfs = extract_tables_from_markdown(markdown_content)

            if not dfs:
                # No tables found, convert all text lines to dataframe
                lines = [l.strip() for l in markdown_content.split('\n') if l.strip()]
                rows = [re.split(r'\s{2,}|\t', l) for l in lines]
                dfs = [pd.DataFrame(rows)]

            for idx, df in enumerate(dfs):
                df.dropna(how='all', inplace=True)
                df.reset_index(drop=True, inplace=True)
                st.write(f"Table {idx+1}:")
                st.dataframe(df)
                all_dfs.append(df)

                st.download_button(
                    label=f"⬇ Download Table {idx+1} from {uploaded_file.name}",
                    data=df.to_csv(index=False, header=False),
                    file_name=f"{uploaded_file.name.rsplit('.', 1)[0]}_table{idx+1}.csv",
                    mime="text/csv",
                    key=f"dl_{uploaded_file.name}_{idx}"
                )

        except Exception as e:
            st.error(f"Error: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    if len(all_dfs) > 1:
        st.subheader("📦 Combined CSV")
        combined = pd.concat(all_dfs, ignore_index=True)
        st.dataframe(combined)
        st.download_button(
            label="⬇ Download Combined CSV",
            data=combined.to_csv(index=False, header=False),
            file_name="combined_output.csv",
            mime="text/csv",
            key="dl_combined"
        )
