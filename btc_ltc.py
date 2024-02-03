from flask import Flask, request
from utils import *
import json
from config import wallets_to_monitor, bot

app = Flask(__name__)
def find_transaction(data):
    types = ("inputs", "outputs")
    for type in types:
        for output in data[type]:
            for crypto, wallets in wallets_to_monitor.items():
                for wallet in wallets:
                    if output["addresses"][0] == wallet:
                        return type, crypto, wallet, output

@app.route('/', methods = ['POST'])
async def hello_world():
    data = json.loads(request.get_data().decode('utf-8'))
    type, crypto, wallet, last_tx = find_transaction(data)
    amount = last_tx['value'] / 10**8 
    amount_usd = amount * await get_crypto_rate(crypto)
    date = data['received']
    transaction_data = {
        'tx_hash': data['hash'],
        'tx_id': last_tx['script'],
        'type': 'Пополнение' if type == 'outputs' else 'Перевод',
        'amount': amount,
        'amount_usd': amount_usd,
        'date': date
    }
    user_chat_ids = incoming_users if 'Пополнения' else outgoing_users
    for chat_id in user_chat_ids:
        try:
            message = f"""
📥<strong>Номенр транзакции:</strong>
<pre><em>{transaction_data['tx_hash']}</em></pre>

🕰️<strong>Время:</strong><pre>{transaction_data['date']}</pre>

📭<strong>Адрес:</strong><pre>{wallet}</pre>

📮<strong>Айди транзакции:</strong><pre>{transaction_data['tx_id']}</pre>

📘<strong>Тип: </strong>{transaction_data['type']}

💰<strong>Количество:</strong>{transaction_data['amount']} {crypto}

💲<strong>Стоимость:</strong>{transaction_data['amount_usd']} USD
                        """
            await bot.send_message(chat_id, message, parse_mode = "html")
            export_to_google_sheets(transaction_data)
        except Exception as e:
            print(e)
            return {'error': e}
    return transaction_data

if __name__ == '__main__':
    app.run('0.0.0.0', 5000)