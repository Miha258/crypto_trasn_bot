import pickle, os, pygsheets
from config import *
import aiohttp

gc = pygsheets.authorize(service_file=CREDENTIALS_FILE)
def export_to_google_sheets(transaction_data):
    # Открытие Google Sheets по ID
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    # Поиск листа по заголовку
    sheet_title = 'Sheet1'  # Replace with the actual title of your sheet
    worksheet = None
    for sheet in spreadsheet:
        if sheet.title == sheet_title:
            worksheet = sheet
            break
    # Если лист не найден, создайте новый
    if worksheet is None:
        worksheet = spreadsheet.add_worksheet(sheet_title)
    print(worksheet.url)
    # Добавление строки данных
    worksheet.append_table(values=[
        [transaction_data['tx_hash'], transaction_data['type'], transaction_data['amount'], transaction_data['amount_usd'], transaction_data['date']]
    ])

def get_last_transaction(crypto, wallet):
    if not os.path.exists('cache.pickle'):
        last_transaction_hashes = {crypto: {wallet: "" for wallet in wallets} for crypto, wallets in wallets_to_monitor.items()}
        with open('cache.pickle', 'wb') as f:
            pickle.dump(last_transaction_hashes, f)
            return None

    with open('cache.pickle', 'rb') as f:
        data = pickle.load(f)
        return data[crypto][wallet]
    

def update_transaction(crypto, wallet, hash):
    with open('cache.pickle', 'rb') as f:
        data = pickle.load(f)
    
    data[crypto][wallet] = hash

    with open('cache.pickle', 'wb') as f:
        data = pickle.dump(data, f)
        
async def get_crypto_rate(crypto_symbol):
    url = f'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={crypto_symbol}&convert=USD'
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': coinmarketcap_token,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                data = await response.json()
                if 'data' in data and crypto_symbol in data['data']:
                    return data['data'][crypto_symbol]['quote']['USD']['price']
                else:
                    print(f"Error fetching rate for {crypto_symbol}. Response: {data}")
                    return 0.0
    except Exception as e:
        print(f"Exception while fetching rate for {crypto_symbol}: {e}")
        return 0.0