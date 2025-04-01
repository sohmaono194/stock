import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
from datetime import datetime, timedelta
import seaborn as sns

st.title("📈 株価とドル円の比較アプリ")

# 入力欄
ticker = st.text_input("証券コードを入力してください（例: 7203.T）", value="7203.T")

# 日付自動設定（5年前〜昨日）
end_date = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
start_date = (datetime.today() - timedelta(days=5*365)).strftime("%Y-%m-%d")

# 実行ボタン
if st.button("表示"):
    try:
        stock = yf.download(ticker, start=start_date, end=end_date)
        usd_jpy = yf.download("JPY=X", start=start_date, end=end_date)
         # 会社名を取得して表示
        info = yf.Ticker(ticker).info
        company_name = info.get("longName", "会社名不明")
        st.subheader(f"🏢 {company_name}（{ticker}）の株価とドル円の比較")
        # ✅ データが空だった場合はエラー表示
        if stock.empty or usd_jpy.empty:
            st.error("株価またはドル円データが取得できませんでした。証券コードを確認してください。")
        else:
            # .ilocで1列目を確実に取得（Series化）
            stock_close = stock["Close"]
            if isinstance(stock_close, pd.DataFrame):
                stock_close = stock_close.iloc[:, 0]

            usd_jpy_close = usd_jpy["Close"]
            if isinstance(usd_jpy_close, pd.DataFrame):
                usd_jpy_close = usd_jpy_close.iloc[:, 0]

            # データフレーム作成
            df = pd.DataFrame({
                "Stock": stock_close,
                "USD_JPY": usd_jpy_close
            }).dropna()

            # グラフ表示（2軸）
            fig, ax1 = plt.subplots(figsize=(12, 5))
            ax1.plot(df.index, df["Stock"], color='blue')
            ax1.set_ylabel(ticker, color='blue')
            ax2 = ax1.twinx()
            ax2.plot(df.index, df["USD_JPY"], color='orange')
            ax2.set_ylabel("USD/JPY", color='orange')
            
            ax1.grid(True)
            plt.tight_layout()
            st.pyplot(fig)

            # 相関係数（棒グラフのみ・ラベル非表示）
            st.subheader("📊 相関係数（棒グラフ）")

            corr_value = df.corr().iloc[0, 1]

            fig_bar, ax = plt.subplots(figsize=(4, 4))
            ax.bar([""], [corr_value], color='skyblue')
            ax.set_ylim(-1, 1)
            ax.set_ylabel("")
            ax.set_xticks([])

            # ✅ 棒の中（または上）に数値を表示
            ax.text(0, corr_value + 0.03 * (1 if corr_value >= 0 else -1), f"{corr_value:.2f}",
            ha="center", va="bottom", fontsize=12, fontweight="bold")

            st.pyplot(fig_bar)
            
            # 数値も表示（オプション）
            st.write(f"相関係数: {corr_value:.4f}")


            # CSVダウンロード
            csv = df.to_csv(index=True).encode('utf-8')
            st.download_button("📥 CSVをダウンロード", csv, file_name=f"{ticker}_vs_usdjpy.csv", mime="text/csv")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
