import streamlit as st
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
import pandas as pd
import chardet
import os
from datetime import datetime, timedelta

# --- APIキーの読み込み ---
API_KEY = os.environ.get("EDINET_API_KEY")

st.title("📄 EDINET提出書類からXBRL・CSVを抽出・可視化するアプリ")

# ============================
# ✅ CSVファイルをAPIから取得
# ============================

def fetch_csv_from_docid(doc_id):
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    params = {"type": 5}  # CSVファイル要求
    res = requests.get(url, headers=headers, params=params, timeout=20)

    if "zip" not in res.headers.get("Content-Type", ""):
        raise ValueError("このdocIDにはCSVファイルが存在しません（ZIP形式で提供されていない可能性があります）")

    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        for file_name in z.namelist():
            if file_name.endswith(".csv"):
                with z.open(file_name) as f:
                    raw = f.read()
                    encoding = chardet.detect(raw)["encoding"]
                    return pd.read_csv(io.BytesIO(raw), encoding=encoding), file_name
    raise FileNotFoundError("ZIP内にCSVファイルが見つかりませんでした。")

# ============================
# ✅ CSVファイル取得可能なdocID一覧を取得
# ============================

def fetch_csv_doc_ids(limit=20):
    results = []
    checked = 0
    date = datetime.today()

    while len(results) < limit and checked < 90:
        date -= timedelta(days=1)
        if date.weekday() >= 5:
            continue

        url = "https://disclosure.edinet-fsa.go.jp/api/v1/documents.json"
        params = {"date": date.strftime('%Y-%m-%d'), "type": 2}

        try:
            res = requests.get(url, params=params, timeout=10, verify=False)
            docs = res.json().get("results", [])
            for doc in docs:
                if doc.get("csvFlag") == "1":
                    results.append({
                        "date": date.strftime('%Y-%m-%d'),
                        "docID": doc.get("docID"),
                        "filerName": doc.get("filerName"),
                        "docDescription": doc.get("docDescription")
                    })
                    if len(results) >= limit:
                        break
        except Exception as e:
            st.warning(f"{date.strftime('%Y-%m-%d')} の取得失敗: {e}")
        checked += 1
    return results

# ============================
# Streamlit UI - CSV関連機能
# ============================

st.header("📄 EDINET CSVファイル取得（type=5）")
if st.button("📥 CSV取得可能なdocIDを表示"):
    with st.spinner("CSV対応書類を検索中..."):
        docs = fetch_csv_doc_ids(limit=20)
        if docs:
            for d in docs:
                st.write(f"{d['date']}｜{d['filerName']}｜{d['docDescription']}｜docID: {d['docID']}")
        else:
            st.warning("取得できるdocIDが見つかりませんでした。")

csv_doc_id = st.text_input("📥 CSV取得用のdocIDを入力してください：")
if st.button("CSVを取得して表示"):
    if not csv_doc_id:
        st.warning("docIDを入力してください")
    else:
        with st.spinner("CSVデータを取得中..."):
            try:
                df, fname = fetch_csv_from_docid(csv_doc_id)
                st.success(f"✅ CSV取得成功: {fname}")
                st.dataframe(df.head(30))
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
