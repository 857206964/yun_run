#!/usr/bin/env python3
"""
Zepp/华米运动刷步数工具
支持多账户、Token持久化、AES加密存储
"""

import os
import sys
import json
import random
import hashlib
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# 导入AES加密工具
try:
    from util.aes_help import encrypt_data, decrypt_data, HM_AES_KEY, HM_AES_IV
except ImportError:
    print("❌ 错误：找不到 util/aes_help.py，请确保文件存在")
    sys.exit(1)

# ==================== 配置部分 ====================

# API端点配置
API_BASE = "https://api-mifit-cn2.huami.com"
LOGIN_URL = f"{API_BASE}/users/login.json"
STEP_URL = f"{API_BASE}/v1/data/band_data.json"

# 固定应用参数（从华米APP逆向获取）
APP_VERSION = "5.9.2-play_100355"
DEVICE_ID = "02:00:00:00:00:00"
DEVICE_MODEL = "Android Phone"

# 环境变量配置
ZEPP_ACCOUNT = os.getenv("ZEPP_ACCOUNT", "")
ZEPP_PASSWORD = os.getenv("ZEPP_PASSWORD", "")
AES_KEY = os.getenv("AES_KEY", "")  # 用户自定义AES密钥

# 步数范围配置
STEP_MIN = int(os.getenv("STEP_MIN", "8000"))
STEP_MAX = int(os.getenv("STEP_MAX", "15000"))

# Token缓存文件
TOKEN_CACHE_FILE = Path("encrypted_tokens.data")

# ==================== 工具函数 ====================

def log(level: str, message: str):
    """格式化日志输出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    emoji = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️"}.get(level, "📝")
    print(f"{emoji} [{timestamp}] [{level}] {message}")

def validate_env():
    """验证必需的环境变量"""
    missing = []
    if not ZEPP_ACCOUNT:
        missing.append("ZEPP_ACCOUNT")
    if not ZEPP_PASSWORD:
        missing.append("ZEPP_PASSWORD")
    if not AES_KEY or len(AES_KEY.encode()) != 16:
        missing.append("AES_KEY (必须是16字节)")
    
    if missing:
        log("ERROR", f"缺少必需的环境变量: {', '.join(missing)}")
        sys.exit(1)

def generate_app_token(account: str) -> str:
    """生成应用Token（MD5哈希）"""
    raw = f"app_version={APP_VERSION}&device_id={DEVICE_ID}&device_model={DEVICE_MODEL}&email={account}"
    return hashlib.md5(raw.encode()).hexdigest()

# ==================== Token管理 ====================

def save_encrypted_tokens(tokens: Dict[str, Any], aes_key: bytes):
    """加密保存Token到本地"""
    try:
        json_str = json.dumps(tokens, ensure_ascii=False)
        encrypted = encrypt_data(json_str.encode('utf-8'), aes_key, iv=None)
        TOKEN_CACHE_FILE.write_bytes(encrypted)
        log("SUCCESS", f"Token已加密保存到 {TOKEN_CACHE_FILE}")
    except Exception as e:
        log("ERROR", f"保存Token失败: {e}")

def load_encrypted_tokens(aes_key: bytes) -> Optional[Dict[str, Any]]:
    """从本地解密读取Token"""
    if not TOKEN_CACHE_FILE.exists():
        log("INFO", "未找到Token缓存文件，将重新登录")
        return None
    
    try:
        encrypted_data = TOKEN_CACHE_FILE.read_bytes()
        decrypted = decrypt_data(encrypted_data, aes_key, iv=None)
        tokens = json.loads(decrypted.decode('utf-8'))
        log("SUCCESS", f"成功加载 {len(tokens)} 个账户的Token缓存")
        return tokens
    except Exception as e:
        log("WARNING", f"解密Token失败（可能密钥错误），将重新登录: {e}")
        return None

# ==================== 登录功能 ====================

def login(account: str, password: str) -> Optional[str]:
    """
    登录华米账户
    返回：user_token 或 None
    """
    log("INFO", f"正在登录账户: {account}")
    
    # 生成登录参数
    app_token = generate_app_token(account)
    pwd_hash = hashlib.md5(password.encode()).hexdigest()
    
    login_data = {
        "app_version": APP_VERSION,
        "device_id": DEVICE_ID,
        "device_model": DEVICE_MODEL,
        "email": account,
        "password": pwd_hash,
        "app_token": app_token
    }
    
    try:
        response = requests.post(LOGIN_URL, data=login_data, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            user_token = result["token_info"]["user_token"]
            log("SUCCESS", f"登录成功! Token: {user_token[:20]}...")
            return user_token
        else:
            log("ERROR", f"登录失败: {result.get('errors', 'Unknown error')}")
            return None
            
    except requests.RequestException as e:
        log("ERROR", f"网络请求失败: {e}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        log("ERROR", f"响应解析失败: {e}")
        return None

# ==================== 刷步数功能 ====================

def update_steps(user_token: str, steps: int) -> bool:
    """
    更新步数
    返回：是否成功
    """
    log("INFO", f"正在更新步数: {steps}")
    
    # 构造请求数据（使用华米协议加密）
    today = datetime.now().strftime("%Y-%m-%d")
    data_json = {
        "data_json": f'{{"step":{steps},"date":"{today}"}}'
    }
    
    # 加密数据（使用华米固定密钥）
    encrypted_data = encrypt_data(
        json.dumps(data_json).encode('utf-8'),
        HM_AES_KEY,
        HM_AES_IV
    )
    
    headers = {
        "User-Agent": f"MiFit/{APP_VERSION}",
        "Content-Type": "application/x-www-form-urlencoded",
        "apptoken": user_token
    }
    
    try:
        response = requests.post(
            STEP_URL,
            data={"data": encrypted_data.hex()},
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            log("SUCCESS", f"✨ 步数更新成功: {steps} 步")
            return True
        else:
            log("ERROR", f"更新步数失败: {result.get('errors', 'Unknown error')}")
            return False
            
    except requests.RequestException as e:
        log("ERROR", f"网络请求失败: {e}")
        return False
    except Exception as e:
        log("ERROR", f"未知错误: {e}")
        return False

# ==================== 主流程 ====================

def main():
    """主程序入口"""
    log("INFO", "=== Zepp刷步数工具启动 ===")
    
    # 验证环境变量
    validate_env()
    
    # 准备AES密钥
    aes_key = AES_KEY.encode('utf-8')
    
    # 尝试加载Token缓存
    user_tokens = load_encrypted_tokens(aes_key) or {}
    
    # 解析账户列表（支持多账户，逗号分隔）
    accounts = [acc.strip() for acc in ZEPP_ACCOUNT.split(',') if acc.strip()]
    
    if not accounts:
        log("ERROR", "未配置任何账户")
        sys.exit(1)
    
    log("INFO", f"检测到 {len(accounts)} 个账户")
    
    # 处理每个账户
    success_count = 0
    for account in accounts:
        log("INFO", f"\n--- 处理账户: {account} ---")
        
        # 获取Token（优先使用缓存）
        user_token = user_tokens.get(account)
        if not user_token:
            user_token = login(account, ZEPP_PASSWORD)
            if user_token:
                user_tokens[account] = user_token
                save_encrypted_tokens(user_tokens, aes_key)
        else:
            log("INFO", "使用缓存的Token")
        
        if not user_token:
            log("ERROR", f"账户 {account} 登录失败，跳过")
            continue
        
        # 生成随机步数
        random_steps = random.randint(STEP_MIN, STEP_MAX)
        
        # 更新步数
        if update_steps(user_token, random_steps):
            success_count += 1
        else:
            # 如果失败，可能Token过期，尝试重新登录
            log("WARNING", "可能Token已过期，尝试重新登录...")
            user_token = login(account, ZEPP_PASSWORD)
            if user_token:
                user_tokens[account] = user_token
                save_encrypted_tokens(user_tokens, aes_key)
                if update_steps(user_token, random_steps):
                    success_count += 1
    
    # 输出结果
    log("INFO", "\n=== 执行完成 ===")
    log("SUCCESS" if success_count > 0 else "WARNING", 
        f"成功: {success_count}/{len(accounts)} 个账户")
    
    sys.exit(0 if success_count > 0 else 1)

if __name__ == "__main__":
    main()
