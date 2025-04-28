import streamlit as st
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# .envからAPIキー読み込み
load_dotenv()
API_KEY = os.getenv("EDINET_API_KEY")

st.title("📄 企業名からEDINET docIDを自動取得")

# 企業名を入力
company_name = st.text_input("企業名を入力してください（例: トヨタ）")

def get_docid_by_company_name(company_name):
    results = []
    headers = {
        "Ocp-Apim-Subscription-Key": API_KEY
    }

    # 今日の日付から180日分を確認
    date = datetime.today()
    for i in range(180):
        date -= timedelta(days=1)
        if date.weekday() >= 5:
            continue  # 土日スキップ
        date_str = date.strftime("%Y-%m-%d")
        url = f"https://api.edinet-fsa.go.jp/api/v2/documents.json?date={date_str}"
        
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if "application/json" in res.headers.get("Content-Type", ""):
                day_docs = res.json().get("results", [])
                for doc in day_docs:
                    if company_name in doc.get("filerName", ""):
                        doc["date"] = date_str
                        results.append(doc)
        except Exception as e:
            st.warning(f"エラー発生：{e}")

    return results

if st.button("企業名からdocIDを取得"):
    if not company_name:
        st.warning("企業名を入力してください！")
    else:
        with st.spinner("docIDを取得中..."):
            docs = get_docid_by_company_name(company_name)
            if docs:
                st.success(f"{len(docs)} 件のdocIDが見つかりました！")
                for doc in docs[:100]:
                    st.write(f"📅 {doc['date']}｜{doc['docDescription']}｜docID: {doc['docID']}")
            else:
                st.warning("該当するdocIDが見つかりませんでした。")
