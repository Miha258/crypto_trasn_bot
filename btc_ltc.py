from flask import Flask, request
from utils import *
import json
from aiogram import types
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

hashes = []
@app.route('/', methods = ['POST'])
async def hello_world():
    try:
        data = json.loads(request.get_data().decode('utf-8'))
        type, crypto, wallet, last_tx = find_transaction(data)
        print(1)
        print(last_tx.get('value'))
        if last_tx.get('value'):
            amount = last_tx['value'] / 10**8 
            amount_usd = amount * await get_crypto_rate(crypto)
            date = data['received'].replace('T', ' ').split('.')[0]
            transaction_data = {
                'tx_hash': data['hash'],
                'type': 'Пополнение' if type == 'outputs' else 'Перевод',
                'amount': amount,
                'amount_usd': amount_usd,
                'date': date
            }
            print(2)
            print(transaction_data['tx_hash'] != get_last_transaction(crypto, wallet), transaction_data['tx_hash'] not in hashes)
            if transaction_data['tx_hash'] != get_last_transaction(crypto, wallet) and transaction_data['tx_hash'] not in hashes:
                if len(hashes) > 100:
                    hashes.clear()
                hashes.append(transaction_data['tx_hash'])
                update_transaction(crypto, wallet, transaction_data['tx_hash'])
                transaction_data['wallet'] = wallet
                for chat_id in users:
                    try:
                        message = f"""
📘<em><strong>Тип: </strong>{transaction_data['type']}</em>

📮<strong>Хеш транзакции:</strong>
<code><pre><em>{transaction_data['tx_hash']}</em></pre></code>

🕰️<strong>Время:</strong><code><pre>{transaction_data['date']}</pre></code>

📭<strong>Адрес:</strong><code><pre>{wallet}</pre></code>

💰<strong>Количество:</strong>{transaction_data['amount']} {crypto}

💲<strong>Стоимость:</strong>{transaction_data['amount_usd']} USD
                        """ 
                        sub_kb = types.InlineKeyboardMarkup(inline_keyboard=[[
                            types.InlineKeyboardButton('Подписать', callback_data = f"subscribe_{transaction_data['date']}")
                        ]])
                        if str(chat_id) in admins and transaction_data['type'] == 'Перевод':
                            sub_kb = None
                        await bot.send_message(chat_id, message, parse_mode = "html", reply_markup = sub_kb)
                        register_transaction(transaction_data['date'], transaction_data)
                    except Exception as e:
                        print(e)
                        continue
                return transaction_data
            return transaction_data
        print('Error')
        return {'error': 400}
    except Exception as e:
        print('Error', e)
        return {'error': 400}

if __name__ == '__main__':
    app.run('0.0.0.0', 5000)