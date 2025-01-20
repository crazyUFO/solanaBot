import tls_client

class gmgn:
    BASE_URL = "https://gmgn.ai/defi/quotation"

    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control":"no-cache",
            "cookie": "__cf_bm=6VsuJDimD8zNOIqFFGpD61zR9dNfPL1_qy3CEpSesK8-1737391588-1.0.1.1-ug6pZFbAUM5LU1aYj5kh3dCH0C1RBi9P0FhjafECTlrUQlF3lbn._C4yscO9m9yJhuuZUk4SwTrjPhKULdtpvw; _ga=GA1.1.1405690339.1737391590; cf_clearance=5Vjo7Evg5gQxV80g3qyeFM1G3qPYRyUWHY4VlNqhx6U-1737391592-1.2.1.1-JrJVR13tTAHDObkIC.YSEFUnboHE_L97Vj0DQXwCoSRohJ99PLZyxK7SyEdxKusDEwHbLgZ5hP11KmtDi2lrYbjRghHHkxa7nQHQtQ_63a7kdrPMkc_WHNhhh5pwF4VTtxht5P.04KEzAsripDWnfgROId5rJnXV82uNdRuB3KlOwEjbn_0qR7RXJBSEtXrKNd7n0wqjD85Mrk5JMNPiGmwKX2kHs3IzEZrj0sb_rQ7xVjVVC41_RY03IL0NKFVxwTxMoTKjz2Xk5OKvbR7xoIdpENbUwUzvFZ37upM1jrs; _ga_0XM0LYXGC8=GS1.1.1737391589.1.1.1737391656.0.0.0",
            "pragma":"no-cache",
            "priority":"u=1, i",
            "referer":"https://gmgn.ai/trade/VqNpWUdf?chain=sol",
            "sec-ch-ua": "\"Not_A Brand\";v=\"99\", \"Google Chrome\";v=\"109\", \"Chromium\";v=\"109\"",
            "sec-ch-ua-arch":'"x86"',
            "sec-ch-ua-bitness":'"64"',
            "sec-ch-ua-full-version":'"131.0.6778.86"',
            "sec-ch-ua-full-version-list":'"Google Chrome";v="131.0.6778.86", "Chromium";v="131.0.6778.86", "Not_A Brand";v="24.0.0.0"',
            "sec-ch-ua-mobile":"?0",
            "sec-ch-ua-model":"",
            "sec-ch-ua-platform":'"Windows"',
            "sec-ch-ua-platform-version":'"10.0.0"',
            "sec-fetch-dest":"empty",
            "sec-fetch-mode":"cors",
            "sec-fetch-site":"same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
        }

        self.session = tls_client.Session(client_identifier="chrome_103")

    def getTokenInfo(self, contractAddress: str) -> dict:
        """
        Gets info on a token.
        """
        if not contractAddress:
            return "You must input a contract address."
        url = f"{self.BASE_URL}/v1/tokens/sol/{contractAddress}"

        request = self.session.get(url, headers=self.headers)
        print(request)
        jsonResponse = request.json()['data']['token']

        return jsonResponse
    
    def getNewPairs(self, limit: int = None) -> dict:
        """
        Limit - Limits how many tokens are in the response.
        """
        if not limit:
            limit = 50
        elif limit > 50:
            return "You cannot have more than check more than 50 pairs."
        
        url = f"{self.BASE_URL}/v1/pairs/sol/new_pairs?limit={limit}&orderby=open_timestamp&direction=desc&filters[]=not_honeypot"

        request = self.session.get(url, headers=self.headers)

        jsonResponse = request.json()['data']

        return jsonResponse
    
    def getTrendingWallets(self, timeframe: str = None, walletTag: str = None) -> dict:
        """
        Gets a list of trending wallets based on a timeframe and a wallet tag.

        Timeframes\n
        1d = 1 Day\n
        7d = 7 Days\n
        30d = 30 days\n

        ----------------

        Wallet Tags\n
        pump_smart = Pump.Fun Smart Money\n
        smart_degen = Smart Money\n
        reowned = KOL/VC/Influencer\n
        snipe_bot = Snipe Bot\n

        """
        if not timeframe:
            timeframe = "7d"
        if not walletTag:
            walletTag = "smart_degen"
        
        url = f"{self.BASE_URL}/v1/rank/sol/wallets/{timeframe}?tag={walletTag}&orderby=pnl_{timeframe}&direction=desc"

        request = self.session.get(url, headers=self.headers)

        jsonResponse = request.json()['data']

        return jsonResponse
    
    def getTrendingTokens(self, timeframe: str = None) -> dict:
        """
        Gets a list of trending tokens based on a timeframe.

        Timeframes\n
        1m = 1 Minute\n
        5m = 5 Minutes\n
        1h = 1 Hour\n
        6h = 6 Hours\n
        24h = 24 Hours\n
        """
        timeframes = ["1m", "5m", "1h", "6h", "24h"]
        if timeframe not in timeframes:
            return "Not a valid timeframe."

        if not timeframe:
            timeframe = "1h"

        if timeframe == "1m":
            url = f"{self.BASE_URL}/v1/rank/sol/swaps/{timeframe}?orderby=swaps&direction=desc&limit=20"
        else:
            url = f"{self.BASE_URL}/v1/rank/sol/swaps/{timeframe}?orderby=swaps&direction=desc"
        
        request = self.session.get(url, headers=self.headers)

        jsonResponse = request.json()['data']

        return jsonResponse

    def getTokensByCompletion(self, limit: int = None) -> dict:
        """
        Gets tokens by their bonding curve completion progress.\n

        Limit - Limits how many tokens in the response.
        """

        if not limit:
            limit = 50
        elif limit > 50:
            return "Limit cannot be above 50."

        url = f"{self.BASE_URL}/v1/rank/sol/pump?limit={limit}&orderby=progress&direction=desc&pump=true"

        request = self.session.get(url, headers=self.headers)

        jsonResponse = request.json()['data']

        return jsonResponse
    
    def findSnipedTokens(self, size: int = None) -> dict:
        """
        Gets a list of tokens that have been sniped.\n

        Size - The amount of tokens in the response
        """

        if not size:
            size = 10
        elif size > 39:
            return "Size cannot be more than 39"
        
        url = f"{self.BASE_URL}/v1/signals/sol/snipe_new?size={size}&is_show_alert=false&featured=false"

        request = self.session.get(url, headers=self.headers)

        jsonResponse = request.json()['data']

        return jsonResponse
    
    def getGasFee(self):
        """
        Get the current gas fee price.
        """
        url = f"{self.BASE_URL}/v1/chains/sol/gas_price"

        request = self.session.get(url, headers=self.headers)

        jsonResponse = request.json()['data']

        return jsonResponse
    
    def getTokenUsdPrice(self, contractAddress: str = None) -> dict:
        """
        Get the realtime USD price of the token.
        """
        if not contractAddress:
            return "You must input a contract address."
        
        url = f"{self.BASE_URL}/v1/sol/tokens/realtime_token_price?address={contractAddress}"

        request = self.session.get(url, headers=self.headers)

        jsonResponse = request.json()['data']

        return jsonResponse

    def getTopBuyers(self, contractAddress: str = None) -> dict:
        """
        Get the top buyers of a token.
        """
        if not contractAddress:
            return "You must input a contract address."
        
        url = f"{self.BASE_URL}/v1/tokens/top_buyers/sol/{contractAddress}"

        request = self.session.get(url, headers=self.headers)

        jsonResponse = request.json()['data']

        return jsonResponse

    def getSecurityInfo(self, contractAddress: str = None) -> dict:
        """
        Gets security info about the token.
        """
        if not contractAddress:
            return "You must input a contract address."
        
        url = f"{self.BASE_URL}/v1/tokens/security/sol/{contractAddress}"

        request = self.session.get(url, headers=self.headers)

        jsonResponse = request.json()['data']

        return jsonResponse
    
    def getWalletInfo(self, walletAddress: str = None, period: str = None,proxies:dict = None) -> dict:
        """
        Gets various information about a wallet address.

        Period - 7d, 30d - The timeframe of the wallet you're checking.
        """

        periods = ["7d", "30d"]

        if not walletAddress:
            return "You must input a wallet address."
        if not period or period not in periods:
            period = "7d"
        
        url = f"{self.BASE_URL}/v1/smartmoney/sol/walletNew/{walletAddress}?period={period}"
        # 设置代理
        proxies = proxies
        return self.session.get(url, headers=self.headers,proxy=proxies)
    
    def getWalletActivity(self, walletAddress: str = None, type: str = None,proxies:dict = None) -> dict:
        """
        Gets various information about a wallet address.

        types - buy, sell - The Activitys of the wallet you're checking.
        """

        types = ["buy", "sell"]

        if not walletAddress:
            return "You must input a wallet address."
        if not type or type not in types:
            type = "buy"
        
        url = f"{self.BASE_URL}/v1/wallet_activity/sol?type={type}&wallet={walletAddress}&limit=100"
        # 设置代理
        proxies = proxies
        return self.session.get(url, headers=self.headers,proxy=proxies)
    
    
    def getWalletHoldings(self, walletAddress: str = None, params: str = None,proxies:dict = None) -> dict:
        """
        获取GMGN上 一个钱包历史的代币持仓情况，
        """
        url = "https://gmgn.ai/api"
        if not walletAddress:
            return "You must input a wallet address."
        if not params:
            return "You must input a params"
        
        url = f"{url}/v1/wallet_holdings/sol/{walletAddress}?{params}"
        # 设置代理
        proxies = proxies
        return self.session.get(url, headers=self.headers,proxy=proxies)
    
    def get_gas_price_sol(self,proxies:dict = None) -> dict:
        """
        获取GMGN上 SOL的美元的单价
        """
        url = "https://gmgn.ai/api/v1/gas_price/sol"
        # 设置代理
        proxies = proxies
        return self.session.get(url, headers=self.headers,proxy=proxies)
    
    def getTokenTrades(self, token: str = None, params: str = None,proxies:dict = None) -> dict:
        """
        获取一个token的购买者列表
        """
        if not token:
            return "You must input a token address."
        
        url = f"{self.BASE_URL}/v1/trades/sol/{token}?{params}"
        # 设置代理
        proxies = proxies
        return self.session.get(url, headers=self.headers,proxy=proxies)
    
    def getTokenPoolInfo(self,token: str = None,proxies:dict = None) -> dict:
        """
        获取GMGN上 代币流动性的详情
        """
        if not token:
            return "You must input a token address."
        url = f"https://gmgn.ai/api/v1/token_pool_info_sol/sol/{token}"
        # 设置代理
        proxies = proxies
        return self.session.get(url, headers=self.headers,proxy=proxies)
    
    def getTokenTopHolders(self,token: str = None, params: str = None,proxies:dict = None) -> dict:
        """
        获取GMGN上一个token的交易top持仓数据
        """
        if not token:
            return "You must input a token address."
        if not params:
            return "You must input a params."
        url = f"https://gmgn.ai/api/v1/tokens/top_holders/sol/{token}?{params}"
        
        # 设置代理
        proxies = proxies
        return self.session.get(url, headers=self.headers,proxy=proxies)
    
    def getKline(self,token:str= None,type:str= 'kline',params:str=None,proxies:dict = None)->dict:
        '''
            获取市场行情数据
            type: kline mcapkline
            params : resolution=1s&from=1737116995&to=1737203395
        '''
        if not token:
            return "You must input a token address."
        if not params:
            return "You must input a params."
        url = f"https://www.gmgn.cc/defi/quotation/v1/tokens/{type}/sol/{token}?{params}"
        return self.session.get(url, headers=self.headers,proxy=proxies)