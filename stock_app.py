import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# APIキー読み込み
load_dotenv()
API_KEY = os.getenv("EDINET_API_KEY")
API_ENDPOINT = "https://disclosure.edinet-fsa.go.jp/api/v2"

def search_docid_by_company(company_name, days_back=60):
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    today = datetime.today()

    for _ in range(days_back):
        today -= timedelta(days=1)
        if today.weekday() >= 5:
            continue  # 土日スキップ

        url = f"{API_ENDPOINT}/documents.json"
        params = {"date": today.strftime("%Y-%m-%d"), "type": 2}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            for item in res.json().get("results", []):
                name = item.get("filerName", "")
                desc = item.get("docDescription", "")
                doc_id = item.get("docID", "")
                csv_flag = item.get("csvFlag", "0")
                # 書類の種類をフィルター
                if company_name in name and any(x in desc for x in ["四半期報告書", "有価証券報告書", "半期報告書"]):
                    return doc_id, name, desc, csv_flag
        except Exception:
            continue

    return None, None, None, "0"

# 使用例
if __name__ == "__main__":
    company = "トヨタ自動車株式会社"
    doc_id, name, desc, csv_flag = search_docid_by_company(company)
    if doc_id:
        print(f"見つかりました：{name}｜{desc}｜docID: {doc_id}｜CSV: {csv_flag}")
    else:
        print("該当する書類が見つかりませんでした。")

