import streamlit as st
import requests
import zipfile
import io
import os
import pandas as pd
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt

# 日本語フォント（Windows）
plt.rcParams['font.family'] = 'MS Gothic'

# APIキー
API_KEY = os.getenv("EDINET_API_KEY")
HEADERS = {"Ocp-Apim-Subscription-Key": API_KEY}
EDINET_API = "https://api.edinet-fsa.go.jp/api/v2"

st.title("📊 EDINET報告書から財務指標を可視化")

# docIDを検索
def find_latest_docid(company_name, days_back=180):
    today = datetime.today()
    target_types = {"120", "140", "160"}  # 有報、四報、半報

    for _ in range(days_back):
        today -= timedelta(days=1)
        if today.weekday() >= 5:
            continue
        try:
            res = requests.get(
                f"{EDINET_API}/documents.json",
                headers=HEADERS,
                params={"date": today.strftime('%Y-%m-%d'), "type": 2},
                timeout=10
            )
            results = res.json().get("results", [])
            for doc in results:
                if (
                    doc.get("filerName", "").strip().startswith(company_name)
                    and doc.get("docTypeCode", "") in target_types
                    and doc.get("csvFlag") == "1"  # 任意：CSVもあるもの
                ):
                    return doc.get("docID"), doc.get("docDescription")
        except:
            continue
    return None, None


# XBRL抽出
def extract_xbrl_metrics(xml_data):
    soup = BeautifulSoup(xml_data, "xml")
    tag_map = {
        "売上高": ["NetSales", "NetSalesConsolidated"],
        "営業利益": ["OperatingIncome", "OperatingIncomeConsolidated"],
        "経常利益": ["OrdinaryIncome", "OrdinaryIncomeConsolidated"],
        "純利益": ["NetIncome", "Profit", "NetIncomeAttributableToOwnersOfParent"]
    }
    result = {}
    for label, tags in tag_map.items():
        for tag in tags:
            el = soup.find(tag)
            if el and el.text.strip().isdigit():
                result[label] = int(el.text.strip())
                break
        if label not in result:
            result[label] = None
    return result

# ZIPからXBRLを解凍＆取得
def fetch_xbrl_from_zip(doc_id):
    res = requests.get(
        f"{EDINET_API}/documents/{doc_id}",
        headers=HEADERS,
        params={"type": 1},
        timeout=15
    )
    if "zip" not in res.headers.get("Content-Type", ""):
        raise ValueError("ZIPファイルが取得できませんでした。")

    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        for name in z.namelist():
            if name.endswith(".xbrl") and "PublicDoc" in name:
                with z.open(name) as f:
                    return extract_xbrl_metrics(f.read())
    raise ValueError("XBRLファイルが見つかりませんでした。")

# グラフ表示
def show_graph(metrics):
    df = pd.DataFrame(list(metrics.items()), columns=["指標", "金額"])
    plt.figure(figsize=(6, 4))
    plt.bar(df["指標"], df["金額"])
    plt.title("財務指標")
    plt.ylabel("金額（百万円）")
    st.pyplot(plt)

# UI
company = st.text_input("企業名を入力してください（例：トヨタ自動車株式会社）")
if st.button("報告書を検索して可視化"):
    if not company:
        st.warning("企業名を入力してください。")
    else:
        with st.spinner("docIDを検索中..."):
            doc_id, desc = find_latest_docid(company)
            if not doc_id:
                st.error("報告書が見つかりませんでした。")
            else:
                st.success(f"✅ 見つかりました：{desc}｜docID: {doc_id}")
                try:
                    metrics = fetch_xbrl_from_zip(doc_id)
                    st.write(metrics)
                    show_graph(metrics)
                except Exception as e:
                    st.error(f"データ取得に失敗しました：{e}")
