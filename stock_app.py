import streamlit as st
import os
import requests
import zipfile
import io
import pandas as pd
import chardet
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ.get("EDINET_API_KEY")

st.title("📊 企業名からEDINET財務データを自動取得・可視化")

if not API_KEY:
    st.error("APIキーが設定されていません。`.env` ファイルを確認してください。")
    st.stop()

# ----------------------------
# 🔍 docID検索（四半期報告書優先）
# ----------------------------
def find_docid(company_name, days=180):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    date = datetime.today()
    for _ in range(days):
        date -= timedelta(days=1)
        if date.weekday() >= 5:
            continue
        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {"date": date.strftime("%Y-%m-%d"), "type": 2}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            for item in res.json().get("results", []):
                if "四半期報告書" in item.get("docDescription", "") and company_name in item.get("filerName", ""):
                    return item["docID"], item["docDescription"]
        except Exception:
            continue
    return None, None

# ----------------------------
# 📥 ZIP取得と解凍 → CSV or XBRL処理
# ----------------------------
def extract_from_zip(doc_id):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    url_csv = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}?type=5"
    url_xbrl = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}?type=1"

    # CSV
    try:
        res = requests.get(url_csv, headers=headers, timeout=15)
        if "zip" in res.headers.get("Content-Type", ""):
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                for file in z.namelist():
                    if file.endswith(".csv"):
                        raw = z.read(file)
                        encoding = chardet.detect(raw)["encoding"]
                        df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
                        return parse_csv(df), "CSV"
    except Exception:
        pass

    # XBRL fallback
    try:
        res = requests.get(url_xbrl, headers=headers, timeout=20)
        if "zip" in res.headers.get("Content-Type", ""):
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                for file in z.namelist():
                    if "PublicDoc" in file and file.endswith(".xbrl"):
                        xml = z.read(file)
                        return parse_xbrl(xml), "XBRL"
    except Exception as e:
        st.warning(f"XBRL取得失敗: {e}")

    return None, "取得失敗"

# ----------------------------
# 📑 CSV解析
# ----------------------------
def parse_csv(df):
    if not set(["項目ID", "金額"]).issubset(df.columns):
        return {"エラー": "CSV列が足りません"}
    keys = ["NetSales", "OperatingIncome", "OrdinaryIncome", "NetIncome"]
    out = {}
    for k in keys:
        matches = df[df["項目ID"].astype(str).str.contains(k, na=False)]
        if not matches.empty:
            out[k] = matches.iloc[0]["金額"]
    return out

# ----------------------------
# 📑 XBRL解析
# ----------------------------
def parse_xbrl(xml):
    soup = BeautifulSoup(xml, "xml")
    tag_map = {
        "NetSales": ["NetSales", "NetSalesConsolidated"],
        "OperatingIncome": ["OperatingIncome"],
        "OrdinaryIncome": ["OrdinaryIncome"],
        "NetIncome": ["NetIncome", "Profit"]
    }
    result = {}
    for label, tags in tag_map.items():
        for tag in tags:
            found = soup.find(tag)
            if found and found.text.strip().isdigit():
                result[label] = found.text.strip()
                break
        if label not in result:
            result[label] = "N/A"
    return result

# ----------------------------
# 📊 グラフ描画
# ----------------------------
def plot_metrics(metrics):
    df = pd.DataFrame(metrics.items(), columns=["指標", "金額"])
    df["金額"] = pd.to_numeric(df["金額"], errors="coerce")
    sns.barplot(x="指標", y="金額", data=df)
    st.pyplot(plt.gcf())
    plt.clf()

# ----------------------------
# Streamlit UI
# ----------------------------
st.header("🔍 企業名を入力")
company = st.text_input("例: トヨタ自動車株式会社")

if st.button("検索"):
    if not company:
        st.warning("企業名を入力してください。")
    else:
        with st.spinner("docIDを検索中..."):
            doc_id, desc = find_docid(company)
            if not doc_id:
                st.error("四半期報告書が見つかりませんでした。")
            else:
                st.success(f"✅ {desc}｜docID: {doc_id}")
                with st.spinner("ZIPファイル取得・解凍中..."):
                    data, src = extract_from_zip(doc_id)
                    if data:
                        st.subheader(f"📈 {src}から抽出された財務データ")
                        st.dataframe(pd.DataFrame(data.items(), columns=["指標", "金額"]))
                        plot_metrics(data)
                    else:
                        st.error("財務データの抽出に失敗しました。")
