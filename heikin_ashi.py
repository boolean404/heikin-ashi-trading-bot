from datetime import datetime
import time
import pandas as pd
import pytz
import schedule
import secret
import ccxt

# for binance exchange
exchange = ccxt.binance({
    "apiKey": secret.BINANCE_API_KEY,
    "secret": secret.BINANCE_SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})

# input data for trading
name = 'Heikin Ashi'
symbol = 'SUIUSDT'
timeframe = '15m'
usdt_amount = 110
leverage = 20

# global variables
bot_status = True
adjusted_leverage = False
in_long_position = False
in_short_position = False

# get bot start run time
def get_bot_start_run_time():
    return time.strftime('%Y-%m-%d %H:%M:%S')

# get last price
def get_last_price():
    ticker = exchange.fetch_ticker(symbol)
    return float(ticker['last'])

# get account balance
def get_balance():
    account_info = exchange.fetch_balance()
    return round(account_info['total']['USDT'], 2)

# adjust leverage
def adjust_leverage():
    global adjusted_leverage
    response = exchange.fapiprivate_post_leverage({
        'symbol': symbol,
        'leverage': leverage
    })
    adjusted_leverage = True
    print(f"\n=> Leverage adjusted successfully to: {response['leverage']}x\n")

# start check entry condition
def check_entry_con(df):
    entry_con = None
    long_con = df['prev_open2'] > df['prev_close2'] and df['prev_open1'] < df['prev_close1'] and df['ha_open'] < df['ha_close']
    short_con = df['prev_open2'] < df['prev_close2'] and df['prev_open1'] > df['prev_close1'] and df['ha_open'] > df['ha_close']
    if long_con:
        entry_con = True
    if short_con:
        entry_con = False
    return entry_con
# end check entry condition

def get_data_frame(df):
    # heikin ashi candle
    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    df['ha_open'] = (df['open'].shift(1) + df['close'].shift(1)) / 2
    df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
    df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)

    df['prev_open1'] = df['ha_open'].shift(1)
    df['prev_open2'] = df['ha_open'].shift(2)
    df['prev_close1'] = df['ha_close'].shift(1)
    df['prev_close2'] = df['ha_close'].shift(2)
    df['prev_low'] = df['ha_low'].shift(1)
    df['prev_high'] = df['ha_high'].shift(1)

    df['entry_con'] = df.apply(check_entry_con, axis=1)
    df['total_margin'] = f'{get_balance()} usdt'

# Fetch open positions
def get_open_positions():
    # positions = exchange.fetch_positions_risk(symbols=[symbol])
    positions = exchange.fapiprivatev2_get_positionrisk()
    return [position for position in positions if position['symbol'] == symbol]

# change default timezone
def change_datetime_zone(update_time, timezone='Asia/Yangon'):
    utc_datetime = datetime.utcfromtimestamp(update_time)
    target_timezone = pytz.timezone(timezone)  # Replace timezone with the desired timezone
    return utc_datetime.replace(tzinfo=pytz.utc).astimezone(target_timezone) # retun is updatetime

# start check buy sell orders
def check_buy_sell_orders(df):
    global in_long_position
    global in_short_position
    
    amount = usdt_amount / get_last_price()

    last_row_index = len(df.index) - 1
    previous_row_index = last_row_index - 1

    # Drop the unnecessary columns
    ha_df = df[['timestamp', 'ha_open', 'ha_high', 'ha_low', 'ha_close', 'volume', 'entry_con', 'total_margin']]
    print(ha_df.tail(5))

    # get open position 
    open_positions = get_open_positions()
    # print(open_positions)

    for position in open_positions:
        position_symbol = position['symbol']
        position_side = position['positionSide']
        position_leverage = position['leverage']
        position_entry_price = float(position['entryPrice'])
        position_mark_price = float(position['markPrice'])
        position_amount = float(position['positionAmt'])
        position_pnl = round(float(position['unRealizedProfit']), 2)
        position_liquidation_price = round(float(position['liquidationPrice']), 2)
        position_amount_usdt =  round((position_amount * position_entry_price), 2)
        position_update_time = float(position['updateTime']) / 1000.0
        
        # change default timezone to local
        position_running_time = change_datetime_zone(position_update_time).strftime('%Y-%m-%d %H:%M:%S')

        # get long position
        if position_side == 'LONG' and position_amount != 0:
            # if bear candle occur close long position
            if df['ha_open'][previous_row_index] > df['ha_close'][previous_row_index]:
                close_long_position = exchange.create_market_sell_order(symbol=position_symbol, amount=abs(position_amount), params={'positionSide': position_side})
                in_long_position = False
                time.sleep(1)
                print(f"=> Closed {position_side} position..........")
                # print(close_long_position)
            else:
                print(f"\n=> {position_side} position is running since {position_running_time}")
                print(f"=> {position_symbol} | {position_leverage}x | {position_side} | {position_amount_usdt} USDT | Entry: {position_entry_price} | Mark: {round(position_mark_price, 2)} | Liquidation: {position_liquidation_price} | PNL: {position_pnl} USDT")
                in_long_position = True

        # get short position
        if position_side == 'SHORT' and position_amount != 0:
            # if bull candle occur close short position
            if df['ha_open'][previous_row_index] < df['ha_close'][previous_row_index]:
                close_short_position = exchange.create_market_buy_order(symbol=position_symbol, amount=abs(position_amount), params={'positionSide': position_side})
                in_short_position = False
                time.sleep(1)
                print(f"=> Closed {position_side} position..........")
                # print(close_short_position)
            else:
                print(f"\n=> {position_side} position is running since {position_running_time}")
                print(f"=> {position_symbol} | {position_leverage}x | {position_side} | {position_amount_usdt} USDT | Entry: {position_entry_price} | Mark: {round(position_mark_price, 2)} | Liquidation: {position_liquidation_price} | PNL: {position_pnl} USDT")
                in_short_position = True

    if not in_long_position and not in_short_position:
        print("\n=> There is no LONG or SHORT position!")
    
    # show last price and account balance
    account_balance = get_balance()
    print(f"\n=> Last price of {symbol} = {get_last_price()} | Future Account Margin = {account_balance} USDT\n")

    # long position
    if not in_long_position:
        if df['entry_con'][previous_row_index]:
            print(f"=> [1-3] LONG condition is occured at {df['timestamp'][previous_row_index]}..........")

            if account_balance > 1:
                buy_order = exchange.create_market_buy_order(symbol=symbol, amount=amount, params={'positionSide': 'LONG'})
                in_long_position = True
                time.sleep(1)
                print(f"=> [3-3] Market BUY ordered {buy_order['info']['symbol']} | {float(buy_order['amount']) * float(buy_order['price'])} USDT at {buy_order['price']}")
                # print(buy_order)
            else:
                print("=>[Error] Not enough balance for LONG position!")

    # short position
    if not in_short_position:
        if df['entry_con'][previous_row_index] == False:
            print(f"=> [1-2] SHORT condition is occured at {df['timestamp'][previous_row_index]}..........")

            if account_balance > 1:
                sell_order = exchange.create_market_sell_order(symbol=symbol, amount=amount, params={'positionSide': 'LONG'})
                in_short_position = True
                time.sleep(1)
                print(f"=> [2-2] Market SELL ordered {sell_order['info']['symbol']} | {abs(float(sell_order['amount']) * float(sell_order['price']))} USDT at {sell_order['price']}")
                # print(sell_order)
            else:
                print("=> [Error] Not enough balance for SHORT position!")

# end check buy sell orders

bot_start_run_time = get_bot_start_run_time()

def run_bot():
    try:
        print("\n\n#######################################################################################################################")
        print(f"\t\t{name} Trading Bot is running {symbol} | {timeframe} | {leverage}x | Since {bot_start_run_time}")
        print("#######################################################################################################################")
        print(f"Fetching new bars for {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        bars = exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=21)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC')
        
        # Convert to Myanmar timezone (UTC +6:30)
        myanmar_timezone = pytz.timezone('Asia/Yangon')
        df['timestamp'] = df['timestamp'].dt.tz_convert(myanmar_timezone)       

        # change leverage
        if not adjusted_leverage:
            adjust_leverage()
            time.sleep(1)
        
        # get data frame
        get_data_frame(df)

        # call all functions
        check_buy_sell_orders(df)
        
    except Exception as e:
        print(f"An error occurred: {e}")

schedule.every(5).seconds.do(run_bot)

while bot_status:
    schedule.run_pending()
    time.sleep(1)