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
    TRANSACTION_TEXT = State()

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
    buttons = ["Добавить", "Удалить", "Список"]
    keyboard.add(*buttons)
    if str(message.from_id) in su_admins:
        await message.answer("Меню:", reply_markup=keyboard)

@dp.message_handler(IsAdminFilter(), lambda m: m.text == 'Список')
async def get_wallets(message: types.Message):
    text = ""
    for key, wallets in wallets_to_monitor.items():
        text += f"\n\n<strong>{key}</strong>" + "\n" + "\n\n".join([f"<code><i>{wallet}</i></code>" for wallet in wallets])
    await message.answer(text, parse_mode = 'html')

@dp.message_handler(IsAdminFilter(), lambda m: m.text == 'Добавить')
async def get_wallets(message: types.Message, state: FSMContext):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["LTC", "BTC", "USDT_TRC20"]
    keyboard.add(*buttons)
    await message.answer("Выберите тип кошелька:", reply_markup=keyboard)
    await state.set_state(Form.COIN)


@dp.message_handler(IsAdminFilter(), lambda m: m.text in ["LTC", "BTC", "USDT_TRC20"], state=Form.COIN)
async def process_coin(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['coin'] = message.text

    await state.set_state(Form.WALLET_ADDRESS)
    await message.answer('Введите адрес кошелька:')


@dp.message_handler(IsAdminFilter(), lambda m: m.text == 'Удалить')
async def remove_wallets(message: types.Message, state: FSMContext):
    await state.set_state(Form.REMOVE_ADDRESS)
    await message.answer('Введите адрес кошелька, который хотите удалить:')

@dp.message_handler(IsAdminFilter(), state=Form.REMOVE_ADDRESS)
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

@dp.message_handler(IsAdminFilter(), state=Form.WALLET_ADDRESS)
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


@dp.callback_query_handler(lambda cb: 'subscribe' in cb.data)
async def subscribe_transaction(callback_query: types.CallbackQuery, state: FSMContext):
    trans_id = callback_query.data.split('_')[-1]
    if check_transaction(trans_id):
        await state.set_data({'trans_id': trans_id, "msg_id": callback_query.message.message_id})
        await state.set_state(Form.TRANSACTION_TEXT)
        await callback_query.message.answer('Введите текст тразакции:')
    else:
        await callback_query.answer('Тразакцию подписал уже кто-то другой.', show_alert = True)
        await callback_query.message.delete_reply_markup()

@dp.message_handler(state=Form.TRANSACTION_TEXT)
async def save_transaction(message: types.Message, state: FSMContext):
    comment = message.text
    data = await state.get_data()
    transaction_data = check_transaction(data['trans_id'])
    transaction_data['comment'] = comment
    await bot.edit_message_reply_markup(message.from_id, data['msg_id'], reply_markup = None)
    unregister_transaction(data['trans_id'])
    export_to_google_sheets(transaction_data)
    await message.answer('Тразакция успешно подписана и сохранена!')
    await state.finish()


async def monitor_wallets():
    while True:
        for crypto, wallets in wallets_to_monitor.items():
            for wallet in wallets:
                transaction_data = await get_transaction_data(crypto, wallet)
                if transaction_data:
                    if transaction_data['tx_hash'] != get_last_transaction(crypto, wallet): #and transaction_data['token'] in ('USDT', 'USDT_TRC20'):
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

💰<strong>Количество:</strong>{transaction_data['amount']} {transaction_data['token']}

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
        await asyncio.sleep(60)

async def get_transaction_data(crypto, wallet):
    try:
        if crypto in ["USDT_TRC20"]:
            url = f'https://apilist.tronscanapi.com/api/filter/trc20/transfers?limit=1&start=0&sort=-timestamp&count=true&filterTokenValue=0&relatedAddress={wallet}'
            headers = {
                'TRON-Pro-API-KEY': tronscan_api_key,
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    data = await response.json()
                    if data.get('token_transfers'):
                        last_tx = data['token_transfers'][0]
                        amount = int(last_tx['quant']) / 10**6  # Convert to USDT
                        amount_usd = amount 
                        
                        timestamp_seconds = last_tx['block_ts'] / 1000  # convert to seconds
                        dt_object = datetime.utcfromtimestamp(timestamp_seconds)
                        formatted_date = dt_object.strftime('%Y-%m-%dT%H:%M:%S')
                        return {
                            'tx_hash': last_tx.get('transaction_id', 'Unknown'),
                            'type': 'Пополнение' if last_tx['to_address'] == wallet else 'Перевод',
                            'amount': amount,
                            'amount_usd': amount_usd,
                            'date': formatted_date,
                            'token': last_tx['tokenInfo']['tokenAbbr']
                        }
                    else:
                        print(f"Unexpected content type: {response.content_type}")
    except Exception as e:
        print(e)

def start_polling_with_monitoring():
    async def on_startup(dp):
        for user in users:
            await bot.send_message(user, 'Бот запущен')
        asyncio.create_task(monitor_wallets())
        subprocess.Popen(['python3', 'btc_ltc.py'])
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)

if __name__ == '__main__':
    start_polling_with_monitoring()