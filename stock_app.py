import streamlit as st
import requests
import zipfile
import io
import pandas as pd
import os
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# .envからAPIキー読み込み
load_dotenv()
API_KEY = os.environ.get("EDINET_API_KEY")
if not API_KEY:
    st.error("APIキーが見つかりません。`.env` または環境変数を確認してください。")
    st.stop()

# フォント設定（日本語表示）
plt.rcParams["font.family"] = "MS Gothic"  # Macの場合は "AppleGothic" に変更

st.title("📊 EDINET 財務データ取得アプリ（CSVまたはXBRL + グラフ表示）")

# ----------------------------
# docID 検索
# ----------------------------
def find_docid(company_name, days=180):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    today = datetime.today()

    for _ in range(days):
        today -= timedelta(days=1)
        if today.weekday() >= 5:  # 土日スキップ
            continue
        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {"date": today.strftime("%Y-%m-%d"), "type": 2}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            for item in res.json().get("results", []):
                if company_name in item.get("filerName", "") and "報告書" in item.get("docDescription", ""):
                    return item.get("docID"), item.get("docDescription")
        except Exception:
            continue
    return None, None

# ----------------------------
# ZIP 取得 & 展開
# ----------------------------
def download_and_extract_zip(doc_id, file_type=5):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {"type": file_type}
    res = requests.get(url, headers=headers, params=params)
    if "zip" not in res.headers.get("Content-Type", ""):
        return None
    return zipfile.ZipFile(io.BytesIO(res.content))

# ----------------------------
# 財務データ抽出（CSV）
# ----------------------------
def parse_csv_metrics(df):
    if not set(["項目ID", "金額"]).issubset(df.columns):
        raise ValueError("CSVに必要な列がありません。")
    
    metrics = {}
    key_map = {
        "NetSales": "売上高",
        "OperatingIncome": "営業利益",
        "OrdinaryIncome": "経常利益",
        "NetIncome": "純利益"
    }

    for key, label in key_map.items():
        match = df[df["項目ID"].astype(str).str.contains(key, na=False)]
        if not match.empty:
            try:
                metrics[label] = int(match.iloc[0]["金額"])
            except:
                metrics[label] = match.iloc[0]["金額"]
        else:
            metrics[label] = None

    return metrics

# ----------------------------
# 財務データ抽出（XBRL）
# ----------------------------
def parse_xbrl_metrics(xml_data):
    soup = BeautifulSoup(xml_data, "xml")
    tag_map = {
        "売上高": ["NetSales", "NetSalesConsolidated"],
        "営業利益": ["OperatingIncome"],
        "経常利益": ["OrdinaryIncome"],
        "純利益": ["NetIncome", "Profit"]
    }
    result = {}
    for label, tags in tag_map.items():
        for tag in tags:
            val = soup.find(tag)
            if val and val.text.strip().isdigit():
                result[label] = int(val.text.strip())
                break
        if label not in result:
            result[label] = None
    return result

# ----------------------------
# グラフ描画
# ----------------------------
def plot_metrics(metrics: dict):
    labels = list(metrics.keys())
    values = [v if isinstance(v, (int, float)) else 0 for v in metrics.values()]
    fig, ax = plt.subplots()
    ax.bar(labels, values)
    ax.set_title("財務指標")
    ax.set_ylabel("金額（百万円）")
    st.pyplot(fig)

# ----------------------------
# UI
# ----------------------------
company = st.text_input("企業名を入力（例：トヨタ自動車株式会社）")
if st.button("データ取得と表示"):
    if not company:
        st.warning("企業名を入力してください。")
        st.stop()

    with st.spinner("docIDを検索中..."):
        doc_id, desc = find_docid(company)
        if not doc_id:
            st.error("該当する報告書が見つかりませんでした。")
            st.stop()
        st.success(f"docID: {doc_id}｜{desc}")

    with st.spinner("ZIPファイルを取得中..."):
        z = download_and_extract_zip(doc_id, file_type=5)
        if not z:
            z = download_and_extract_zip(doc_id, file_type=1)
            if not z:
                st.error("ZIPファイルが取得できませんでした。")
                st.stop()
            else:
                for name in z.namelist():
                    if name.endswith(".xbrl"):
                        with z.open(name) as f:
                            xml = f.read()
                            metrics = parse_xbrl_metrics(xml)
                            break
        else:
            for name in z.namelist():
                if name.endswith(".csv"):
                    with z.open(name) as f:
                        df = pd.read_csv(f, encoding="utf-8", low_memory=False)
                        metrics = parse_csv_metrics(df)
                        break

    st.subheader("📊 抽出された財務指標")
    st.dataframe(pd.DataFrame(metrics.items(), columns=["指標", "金額"]))
    plot_metrics(metrics)
