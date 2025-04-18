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

# EDINETコードのマッピング
target_date = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
code_map = {"7203.T": "E02744", "6758.T": "E01767", "9984.T": "E06525"}
edinet_code = code_map.get(ticker, None)

st.subheader("\U0001F4E5 EDINETからXBRLファイルを取得と進捗度表示")

if edinet_code:
    try:
        url = f"https://disclosure.edinet-fsa.go.jp/api/v1/documents.json?date={target_date}"
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        res = requests.get(url, headers=headers, timeout=10)
        docs = res.json().get("results", [])

        doc_id = None
        for doc in docs:
            if doc.get("edinetCode") == edinet_code and "四半期" in doc.get("docDescription", ""):
                doc_id = doc.get("docID")
                break

        if doc_id:
            st.success(f"四半期報告書が見つかりました！（docID: {doc_id}）")
            zip_url = f"https://disclosure.edinet-fsa.go.jp/api/v1/documents/{doc_id}?type=1"
            zip_res = requests.get(zip_url, timeout=15)
            extract_path = f"edinet_download/{doc_id}"
            os.makedirs(extract_path, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(zip_res.content)) as z:
                z.extractall(extract_path)

            xbrl_files = glob.glob(f"{extract_path}/*.xbrl")
            if not xbrl_files:
                st.warning("XBRLファイルが見つかりませんでした。")
            else:
                with open(xbrl_files[0], "r", encoding="utf-8") as file:
                    soup = BeautifulSoup(file.read(), "lxml-xml")

                tags = {
                    "売上高": "jppfs_cor:NetSales",
                    "営業利益": "jppfs_cor:OperatingIncome",
                    "経常利益": "jppfs_cor:OrdinaryIncome",
                    "純利益": "jppfs_cor:ProfitLoss"
                }

                data = {}
                for label, tag in tags.items():
                    current = soup.find(tag, contextRef="CurrentYTDConsolidatedDuration")
                    forecast = soup.find(tag, contextRef="ForecastConsolidatedDuration")
                    if current and forecast:
                        try:
                            current_val = float(current.text)
                            forecast_val = float(forecast.text)
                            progress = round(current_val / forecast_val * 100, 1)
                            data[label] = progress
                        except:
                            continue

                if data:
                    st.subheader("\U0001F4CA 四半期進捗度")
                    for label, pct in data.items():
                        st.write(f"{label}：{pct:.1f}%")
                        st.progress(min(int(pct), 100))

                    fig3, ax = plt.subplots(figsize=(6, 4))
                    bars = ax.bar(data.keys(), data.values(), color='skyblue')
                    ax.set_ylim(0, 120)
                    ax.axhline(100, color="red", linestyle="--", label="目標達成ライン")
                    ax.set_ylabel("進捗度（％）")
                    ax.set_title("四半期進捗度")
                    ax.legend()
                    for bar, val in zip(bars, data.values()):
                        ax.text(bar.get_x() + bar.get_width()/2, val + 2, f"{val:.1f}%", ha="center", fontsize=10)
                    st.pyplot(fig3)
                else:
                    st.warning("📉 データが抽出できませんでした。文書の構造が異なる可能性があります。")
        else:
            st.warning("四半期報告書のdocIDが見つかりませんでした。")

    except Exception as e:
        st.error(f"❌ 処理中にエラーが発生しました: {e}")
else:
    st.warning("この証券コードはEDINET対応表に登録されていません。")
