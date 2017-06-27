from jqdata import *
import numpy as np
import pandas as pd
import talib as ta

class Status(Enum):
    INIT    = 0  # 在每天交易开始时，置为INIT
    BUYING_SELLING  = 1  # 已经挂单买入及卖出，但还未成交
    BOUGHT_SELLING  = 2  # 买入挂单已经成交，卖出挂单还未成交
    BOUGHT_SOLD     = 3  # 买入挂单已经成交，卖出挂单已经成交
    BUYING_SOLD     = 4  # 买入挂单还未成交，卖出挂单已经成交
    NONE            = 5  # 不再做任何交易
    
    
def initialize(context):
    log.info("---> initialize @ %s" % (str(context.current_dt))) 
    g.basestock_df = pd.DataFrame(columns=("stock", "close", "min_vol", "max_vol", "lowest", "highest", "operator", "status", "position", "sell_order_id", "buy_order_id"))
    g.count = 0
    g.firstrun = True
    g.first_value = 1000000
    g.total_value = 100000000
    g.position_count = 30
    g.expected_revenue = 0.003
    # 获得沪深300的股票列表, 5天波动率大于2%，单价大于10.00元, 每标的买入100万元
    stock_list = get_index_stocks('399300.XSHE')
    for stock in stock_list:
        df = get_price(stock, count = 6, end_date = str(context.current_dt), frequency = 'daily', fields = ['high','low', 'close'])
        for i in range(5):
            df.ix[i+1, 'Volatility'] = (df.ix[i, 'high'] - df.ix[i, 'low']) / df.ix[i+1, 'close']
        
        #选择单价大于10.0元
        if df.ix[5, 'close'] > 10.00:
            vol_df = df.ix[1:6,['Volatility']].sort(["Volatility"], ascending=True)
            min_vol = vol_df.iat[0, 0]
            max_vol = vol_df.iat[4, 0]
            #选择最近5天的波动率最小值大于0.02
            if min_vol > 0.02:
                g.basestock_df.loc[g.count] = [stock, df.ix[5, 'close'], min_vol, max_vol, 0, 0, 0, Status.INIT, 0, -1, -1]
                g.count += 1
            else:
                pass
        else:
            pass
    
    if g.count < g.position_count:
        g.position_count = g.count
        
    
    

    # 设置基准
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)


def process_initialize(context):
    pass


def before_trading_start(context):
    log.info("初始化买卖状态为INIT")
    for i in range(g.position_count):
        g.basestock_df.iat[i, 7] = Status.INIT
    
def buy_stock(context, stock, amount, limit_price, index):
    buy_order = order(stock, amount, LimitOrderStyle(limit_price))
    
    if buy_order is not None:
        #log.info("buy_order: ", buy_order)
        g.basestock_df.iat[index, 10] = buy_order.order_id;
    
def sell_stock(context, stock, amount, limit_price, index):
    sell_order = order(stock, -amount, LimitOrderStyle(limit_price))
    
    if sell_order is not None:
        #log.info("sell_order: ", sell_order)
        g.basestock_df.iat[index, 9] = sell_order.order_id;
    
def sell_buy(context, stock, close_price, index):
    if g.basestock_df.iat[index, 7] != Status.INIT:
        log.warn("NO Chance to SELL_BUY, current status: ", g.basestock_df.iat[index, 7])
        return
    
    amount = 0.25 * context.portfolio.positions[stock].total_amount
    
    if amount % 100 != 0:
        amount_new = amount - (amount % 100)
        amount = amount_new

    limit_price = close_price + 0.01

    sell_ret = sell_stock(context, stock, amount, limit_price, index)
    
    yesterday = get_price(stock, count = 1, end_date=str(context.current_dt), frequency='daily', fields=['close'])

    limit_price = close_price - yesterday.iat[0, 0] * g.expected_revenue
    buy_ret = buy_stock(context, stock, amount, limit_price, index)
    
    g.basestock_df.iat[index, 7] = Status.BUYING_SELLING
    
def buy_sell(context, stock, close_price, index):
    if g.basestock_df.iat[index, 7] != Status.INIT:
        log.warn("NO Chance to BUY_SELL, current status: ", g.basestock_df.iat[index, 7])
        return
    
    amount = 0.25 * context.portfolio.positions[stock].total_amount
    
    if amount % 100 != 0:
        amount_new = amount - (amount % 100)
        #log.info("amount from %d to %d", amount, amount_new)
        amount = amount_new
    
    current_data = get_current_data()

    limit_price = close_price - 0.01
    buy_stock(context, stock, amount, limit_price, index)
    

    yesterday = get_price(stock, count = 1, end_date=str(context.current_dt), frequency='daily', fields=['close'])
    limit_price = close_price - yesterday.iat[0, 0] * g.expected_revenue
    sell_stock(context, stock, amount, limit_price, index)
    g.basestock_df.iat[index, 7] = Status.BUYING_SELLING
    
    
def get_minute_count(context):
    '''
     9:30 -- 11:30
     13:00 --- 15:00
     '''
    current_hour = context.current_dt.hour
    current_min  = context.current_dt.minute
    
    if current_hour < 12:
        minute_count = (current_hour - 9) * 60 + current_min - 29
    else:
        minute_count = (current_hour - 11) * 60 + current_min + 120

    return minute_count
    
def update_89_lowest(context):
    minute_count = get_minute_count(context)
    if minute_count > 89:
        minute_count = 89
    for i in range(g.position_count):
        low_df = get_price(g.basestock_df.ix[i, 0], count = minute_count, end_date=str(context.current_dt), frequency='1m', fields=['close'])
        g.basestock_df.iat[i, 4] = low_df.sort(['close'], ascending = True).iat[0,0]
        
def update_233_highest(context):
    minute_count = get_minute_count(context)
    if minute_count > 233:
        minute_count = 233
    for i in range(g.position_count):
        high_df = get_price(g.basestock_df.ix[i, 0], count = minute_count, end_date=str(context.current_dt), frequency='1m', fields=['close'])
        g.basestock_df.iat[i, 5] = high_df.sort(['close'], ascending = False).iat[0,0]
        
def cancel_open_order(context):
    orders = get_open_orders()
    for _order in orders.values():
        cancel_order(_order)
        log.warn("cancel order: ", _order)
    

def reset_position(context):
    for i in range(g.position_count):
        stock = g.basestock_df.ix[i, 0]
        src_position = g.basestock_df.ix[i, 8]
        cur_position = context.portfolio.positions[stock].total_amount
        if src_position != cur_position:
            log.info("src_position : cur_position", src_position, cur_position)
            _order = order(stock, src_position - cur_position)
            log.warn("reset posiont: ", _order)
        
        
def update_socket_statue(context):
    orders = get_orders()
    if len(orders) == 0:
        return
    hour = context.current_dt.hour
    minute = context.current_dt.minute
    for i in range(g.position_count):
        stock = g.basestock_df.ix[i, 0]
        sell_order_id = g.basestock_df.ix[i, 9]
        buy_order_id = g.basestock_df.ix[i, 10]
        status = g.basestock_df.ix[i, 7]
        if (status != Status.INIT) and (Status != Status.NONE) and (sell_order_id != -1) and (buy_order_id != -1):
            sell_order =  orders.get(sell_order_id)
            buy_order = orders.get(buy_order_id)
            if (sell_order is not None) and (buy_order is not None):
                if sell_order.status == OrderStatus.held and buy_order.status == OrderStatus.held:
                    g.basestock_df.ix[i, 9] = -1
                    g.basestock_df.ix[i, 10] = -1
                    g.basestock_df.ix[i, 7] = Status.INIT
        
        if hour == 14 and g.basestock_df.ix[i, 7] == Status.INIT:
            g.basestock_df.ix[i, 7] = Status.NONE
            
            
def handle_data(context, data):
    # 0. 购买30支股票
    if str(context.run_params.start_date) ==  str(context.current_dt.strftime("%Y-%m-%d")):
        if g.firstrun is True:
            for i in range(g.position_count):
                #log.info("Buy[%d]---> stock: %s, value: %d", i + 1, g.basestock_df.ix[i, 0], g.first_value)
                myorder = order_value(g.basestock_df.ix[i, 0], 1000000)
                g.basestock_df.ix[i, 8] = myorder.amount
                #log.info(myorder)
            g.firstrun = False
            log.info("\n", g.basestock_df, g.count)
        return
    
    hour = context.current_dt.hour
    minute = context.current_dt.minute
    
    if hour == 14 and minute == 45:
        cancel_open_order(context)
        reset_position(context)
        return
    if hour == 14 and minute > 45:
        return
    update_89_lowest(context)
    update_233_highest(context)
    
    # 根据订单状态来更新 buying -> bought or selling -> sold
    update_socket_statue(context)
    
    
    
    
    if get_minute_count(context) < 4:
        return
    # 1. 循环股票列表，看当前价格是否有买入或卖出信号
    for i in range(g.position_count):
        stock = g.basestock_df.ix[i, 0]
        lowest_89 = g.basestock_df.iat[i, 4]
        highest_233 = g.basestock_df.iat[i, 5]
        if lowest_89 == highest_233:
            continue
        close_m = get_price(stock, count = 4, end_date=str(context.current_dt), frequency='1m', fields=['close'])
        
        close =  np.array([close_m.iat[0,0], close_m.iat[1,0], close_m.iat[2,0], close_m.iat[3,0]]).astype(float)
        #log.info("handle MA: ", stock, close)
        for j in range(4):
            close[j] = ((close[j] - lowest_89) * 1.0 / (highest_233 - lowest_89)) * 4
        operator_line =  ta.MA(close, 4)
        
        if g.basestock_df.iat[i, 6] < 0.1 and operator_line[3] > 0.1 and g.basestock_df.iat[i, 6] != 0.0:
            log.info("WARNNIG: Time: %s, BUY SIGNAL for %s, from %f to %f, close_price: %f", 
                    str(context.current_dt), stock, g.basestock_df.iat[i, 6], operator_line[3], close_m.iat[3,0])
            buy_sell(context, stock, close_m.iat[3,0], i)
        elif g.basestock_df.iat[i, 6] > 3.9 and operator_line[3] < 3.9:
            log.info("WARNNING: Time: %s, SELL SIGNAL for %s, from %f to %f, close_price: %f", 
                    str(context.current_dt), stock, g.basestock_df.iat[i, 6], operator_line[3], close_m.iat[3,0])
            sell_buy(context, stock, close_m.iat[3,0], i)
        g.basestock_df.iat[i, 6] = operator_line[3]
        
      
def after_trading_end(context):
    '''
    log.info("~~~~~~~~~~~~~~~未成交订单~~~~~~~~~~~~~~~~~~~~")
    orders = get_open_orders()
    for _order in orders.values():
        log.info(_order)
    log.info("~~~~~~~~~~~~~~~所有订单~~~~~~~~~~~~~~~~~~~~")
    orders = get_orders()
    for _order in orders.values():
        log.info(_order)
    log.info("~~~~~~~~~~~~~~~成交信息~~~~~~~~~~~~~~~~~~~~~")
    trades = get_trades()
    for _trade in trades.values():
        log.info(_trade)
    log.info("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    '''
    pass