import streamlit as st
import datetime
import os
import json
import urllib.parse
import urllib.request
from typing import List, Dict, Union
from dotenv import load_dotenv
import zipfile
import io
import pandas as pd
import chardet

# --- 環境変数ロード ---
load_dotenv()
EDINET_API_KEY = os.environ.get('EDINET_API_KEY')

if not EDINET_API_KEY:
    st.error("`.env` に `EDINET_API_KEY` が設定されていません。")
    st.stop()

# --- ヘルパー関数 ---
def sanitize_filename(name: str) -> str:
    return ''.join(c if c.isalnum() else '_' for c in name)

def disclosure_documents(date: Union[str, datetime.date], type: int = 2) -> Dict:
    if isinstance(date, datetime.date):
        date_str = date.strftime('%Y-%m-%d')
    elif isinstance(date, str):
        date_str = date
    else:
        raise TypeError("Date must be string (YYYY-MM-DD) or datetime.date")

    url = "https://disclosure.edinet-fsa.go.jp/api/v2/documents.json"
    params = {
        "date": date_str,
        "type": type,
        "Subscription-Key": EDINET_API_KEY
    }
    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"

    with urllib.request.urlopen(full_url) as response:
        return json.loads(response.read().decode('utf-8'))

def get_document(doc_id: str) -> bytes:
    url = f'https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}'
    params = {
        "type": 5,  # CSV zip
        "Subscription-Key": EDINET_API_KEY
    }
    query_string = urllib.parse.urlencode(params)
    full_url = f'{url}?{query_string}'
    with urllib.request.urlopen(full_url) as response:
        return response.read()

def extract_csv_from_zip(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for file_name in z.namelist():
            if file_name.endswith('.csv'):
                with z.open(file_name) as f:
                    raw = f.read()
                    encoding = chardet.detect(raw)['encoding']
                    return pd.read_csv(io.BytesIO(raw), encoding=encoding)
    return pd.DataFrame()

def extract_financial_metrics(df: pd.DataFrame) -> Dict[str, Union[str, float]]:
    if not set(["項目ID", "金額"]).issubset(df.columns):
        return {"エラー": "CSVフォーマットが不明です（項目IDや金額列が存在しません）"}

    keywords = {
        "NetSales": "売上高",
        "OperatingIncome": "営業利益",
        "OrdinaryIncome": "経常利益",
        "NetIncome": "当期純利益"
    }
    extracted = {}
    for kw, label in keywords.items():
        matches = df[df["項目ID"].astype(str).str.contains(kw, na=False)]
        if not matches.empty:
            val = matches.iloc[0].get("金額", "")
            extracted[label] = val
    return extracted

# --- Streamlit UI ---
st.title("\ud83d\udcc4 EDINET 開示書類 検索＆財務指標の可視化")

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("開始日", datetime.date.today() - datetime.timedelta(days=7))
with col2:
    end_date = st.date_input("終了日", datetime.date.today())

edinet_codes_input = st.text_input("EDINETコード（カンマ区切りで複数指定可、例：E03614,E03615）")
doc_type_codes_input = st.text_input("書類種別コード（例：120,160）")

if st.button("\ud83d\udd0d 検索実行"):
    if start_date > end_date:
        st.error("開始日は終了日より前にしてください")
        st.stop()

    codes = [c.strip() for c in edinet_codes_input.split(",") if c.strip()]
    doc_types = [d.strip() for d in doc_type_codes_input.split(",") if d.strip()]
    results = []

    with st.spinner("EDINETからデータ取得中..."):
        current_date = start_date
        while current_date <= end_date:
            try:
                docs_res = disclosure_documents(date=current_date)
                for doc in docs_res.get("results", []):
                    if (not codes or doc['edinetCode'] in codes) and (not doc_types or doc['docTypeCode'] in doc_types):
                        results.append(doc)
            except Exception as e:
                st.warning(f"{current_date} のデータ取得に失敗しました: {e}")
            current_date += datetime.timedelta(days=1)

    if not results:
        st.warning("該当する書類は見つかりませんでした。")
    else:
        st.success(f"{len(results)} 件の書類が見つかりました。")
        for doc in results:
            doc_id = doc['docID']
            filer = sanitize_filename(doc.get("filerName", "Unknown"))
            submit_date = doc.get("submitDateTime", "")
            st.markdown(f"### ✍ {doc.get('filerName')} ({submit_date})")
            try:
                zip_bytes = get_document(doc_id)
                df = extract_csv_from_zip(zip_bytes)
                if df.empty:
                    st.warning("CSVデータが読み込めませんでした")
                    continue
                metrics = extract_financial_metrics(df)
                if "エラー" in metrics:
                    st.error(metrics["エラー"])
                else:
                    st.write("#### 抽出された財務指標：")
                    st.dataframe(pd.DataFrame(metrics.items(), columns=["指標", "金額"]))
                # ダウンロード
                st.download_button(
                    label="⬇ ZIPをダウンロード",
                    data=zip_bytes,
                    file_name=f"{doc_id}_{filer}.zip",
                    mime="application/zip"
                )
            except Exception as e:
                st.error(f"処理中にエラーが発生しました: {e}")
