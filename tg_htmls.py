#老鲸鱼的模版
def tg_message_html_1(item):
    msg = '''
<b>🐋🐋🐋🐋{title}🐋🐋🐋🐋</b>

<b>token:</b>
<code>{mint}</code>

<b>购买的老钱包:</b>
<code>{traderPublicKey}</code>

<b>购买金额:{amount:.4f} SOL</b>
<b>钱包余额:{sol:.4f} SOL</b>
<b>钱包代币余额总计: {total_balance:.4f} USDT</b>
<b>流动性: {liquidity:.4f} USDT</b>
<b>链上查看钱包: <a href="https://solscan.io/account/{traderPublicKey}">详情</a></b>
<b>GMGN查看钱包: <a href="https://gmgn.ai/sol/address/{traderPublicKey}">详情</a></b>
<b>交易详情:<a href="https://solscan.io/tx/{signature}">查看</a></b>

📈<b>查看K线: <a href="https://pump.fun/coin/{mint}">PUMP</a></b> <b><a href="https://gmgn.ai/sol/token/{mint}">GMGN</a></b>

<a href="https://t.me/pepeboost_sol_bot?start=8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>PEPE一键买入</b></a>

<a href="https://t.me/sol_dbot?start=ref_73848156_8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>DBOX一键买入</b></a>
    '''.format(
        title=item.get("title"),
        mint=item.get("mint"),
        traderPublicKey=item.get("traderPublicKey"),
        amount=float(item.get("amount", 0.0)),
        sol=float(item.get("sol", 0.0)),
        total_balance=float(item.get("total_balance", 0.0)),
        liquidity=float(item.get("liquidity", 0.0)),
        signature=item.get("signature")
    )
    return msg


#老鲸鱼暴击的模版2
def tg_message_html_2(info):
    msg = '''
<b>🐋🐋🐋🐋{title}🐋🐋🐋🐋</b>

<b>token:</b>
<code>{mint}</code>

<b>购买的老钱包:</b>
<code>{traderPublicKey}</code>

<b>购买金额:{amount:.4f} SOL</b>
<b>钱包余额: {balance:.4f} SOL</b>
<b>总盈亏: {total_profit:.4f} USDT</b>
<b>30d盈亏: {realized_profit_30d:.4f} USDT</b>
<b>7d盈亏: {realized_profit_7d:.4f} USDT</b>


<b>链上查看钱包: <a href="https://solscan.io/account/{traderPublicKey}">详情</a></b>
<b>GMGN查看钱包: <a href="https://gmgn.ai/sol/address/{traderPublicKey}">详情</a></b>
<b>交易详情:<a href="https://solscan.io/tx/{signature}">查看</a></b>

📈<b>查看K线: <a href="https://pump.fun/coin/{mint}">PUMP</a></b> <b><a href="https://gmgn.ai/sol/token/{mint}">GMGN</a></b>

<a href="https://t.me/pepeboost_sol_bot?start=8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>PEPE一键买入</b></a>

<a href="https://t.me/sol_dbot?start=ref_73848156_8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>DBOX一键买入</b></a>
    '''.format(
        mint = info.get("mint"),
        title=info.get("title"),
        amount=info.get('amount'),
        signature = info.get('signature'),
        traderPublicKey=info.get("traderPublicKey"),
        balance=float(info.get("balance", 0)),
        total_profit=float(info.get("total_profit", 0)),
        realized_profit_30d=float(info.get("realized_profit_30d", 0)),
        realized_profit_7d=float(info.get("realized_profit_7d", 0)),
    )
    return msg
#老鲸鱼暴击的模版
def tg_message_html_3(info):
    msg = '''
<b>💥💥💥💥{title}💥💥💥💥</b>

<b>token:</b>
<code>{mint}</code>

<b>购买的老钱包:</b>
<code>{traderPublicKey}</code>

<b>购买金额:{amount:.4f} SOL</b>
<b>token市值:{market_cap:.4f} USDT</b>
<b>单币最高盈利:{realized_profit:.4f} USDT</b>
<b>盈利百分比:{realized_pnl:.1f} %</b>
<b>流动性:{liquidity:.1f} USDT</b>

<b>链上查看钱包: <a href="https://solscan.io/account/{traderPublicKey}">详情</a></b>
<b>GMGN查看钱包: <a href="https://gmgn.ai/sol/address/{traderPublicKey}">详情</a></b>
<b>交易详情:<a href="https://solscan.io/tx/{signature}">查看</a></b>

📈<b>查看K线: <a href="https://pump.fun/coin/{mint}">PUMP</a></b> <b><a href="https://gmgn.ai/sol/token/{mint}">GMGN</a></b>

<a href="https://t.me/pepeboost_sol_bot?start=8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>PEPE一键买入</b></a>

<a href="https://t.me/sol_dbot?start=ref_73848156_8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>DBOX一键买入</b></a>
    '''.format(
        mint = info.get("mint"),
        title=info.get("title"),
        amount=float(info.get('amount',0)),
        realized_profit = float(info.get('realized_profit',0)),
        realized_pnl = float(info.get('realized_pnl',0)) * 100,#盈利百分比
        market_cap = float(info.get('market_cap',0)),
        signature = info.get('signature'),
        traderPublicKey=info.get("traderPublicKey"),
        liquidity=float(info.get('liquidity',0)),#流动性
    )
    return msg
#新版15天钱包模板
def tg_message_html_4(info):
    msg = '''
<b>🔥🔥🔥🔥{title}🔥🔥🔥🔥</b>

<b>token:</b>
<code>{mint}</code>

<b>上次记录的钱包:</b>
<code>{traderPublicKeyOld}</code>
<b>本次购买的钱包:</b>
<code>{traderPublicKey}</code>

<b>购买金额:{amount:.4f} SOL</b>
<b>token市值:{market_cap:.4f} USDT</b>
<b>流动性:{liquidity:.4f} USDT</b>


<b>链上查看钱包: <a href="https://solscan.io/account/{traderPublicKey}">详情</a></b>
<b>GMGN查看钱包: <a href="https://gmgn.ai/sol/address/{traderPublicKey}">详情</a></b>
<b>交易详情:<a href="https://solscan.io/tx/{signature}">查看</a></b>

📈<b>查看K线: <a href="https://pump.fun/coin/{mint}">PUMP</a></b> <b><a href="https://gmgn.ai/sol/token/{mint}">GMGN</a></b>

<a href="https://t.me/pepeboost_sol_bot?start=8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>PEPE一键买入</b></a>

<a href="https://t.me/sol_dbot?start=ref_73848156_8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>DBOX一键买入</b></a>
    '''.format(
        mint = info.get("mint"),
        title=info.get("title"),
        amount=float(info.get('amount',0)),
        market_cap = float(info.get('market_cap',0)),
        signature = info.get('signature'),
        traderPublicKey=info.get("traderPublicKey"),
        traderPublicKeyOld = info.get("traderPublicKeyOld","--"),
        liquidity =  float(info.get('liquidity',0)),
    )
    return msg