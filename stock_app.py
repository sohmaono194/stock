import streamlit as st
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# APIキーを環境変数から読み込む
load_dotenv()
API_KEY = os.getenv("EDINET_API_KEY")
API_ENDPOINT = "https://disclosure.edinet-fsa.go.jp/api/v2"

# docID検索関数
def search_docid_by_company(company_name, days_back=60):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    today = datetime.today()

    for _ in range(days_back):
        today -= timedelta(days=1)
        if today.weekday() >= 5:
            continue  # 土日をスキップ

        url = f"{API_ENDPOINT}/documents.json"
        params = {"date": today.strftime("%Y-%m-%d"), "type": 2}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            for item in res.json().get("results", []):
                name = item.get("filerName", "")
                desc = item.get("docDescription", "")
                doc_id = item.get("docID", "")
                csv_flag = item.get("csvFlag", "0")
                if company_name in name and any(x in desc for x in ["四半期報告書", "有価証券報告書", "半期報告書"]):
                    return doc_id, name, desc, csv_flag
        except Exception:
            continue
    return None, None, None, "0"

# Streamlit UI
st.title("📄 EDINET書類検索アプリ")
company = st.text_input("企業名を入力（例：トヨタ自動車株式会社）")

if st.button("docIDを検索"):
    if not API_KEY:
        st.error("APIキーが設定されていません。`.env` を確認してください。")
    elif not company:
        st.warning("企業名を入力してください。")
    else:
        with st.spinner("EDINETで検索中..."):
            doc_id, name, desc, csv_flag = search_docid_by_company(company)
            if doc_id:
                st.success(f"✅ {name} の {desc} が見つかりました")
                st.code(f"docID: {doc_id}｜CSV対応: {csv_flag}")
            else:
                st.error("該当する書類が見つかりませんでした。")
