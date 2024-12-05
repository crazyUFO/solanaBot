from portfolivalueCalculator import PortfolioValueCalculator
# 示例用法：
if __name__ == "__main__":
    # 使用 API 密钥和账户地址初始化 PortfolioValueCalculator
    portfolio_calculator = PortfolioValueCalculator(
        balances_api_key="c3b599f9-2a66-494c-87da-1ac92d734bd8",
        account_address="LFcThvX8J558bJ6UYUqTGRRtXirwBHvFscV1kTu8sfo"
    )
    
    # 计算投资组合的总价值
    total_value = portfolio_calculator.calculate_total_value()
    sol = portfolio_calculator.get_sol()
    
    # 输出结果
    print(f"总投资组合价值: {total_value:.4f}")
    print(f"总投资组合价值: {sol:.4f}")
