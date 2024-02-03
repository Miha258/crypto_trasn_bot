from aiogram import types, executor
import aiohttp
import asyncio
import logging
from utils import *
from config import *
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def on_start(msg: types.Message):
    await msg.answer("Мониторинг транзакций запущен")

dp.register_message_handler(on_start, commands=['start'])

@dp.message_handler(commands=['price'])
async def handle_price(message: types.Message):
    args = message.text.split()
    if len(args) == 2:
        crypto_symbol = args[1].upper()
        price = await get_crypto_rate(crypto_symbol)
        if price is not None:
            await message.reply(f"The current price of {crypto_symbol} is ${price}")
        else:
            await message.reply(f"Failed to fetch the price of {crypto_symbol}")
    else:
        await message.reply("Usage: /price <crypto_symbol>")

async def monitor_wallets():
    while True:
        for crypto, wallets in wallets_to_monitor.items():
            for wallet in wallets:
                transaction_data = await get_transaction_data(crypto, wallet)
                if transaction_data and transaction_data['tx_hash'] != get_last_transaction(crypto, wallet):
                    update_transaction(crypto, wallet, transaction_data['tx_hash'])
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
        await asyncio.sleep(60)  # Проверка каждую минуту

async def get_transaction_data(crypto, wallet):
    try:
        if crypto in ["USDT_TRC20"]:
            url = f'https://apilist.tronscan.org/api/transaction?sort=-timestamp&count=true&limit=1&start=0&address={wallet}'
            headers = {
                'TRON-Pro-API-KEY': tronscan_api_key,
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    data = await response.json()
                    if data.get('data'):
                        last_tx = data['data'][0]
                        amount = int(last_tx['contractData']['amount']) / 10**6  # Convert to USDT
                        amount_usd = amount 
                        
                        timestamp_seconds = last_tx['timestamp'] / 1000  # convert to seconds
                        dt_object = datetime.utcfromtimestamp(timestamp_seconds)
                        formatted_date = dt_object.strftime('%Y-%m-%dT%H:%M:%S')
                        return {
                            'tx_hash': last_tx.get('hash', 'Unknown'),
                            'tx_id': last_tx.get('id', 'Unknown'),
                            'type': 'Пополнение' if 'to' in last_tx['contractData'] and last_tx['contractData']['to'] == wallet else 'Перевод',
                            'amount': amount,
                            'amount_usd': amount_usd,
                            'date': formatted_date
                        }
                    else:
                        print(f"Unexpected content type: {response.content_type}")
    except Exception as e:
        print(e)

def start_polling_with_monitoring():
    async def on_startup(dp):
        all_users = set(incoming_users + outgoing_users)
        for user in all_users:
            await bot.send_message(user, 'Бот запущен')
        asyncio.create_task(monitor_wallets())
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)

if __name__ == '__main__':
    start_polling_with_monitoring()