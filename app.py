import streamlit as st
import pandas as pd
import tempfile
import os
import re
from io import StringIO
from docstrange import DocumentExtractor

try:
    API_KEY = st.secrets["docstrange"]["api_key"]
except:
    API_KEY = "76a50770-6832-4756-b160-20d8f5dade76"
os.environ['DOCSTRANGE_API_KEY'] = API_KEY

st.title("Image to CSV Table Extractor")
st.write(f"Using key: ...{API_KEY[-6:]}")  # shows last 6 chars only

uploaded_files = st.file_uploader(
    "Upload images or PDFs",
    type=['png', 'jpg', 'jpeg', 'pdf'],
    accept_multiple_files=True
)

if uploaded_files:
    all_dfs = []

    for uploaded_file in uploaded_files:
        st.subheader(f"📄 {uploaded_file.name}")
        ext = uploaded_file.name.split('.')[-1]

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        try:
            extractor = DocumentExtractor(api_key=API_KEY)

            with st.spinner(f"Extracting from {uploaded_file.name}..."):
                result = extractor.extract(tmp_path)

            # Try CSV first, fallback to text
            csv_content = None
            try:
                csv_content = result.extract_csv()
            except Exception:
                try:
                    text = result.extract_text()
                    if text and text.strip():
                        lines = [
                            ','.join(re.split(r'\s{2,}|\t', line.strip()))
                            for line in text.strip().split('\n') if line.strip()
                        ]
                        csv_content = '\n'.join(lines)
                except Exception as e:
                    st.error(f"Extraction failed: {e}")
                    continue

            if not csv_content or not csv_content.strip():
                st.warning(f"No content extracted from {uploaded_file.name}")
                continue

            # Parse into DataFrame
            try:
                df = pd.read_csv(StringIO(csv_content), header=None, sep=None, engine='python')
            except Exception:
                rows = [re.split(r'[,\t|;]', line) for line in csv_content.strip().split('\n')]
                df = pd.DataFrame(rows)

            df.dropna(how='all', inplace=True)
            df.reset_index(drop=True, inplace=True)

            st.dataframe(df)
            all_dfs.append(df)

            st.download_button(
                label=f"⬇ Download {uploaded_file.name} as CSV",
                data=df.to_csv(index=False, header=False),
                file_name=f"{uploaded_file.name.rsplit('.', 1)[0]}.csv",
                mime="text/csv",
                key=f"dl_{uploaded_file.name}"
            )

        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    if len(all_dfs) > 1:
        st.subheader("📦 Combined CSV (all files)")
        combined = pd.concat(all_dfs, ignore_index=True)
        st.dataframe(combined)
        st.download_button(
            label="⬇ Download Combined CSV",
            data=combined.to_csv(index=False, header=False),
            file_name="combined_output.csv",
            mime="text/csv",
            key="dl_combined"
        )
