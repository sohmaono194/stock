import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
from datetime import datetime, timedelta
import requests
import zipfile
import io
import os
import glob
from bs4 import BeautifulSoup

st.title("\U0001F4C8 株価とドル円の比較アプリ")

# 証券コードの入力
ticker = st.text_input("証券コードを入力してください（例: 7203.T）", value="7203.T")

# 日付範囲の指定
end_date = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
start_date = (datetime.today() - timedelta(days=5*365)).strftime("%Y-%m-%d")

# 株価と為替の取得・表示
if st.button("表示"):
    try:
        stock = yf.download(ticker, start=start_date, end=end_date)
        usd_jpy = yf.download("JPY=X", start=start_date, end=end_date)

        if stock.empty or usd_jpy.empty:
            st.error("株価またはドル円データが取得できませんでした。")
        else:
            company_name = yf.Ticker(ticker).info.get("longName", "会社名不明")
            st.subheader(f"\U0001F3E2 {company_name}（{ticker}）の株価とドル円の比較")

            df = pd.concat([stock["Close"], usd_jpy["Close"]], axis=1)
            df.columns = ["Stock", "USD_JPY"]
            df.dropna(inplace=True)

            fig, ax1 = plt.subplots(figsize=(12, 5))
            ax1.plot(df.index, df["Stock"], color='blue')
            ax1.set_ylabel(ticker, color='blue')
            ax2 = ax1.twinx()
            ax2.plot(df.index, df["USD_JPY"], color='orange')
            ax2.set_ylabel("USD/JPY", color='orange')
            ax1.grid(True)
            plt.tight_layout()
            st.pyplot(fig)

            st.subheader("\U0001F4CA 相関係数（棒グラフ）")
            corr = df["Stock"].corr(df["USD_JPY"])
            fig2, ax = plt.subplots(figsize=(4, 4))
            ax.bar([""], [corr], color='skyblue')
            ax.set_ylim(-1, 1)
            ax.text(0, corr + 0.03 * (1 if corr >= 0 else -1), f"{corr:.2f}", ha="center", fontsize=12)
            st.pyplot(fig2)
            st.write(f"相関係数: {corr:.4f}")

            csv = df.to_csv(index=True).encode('utf-8')
            st.download_button("\U0001F4C5 CSVをダウンロード", csv, file_name=f"{ticker}_vs_usdjpy.csv", mime="text/csv")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")

# EDINET書類の種類ごとの表示
st.subheader("\U0001F4C4 EDINET 提出書類一覧（種類で絞り込み）")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ja,en;q=0.9"
}

@st.cache_data(ttl=3600)
def get_edinet_documents(date_str):
    url = f"https://disclosure.edinet-fsa.go.jp/api/v1/documents.json?date={date_str}"
    res = requests.get(url, headers=headers, timeout=10)
    if "application/json" in res.headers.get("Content-Type", ""):
        return res.json().get("results", [])
    return []

target_date = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
docs = get_edinet_documents(target_date)

# フィルターUI
selected_types = st.multiselect("表示したい書類の種類を選択：", ["有価証券報告書", "四半期報告書", "臨時報告書", "訂正報告書"], default=["四半期報告書"])

# 表示
type_docs = [doc for doc in docs if any(t in doc.get("docDescription", "") for t in selected_types)]

if type_docs:
    for doc in type_docs:
        st.write(f"📄 {doc.get('docDescription')}｜{doc.get('filerName')}｜docID: {doc.get('docID')}")
else:
    st.info("該当する書類が見つかりませんでした。")
