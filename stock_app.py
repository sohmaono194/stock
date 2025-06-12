import streamlit as st
import requests
import zipfile
import io
import pandas as pd
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# フォント設定（日本語対応）
plt.rcParams['font.family'] = 'MS Gothic'  # Macの場合は 'AppleGothic'

# APIキー取得（.env or 環境変数）
API_KEY = os.getenv("EDINET_API_KEY")
HEADERS = {"Ocp-Apim-Subscription-Key": API_KEY}
EDINET_API = "https://api.edinet-fsa.go.jp/api/v2"

# Streamlitタイトル
st.title("📊 企業名からEDINET報告書データをグラフ化")

# ----------------------------
# 企業名から報告書のdocIDを探す
# ----------------------------
def find_docid(company_name, days_back=365):
    today = datetime.today()
    for _ in range(days_back):
        today -= timedelta(days=1)
        if today.weekday() >= 5:
            continue  # 土日スキップ
        params = {"date": today.strftime("%Y-%m-%d"), "type": 2}
        try:
            res = requests.get(f"{EDINET_API}/documents.json", headers=HEADERS, params=params, timeout=10)
            res.raise_for_status()
            for it in res.json().get("results", []):
                if company_name in it.get("filerName", "") and "報告書" in it.get("docDescription", ""):
                    return it["docID"], it["docDescription"]
        except:
            continue
    return None, None

# ----------------------------
# 財務指標抽出：XBRLから
# ----------------------------
def extract_from_xbrl(xml_data):
    soup = BeautifulSoup(xml_data, "xml")
    tags = {
        "売上高": ["NetSales", "NetSalesConsolidated"],
        "営業利益": ["OperatingIncome", "OperatingIncomeConsolidated"],
        "経常利益": ["OrdinaryIncome", "OrdinaryIncomeConsolidated"],
        "純利益": ["NetIncome", "Profit", "NetIncomeAttributableToOwnersOfParent"]
    }
    result = {}
    for key, options in tags.items():
        for tag in options:
            el = soup.find(tag)
            if el and el.text.strip().isdigit():
                result[key] = int(el.text.strip())
                break
        if key not in result:
            result[key] = None
    return result

# ----------------------------
# docIDからZIPファイルを取得し、XBRLパース
# ----------------------------
def fetch_and_parse(doc_id):
    url = f"{EDINET_API}/documents/{doc_id}"
    try:
        res = requests.get(url, headers=HEADERS, params={"type": 1}, timeout=15)
        res.raise_for_status()
        if "zip" not in res.headers.get("Content-Type", ""):
            raise ValueError("ZIPファイルが取得できませんでした。")

        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            for name in z.namelist():
                if name.endswith(".xbrl") and "PublicDoc" in name:
                    with z.open(name) as f:
                        return extract_from_xbrl(f.read())
    except Exception as e:
        st.error(f"データ取得または解析に失敗しました：{e}")
        return None

# ----------------------------
# グラフ描画（matplotlib）
# ----------------------------
def plot_metrics(metrics):
    df = pd.DataFrame(list(metrics.items()), columns=["指標", "金額"])
    plt.figure(figsize=(6, 4))
    plt.bar(df["指標"], df["金額"])
    plt.ylabel("金額（百万円）")
    plt.title("財務指標")
    st.pyplot(plt)

# ----------------------------
# UI
# ----------------------------
company = st.text_input("企業名を入力（例：トヨタ自動車株式会社）")

if st.button("検索して表示"):
    if not company:
        st.warning("企業名を入力してください。")
    else:
        with st.spinner("docIDを検索中..."):
            doc_id, desc = find_docid(company)
            if not doc_id:
                st.error("該当する報告書が見つかりませんでした。")
            else:
                st.success(f"✅ 見つかりました：{desc}｜docID: {doc_id}")
                metrics = fetch_and_parse(doc_id)
                if metrics:
                    st.subheader("📈 財務指標")
                    st.write(metrics)
                    plot_metrics(metrics)
