import datetime
import json
import os
import urllib.parse
import urllib.request
from typing import List, Dict, Union
from dotenv import load_dotenv

# load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

EDINET_API_KEY = os.environ.get('EDINET_API_KEY')

def filter_by_codes(docs: List[Dict], edinet_codes: Union[List[str], str] = [],
                    doc_type_codes: Union[List[str], str] = []) -> List[Dict]:
    """Filter documents by EDINET codes and document type codes."""
    if len(edinet_codes) == 0:
        edinet_codes = [doc['edinetCode'] for doc in docs]
    elif isinstance(edinet_codes, str):
        edinet_codes = [edinet_codes]

    if len(doc_type_codes) == 0:
        doc_type_codes = [doc['docTypeCode'] for doc in docs]
    elif isinstance(doc_type_codes, str):
        doc_type_codes = [doc_type_codes]

    return [doc for doc in docs if doc['edinetCode'] in edinet_codes and
            doc['docTypeCode'] in doc_type_codes]

def disclosure_documents(date: Union[str, datetime.date],
                         type: int = 2) -> Dict:
    """Retrieve disclosure documents from EDINET API for a specified date."""
    if isinstance(date, str):
        try:
            datetime.datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Invalid date string. Use format 'YYYY-MM-DD'")
        date_str = date
    elif isinstance(date, datetime.date):
        date_str = date.strftime('%Y-%m-%d')
    else:
        raise TypeError("Date must be a string ('YYYY-MM-DD') or datetime.date")

    url = "https://disclosure.edinet-fsa.go.jp/api/v2/documents.json"
    params = {
        "date": date_str,
        "type": type, # '1' is metadata only, '2' is metadata and results
        "Subscription-Key": EDINET_API_KEY,
    }
    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"

    with urllib.request.urlopen(full_url) as response:
        return json.loads(response.read().decode('utf-8'))

def get_document(doc_id: str) -> urllib.request.urlopen:
    """Retrieve a specific document from EDINET API."""
    url = f'https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}'
    params = {
      "type": 5,  # '5' for CSV
      "Subscription-Key": EDINET_API_KEY,
    }
    query_string = urllib.parse.urlencode(params)
    full_url = f'{url}?{query_string}'
    return urllib.request.urlopen(full_url)

def save_document(doc_res: urllib.request.urlopen, output_path: str) -> None:
    """Save the document content to file."""
    with open(output_path, 'wb') as file_out:
        file_out.write(doc_res.read())
    print(f'Saved: {output_path}')

def get_documents_for_date_range(start_date: datetime.date,
                                 end_date: datetime.date,
                                 edinet_codes: List[str] = [],
                                 doc_type_codes: List[str] = []) -> List[Dict]:
    """Retrieve and filter documents for a date range."""
    matching_docs = []
    current_date = start_date
    while current_date <= end_date:
        docs_res = disclosure_documents(date=current_date)
        if docs_res['results']:
            filtered_docs = filter_by_codes(docs_res['results'], edinet_codes,
                                            doc_type_codes)
            matching_docs.extend(filtered_docs)
        current_date += datetime.timedelta(days=1)
    return matching_docs


def run_demo():
    """Demonstrate the usage of EDINET API by requesting filings
    from date range, filtering the results, and saving reports to disk."""
    start_date = datetime.date(2024, 2, 14)
    end_date = datetime.date(2024, 2, 15)

    doc_type_codes = ['140', '160'] # Quarterly and Semi-Annual Reports
    megabanks = {
        'E03614': "Sumitomo Mitsui Financial Group, Inc.",
        'E03615': "Mizuho Financial Group, Inc.",
        'E03606': "Mitsubishi UFJ Financial Group, Inc.",
        'E03530': "SBI Shinsei Bank, Limited",
    }

    print(f"Requesting documents of type {doc_type_codes}, filed by:")
    [print(f"{index}. {item}") for index, item in
     enumerate(list(megabanks.values()), start=1)]
    print()

    docs = get_documents_for_date_range(start_date, end_date,
                                        list(megabanks.keys()), doc_type_codes)

    print(f"Found {len(docs)} matching documents. Saving results:")
    for doc in docs:
        doc_id = doc['docID']
        edinet_code = doc['edinetCode']
        doc_type_code = doc['docTypeCode']
        filer = doc['filerName']
        save_name = f'{edinet_code}_{filer}_{doc_type_code}_{doc_id}.zip'
        output_path = os.path.join('.', save_name)
        doc_res = get_document(doc_id)
        save_document(doc_res, output_path)


if __name__ == '__main__':
    print("""
        * EDINET API Demo *
        Japanese Financial Disclosure Document Retrieval
        日本の金融開示文書取得
    """)
    run_demo()