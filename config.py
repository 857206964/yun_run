class Config:
    """配置类"""
    
    # API地址
    BASE_URL = "https://your-api-domain.com"
    LOGIN_URL = f"{BASE_URL}/api/login"
    STEP_URL = f"{BASE_URL}/api/step/update"
    
    # 其他配置
    TIMEOUT = 10
    RETRY_TIMES = 3
    
    # 步数范围配置
    STEP_RANGES = {
        'morning': (1000, 10000),      # 上午
        'afternoon': (15000, 25000),   # 下午
        'evening': (30000, 40000)      # 晚上
    }
