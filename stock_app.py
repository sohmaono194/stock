import streamlit as st
import requests
import zipfile
import io
import os
import pandas as pd
import chardet
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 環境変数からAPIキー取得
load_dotenv()
API_KEY = os.getenv("EDINET_API_KEY")
API_BASE = "https://api.edinet-fsa.go.jp/api/v2"

st.title("📊 EDINET財務データ自動取得・可視化")

if not API_KEY:
    st.error("APIキーが設定されていません")
    st.stop()

# -----------------------------------
# docIDを企業名から取得（報告書で検索）
# -----------------------------------
def find_docid(company_name, days=60):
    for i in range(days):
        date = (datetime.today() - timedelta(days=i)).strftime("%Y-%m-%d")
        if datetime.strptime(date, "%Y-%m-%d").weekday() >= 5:
            continue
        try:
            res = requests.get(
                f"{API_BASE}/documents.json",
                params={"date": date, "type": 2},
                headers={"Ocp-Apim-Subscription-Key": API_KEY},
                timeout=10
            )
            for item in res.json().get("results", []):
                if company_name in item.get("filerName", "") and "報告書" in item.get("docDescription", ""):
                    return item["docID"], item["docDescription"]
        except:
            continue
    return None, None

# -----------------------------------
# 財務指標をXBRLから抽出
# -----------------------------------
def extract_metrics_from_xbrl(xml_bytes):
    soup = BeautifulSoup(xml_bytes, "xml")
    tags = {
        "売上高": ["NetSales", "NetSalesConsolidated"],
        "営業利益": ["OperatingIncome"],
        "経常利益": ["OrdinaryIncome"],
        "純利益": ["NetIncome", "Profit"]
    }
    results = {}
    for label, tag_list in tags.items():
        for tag in tag_list:
            value = soup.find(tag)
            if value and value.text.strip().isdigit():
                results[label] = int(value.text.strip())
                break
        if label not in results:
            results[label] = None
    return results

# -----------------------------------
# docIDからZIPを取得・解凍してXBRL or CSVを読み込み
# -----------------------------------
def fetch_and_parse_zip(doc_id):
    res = requests.get(
        f"{API_BASE}/documents/{doc_id}",
        params={"type": 1},
        headers={"Ocp-Apim-Subscription-Key": API_KEY},
        timeout=20
    )
    if "zip" not in res.headers.get("Content-Type", ""):
        raise ValueError("ZIPファイルが取得できませんでした。")
    
    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        for file_name in z.namelist():
            if "PublicDoc" in file_name and file_name.endswith(".xbrl"):
                with z.open(file_name) as f:
                    return extract_metrics_from_xbrl(f.read())
    raise ValueError("XBRLファイルがZIP内に見つかりませんでした。")

# -----------------------------------
# グラフ表示
# -----------------------------------
def plot_metrics(metrics):
    df = pd.DataFrame(metrics.items(), columns=["項目", "金額"]).dropna()
    fig, ax = plt.subplots()
    ax.bar(df["項目"], df["金額"])
    ax.set_ylabel("金額（円）")
    st.pyplot(fig)

# -----------------------------------
# Streamlit UI
# -----------------------------------
company = st.text_input("企業名を入力（例：トヨタ自動車）")

if st.button("財務データ取得"):
    if not company:
        st.warning("企業名を入力してください。")
    else:
        with st.spinner("docIDを検索中..."):
            doc_id, desc = find_docid(company)
            if not doc_id:
                st.error("該当する報告書が見つかりませんでした。")
            else:
                st.success(f"{desc}｜docID: {doc_id}")
                try:
                    data = fetch_and_parse_zip(doc_id)
                    st.subheader("抽出された財務指標")
                    st.write(data)
                    plot_metrics(data)
                except Exception as e:
                    st.error(f"データ取得または解析に失敗しました：{e}")
