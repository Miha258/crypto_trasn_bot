from aiogram import types, executor
import aiohttp
import asyncio
import logging
from utils import *
from config import *
from datetime import datetime
import subprocess
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from blockcypher import list_webhooks, subscribe_to_address_webhook, unsubscribe_from_webhook

class Form(StatesGroup):
    COIN = State()
    WALLET_ADDRESS = State()
    REMOVE_ADDRESS = State()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

@dp.message_handler(commands=['price'])
async def cmd_price(message: types.Message):
    args = message.text.split()
    if len(args) == 2:
        crypto_symbol = args[1].upper()
        price = await get_crypto_rate(crypto_symbol)
        if price is not None:
            await message.reply(f"Текущая цена на {crypto_symbol}: ${price}")
        else:
            await message.reply(f"Не удалось получить цену {crypto_symbol}")
    else:
        await message.reply("Применение: /price <crypto_symbol>")


@dp.message_handler(commands=['start'], state = "*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["Подписать", "Удалить", "Список"]
    keyboard.add(*buttons)
    await message.answer("Меню:", reply_markup=keyboard)


@dp.message_handler(text = 'Список')
async def get_wallets(message: types.Message):
    text = ""
    
    for key, wallets in wallets_to_monitor.items():
        text += f"\n\n<strong>{key}</strong>" + "\n" + "\n\n".join([f"<code><i>{wallet}</i></code>" for wallet in wallets])
    await message.answer(text, parse_mode = 'html')

@dp.message_handler(text = 'Подписать')
async def get_wallets(message: types.Message, state: FSMContext):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["LTC", "BTC", "USDT_TRC20"]
    keyboard.add(*buttons)
    await message.answer("Выберите тип кошелька:", reply_markup=keyboard)
    await state.set_state(Form.COIN)


@dp.message_handler(lambda message: message.text in ["LTC", "BTC", "USDT_TRC20"], state=Form.COIN)
async def process_coin(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['coin'] = message.text

    await state.set_state(Form.WALLET_ADDRESS)
    await message.answer('Введите адрес кошелька:')


@dp.message_handler(text = 'Удалить')
async def remove_wallets(message: types.Message, state: FSMContext):
    await state.set_state(Form.REMOVE_ADDRESS)
    await message.answer('Введите адрес кошелька, который хотите удалить:')


@dp.message_handler(state=Form.REMOVE_ADDRESS)
async def remove_wallets(message: types.Message, state: FSMContext):
    address = message.text
    found = False
    for key, wallets in wallets_to_monitor.items():
        for wallet in wallets:
            if address == wallet:
                found = True
                if key != 'USDT_TRC20':
                    for webhook in list_webhooks(blockcypher_token, key.lower()):
                        if webhook['address'] == address:
                            webhook_id = webhook['id']
                            unsubscribe_from_webhook(webhook_id, blockcypher_token, key.lower())
                udpated_wallets = wallets
                udpated_wallets.remove(wallet)
                wallets_to_monitor[key] = udpated_wallets

    if found:
        await message.answer('Адрес успешно удален')
        await state.finish()
    else:
        await message.answer('Адрес не найден.Попробуйте еще раз')

@dp.message_handler(state=Form.WALLET_ADDRESS)
async def process_wallet_address(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        coin_type = data['coin']
        wallet_address = message.text

        if wallet_address in wallets_to_monitor[coin_type]:
            await message.answer('Такой адрес уже есть в списке.Попробуйте другой:')
        else:
            if coin_type in ('BTC', 'LTC'):
                try:
                    subscribe_to_address_webhook(
                        domain,
                        wallet_address,
                        coin_symbol = coin_type.lower(),
                        api_key = blockcypher_token
                    )
                except:
                    return await message.answer(f'Неверный адрес кошелька для <strong>{coin_type}</strong>.Попробуйте другой:', parse_mode = "html")
            wallets_to_monitor[coin_type].append(wallet_address)
            await message.answer(f'Адрес кошелька для <strong>{coin_type}</strong> успешно добавлен в список: <strong>{wallet_address}</strong>', parse_mode = "html")
            await state.finish()

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
        subprocess.Popen(['python3', 'btc_ltc.py'])
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)

if __name__ == '__main__':
    start_polling_with_monitoring()