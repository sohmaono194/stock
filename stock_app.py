import os
import io
import zipfile
import pandas as pd
import requests
import chardet
import streamlit as st
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# .envからAPIキーを読み込み
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.environ.get("EDINET_API_KEY")

API_URL = "https://api.edinet-fsa.go.jp/api/v2"

st.title("📊 EDINET 四半期報告書ダウンローダー＋財務グラフ化")

if not API_KEY:
    st.error("APIキーが設定されていません")
    st.stop()

# -------------------------
# docID検索（四半期報告書に限定）
# -------------------------
def find_docid(company_name, days_back=120):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    today = datetime.today()

    for i in range(days_back):
        date = today - timedelta(days=i)
        if date.weekday() >= 5:
            continue
        res = requests.get(
            f"{API_URL}/documents.json",
            params={"date": date.strftime("%Y-%m-%d"), "type": 2},
            headers=headers,
            timeout=10,
        )
        if res.status_code != 200:
            continue

        for item in res.json().get("results", []):
            desc = item.get("docDescription")
            name = item.get("filerName")
            if desc and name and "四半期報告書" in desc and company_name in name:
              return item["docID"], desc
            elif desc and name and "四半期報告書" in desc and company_name in name.replace("株式会社", ""):
              return item["docID"], desc
            elif desc and name and "四半期報告書" in desc and company_name.replace("株式会社", "") in name:
              return item["docID"], desc


# -------------------------
# ZIPからCSVを抽出してデータフレームに
# -------------------------
def fetch_csv_from_zip(doc_id):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    res = requests.get(f"{API_URL}/documents/{doc_id}", params={"type": 5}, headers=headers)

    if "zip" not in res.headers.get("Content-Type", ""):
        raise ValueError("ZIP形式で取得できません")

    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        for filename in z.namelist():
            if filename.endswith(".csv"):
                raw = z.read(filename)
                encoding = chardet.detect(raw)["encoding"]
                df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
                return df
    raise ValueError("CSVファイルが見つかりませんでした")

# -------------------------
# 指標抽出
# -------------------------
def extract_metrics(df):
    metrics = {
        "NetSales": "売上高",
        "OperatingIncome": "営業利益",
        "OrdinaryIncome": "経常利益",
        "NetIncome": "純利益"
    }
    result = {}
    if not set(["項目ID", "金額"]).issubset(df.columns):
        return {}

    for key, label in metrics.items():
        match = df[df["項目ID"].astype(str).str.contains(key)]
        if not match.empty:
            val = match.iloc[0]["金額"]
            result[label] = int(val)
    return result

# -------------------------
# グラフ描画
# -------------------------
def plot_metrics(metrics_dict):
    if not metrics_dict:
        st.warning("有効な指標が見つかりませんでした。")
        return
    fig, ax = plt.subplots()
    ax.bar(metrics_dict.keys(), metrics_dict.values())
    ax.set_title("財務指標（四半期報告書より）")
    ax.set_ylabel("金額（円）")
    st.pyplot(fig)

# -------------------------
# UI部分
# -------------------------
company = st.text_input("企業名を入力（例: トヨタ自動車株式会社）")

if st.button("財務データ取得"):
    if not company:
        st.warning("企業名を入力してください")
        st.stop()

    with st.spinner("docIDを検索中..."):
        doc_id, desc = find_docid(company)

    if not doc_id:
        st.error("該当する四半期報告書が見つかりませんでした。")
    else:
        st.success(f"見つかりました：{desc} ｜ docID: {doc_id}")

        try:
            df = fetch_csv_from_zip(doc_id)
            metrics = extract_metrics(df)
            st.write("抽出された財務指標：", metrics)
            plot_metrics(metrics)
        except Exception as e:
            st.error(f"データ取得または解析に失敗しました: {e}")
