import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
from datetime import datetime, timedelta
import requests
import zipfile
import io
import os
from dotenv import load_dotenv

# --- .envからAPIキー読み込み ---
load_dotenv()
API_KEY = os.getenv("EDINET_API_KEY")

st.title("📈 株価とドル円比較 ＋ 📄 EDINET提出書類取得＆ファイル確認アプリ")

# ============================
# 📈 株価とドル円比較
# ============================

st.header("📈 株価とドル円の比較")

ticker = st.text_input("証券コードを入力してください（例: 7203.T）", value="7203.T")

end_date = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
start_date = (datetime.today() - timedelta(days=5*365)).strftime("%Y-%m-%d")

if st.button("株価とドル円を表示"):
    try:
        stock = yf.download(ticker, start=start_date, end=end_date)
        usd_jpy = yf.download("JPY=X", start=start_date, end=end_date)

        if stock.empty or usd_jpy.empty:
            st.error("株価またはドル円データが取得できませんでした。")
        else:
            company_name = yf.Ticker(ticker).info.get("longName", "会社名不明")
            st.subheader(f"🏢 {company_name}（{ticker}）の株価とドル円の比較")

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

            st.subheader("📊 相関係数（棒グラフ）")
            corr = df["Stock"].corr(df["USD_JPY"])
            fig2, ax = plt.subplots(figsize=(4, 4))
            ax.bar([""], [corr], color='skyblue')
            ax.set_ylim(-1, 1)
            ax.text(0, corr + 0.03 * (1 if corr >= 0 else -1), f"{corr:.2f}", ha="center", fontsize=12)
            st.pyplot(fig2)
            st.write(f"相関係数: {corr:.4f}")

            csv = df.to_csv(index=True).encode('utf-8')
            st.download_button("📅 CSVをダウンロード", csv, file_name=f"{ticker}_vs_usdjpy.csv", mime="text/csv")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")

# ============================
# 📄 EDINET提出書類取得
# ============================

st.header("📄 EDINET提出書類取得（v2 API）")

@st.cache_data(ttl=86400)
def fetch_documents_last_90_days_v2(selected_types):
    results = []
    checked = 0
    date = datetime.today()

    headers = {
        "Ocp-Apim-Subscription-Key": API_KEY
    }

    while len(results) < 1000 and checked < 180:
        date -= timedelta(days=1)
        if date.weekday() >= 5:
            continue
        date_str = date.strftime("%Y-%m-%d")
        url = f"https://api.edinet-fsa.go.jp/api/v2/documents.json?date={date_str}"

        try:
            res = requests.get(url, headers=headers, timeout=10)
            if "application/json" in res.headers.get("Content-Type", ""):
                day_docs = res.json().get("results", [])
                for doc in day_docs:
                    desc = doc.get("docDescription", "")
                    if any(t in desc for t in selected_types):
                        doc["date"] = date_str
                        results.append(doc)
        except Exception as e:
            st.warning(f"{date_str}：取得エラー（{e}）")
        checked += 1

    return results

selected_types = st.multiselect(
    "表示する書類の種類：",
    ["有価証券報告書", "四半期報告書", "臨時報告書", "訂正報告書"],
    default=["四半期報告書"]
)

if st.button("直近提出書類を取得（API認証付き）"):
    with st.spinner("提出書類取得中..."):
        docs = fetch_documents_last_90_days_v2(selected_types)
        st.success(f"{len(docs)} 件の提出書類を取得しました。")
        for doc in docs[:100]:
            st.write(f"{doc['date']}｜{doc['docDescription']}｜{doc['filerName']}｜docID: {doc['docID']}")

# ============================
# 🧩 docIDのファイル形式チェック
# ============================

st.header("🧩 EDINET docIDファイル形式確認")

doc_id_check = st.text_input("docIDを入力してください（例: S100UP32）", key="docid_check")

if st.button("docIDファイル形式を確認"):
    if not doc_id_check:
        st.warning("docIDを入力してください！")
    else:
        with st.spinner("ファイル形式確認中..."):
            try:
                url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id_check}?type=1"
                headers = {
                    "Ocp-Apim-Subscription-Key": API_KEY
                }
                res = requests.get(url, headers=headers, timeout=20)

                content_type = res.headers.get("Content-Type", "不明")
                st.write(f"🌐 返ってきたContent-Type: **{content_type}**")

                if "zip" in content_type:
                    st.success("✅ ZIPファイル（XBRLデータあり）")
                elif "pdf" in content_type:
                    st.warning("⚠️ PDFファイルです（XBRLデータなし）")
                elif "html" in content_type:
                    st.error("❌ HTMLページでした。docID無効または閲覧期限切れかも。")
                else:
                    st.error(f"❓ 未知のファイルタイプ（{content_type}）")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
