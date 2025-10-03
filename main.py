# -*- coding: utf-8 -*-
"""
Zepp自动刷步数主程序
支持多账号、Token缓存、自动推送
"""
import math
import traceback
from datetime import datetime
import pytz
import uuid
import json
import random
import time
import os

import requests
from util.aes_help import encrypt_data, decrypt_data, get_aes_key
import util.zepp_helper as zeppHelper


# ==================== 工具函数 ====================

def get_int_value_default(config: dict, key: str, default: int) -> int:
    """获取配置项的整数值，提供默认值"""
    config.setdefault(key, default)
    return int(config.get(key, default))


def get_beijing_time() -> datetime:
    """获取北京时间"""
    target_timezone = pytz.timezone('Asia/Shanghai')
    return datetime.now(target_timezone)


def format_now() -> str:
    """格式化当前时间"""
    return get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")


def get_timestamp() -> str:
    """获取时间戳（毫秒）"""
    current_time = get_beijing_time()
    return "%.0f" % (current_time.timestamp() * 1000)


def fake_ip() -> str:
    """
    生成虚拟IP地址（国内IP段）
    IP段：223.64.0.0 - 223.117.255.255
    添加以39开头的IP地址
    """
    if random.choice([True, False]):
        return f"39.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
    else:
        return f"{223}.{random.randint(64, 117)}.{random.randint(0, 255)}.{random.randint(0, 255)}"


def desensitize_user_name(user: str) -> str:
    """账号脱敏显示"""
    if len(user) <= 8:
        ln = max(math.floor(len(user) / 3), 1)
        return f'{user[:ln]}***{user[-ln:]}'
    return f'{user[:3]}****{user[-4:]}'


def get_min_max_by_time(hour: int = None, minute: int = None) -> tuple:
    """
    根据当前北京时间智能计算步数范围
    - 手动触发：根据时间段就近原则
      - 上午6-12点：9-10点区间，10000-20000步
      - 下午13-18点：15-16点区间，21000-30000步
      - 晚上19-24点：19-19:30区间，31000-35000步
      - 凌晨1-5点：归到上午
    - 自动触发：按照定时任务配置的步数
    """
    if hour is None:
        hour = time_bj.hour
    if minute is None:
        minute = time_bj.minute
    
    # 判断是否手动触发
    is_manual = os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
    
    if is_manual:
        # 手动触发：根据时间段选择步数范围
        if 1 <= hour <= 5:  # 凌晨归到上午
            return 10000, 20000
        elif 6 <= hour <= 12:  # 上午
            return 10000, 20000
        elif 13 <= hour <= 18:  # 下午
            return 21000, 30000
        elif 19 <= hour <= 23 or hour == 0:  # 晚上
            return 31000, 35000
        else:
            return 15000, 25000  # 兜底
    else:
        # 自动触发：根据时间比例计算
        time_rate = min((hour * 60 + minute) / (22 * 60), 1)
        min_step = 18000
        max_step = 30000
        return int(time_rate * min_step), int(time_rate * max_step)


def server_send(msg: str, sckey: str = None):
    """
    Server酱推送（支持Server酱Turbo）
    :param msg: 推送消息
    :param sckey: Server酱密钥
    """
    if sckey is None or sckey == '':
        return
    
    # Server酱Turbo API
    server_url = f"https://sctapi.ftqq.com/{sckey}.send"
    
    data = {
        'title': f'Zepp刷步数通知 - {format_now()}',
        'desp': msg
    }
    
    try:
        response = requests.post(server_url, data=data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            print(f"[成功] Server酱推送成功: {result.get('message', '已推送')}")
        else:
            print(f"[失败] Server酱推送失败: HTTP {response.status_code}")
    except Exception as e:
        print(f"[异常] Server酱推送异常: {str(e)}")


# ==================== Token管理 ====================

def prepare_user_tokens() -> dict:
    """从加密文件加载Token缓存"""
    data_path = "encrypted_tokens.data"
    
    if not os.path.exists(data_path):
        return {}
    
    try:
        with open(data_path, 'rb') as f:
            encrypted_data = f.read()
        
        decrypted_data = decrypt_data(encrypted_data, get_aes_key(), None)
        return json.loads(decrypted_data.decode('utf-8', errors='strict'))
    except Exception as e:
        print(f"[警告] Token解密失败（密钥错误或文件损坏）: {str(e)}")
        return {}


def persist_user_tokens(user_tokens: dict):
    """保存Token到加密文件"""
    data_path = "encrypted_tokens.data"
    
    try:
        origin_str = json.dumps(user_tokens, ensure_ascii=False)
        encrypted_data = encrypt_data(origin_str.encode("utf-8"), get_aes_key(), None)
        
        with open(data_path, 'wb') as f:
            f.write(encrypted_data)
        
        print("[成功] Token已加密保存")
    except Exception as e:
        print(f"[失败] Token保存失败: {str(e)}")


# ==================== 核心业务类 ====================

class ZeppStepRunner:
    """Zepp刷步数执行器"""
    
    def __init__(self, user: str, password: str, user_tokens: dict):
        self.user_id = None
        self.device_id = str(uuid.uuid4())
        self.invalid = False
        self.log_str = ""
        self.user_tokens = user_tokens
        
        # 参数校验
        user = str(user).strip()
        password = str(password).strip()
        
        if not user or not password:
            self.error = "[失败] 用户名或密码为空"
            self.invalid = True
            return
        
        self.password = password
        
        # 处理用户名格式
        if not (user.startswith("+86") or "@" in user):
            user = "+86" + user
        
        self.is_phone = user.startswith("+86")
        self.user = user
        
        # 生成虚拟IP
        self.fake_ip_addr = fake_ip()
        self.log_str += f"[虚拟IP] {self.fake_ip_addr}\n"
    
    def login(self) -> str:
        """
        登录并获取app_token
        支持三级Token缓存：access_token -> login_token -> app_token
        """
        user_token_info = self.user_tokens.get(self.user)
        
        # 尝试使用缓存的Token
        if user_token_info:
            access_token = user_token_info.get("access_token")
            login_token = user_token_info.get("login_token")
            app_token = user_token_info.get("app_token")
            self.device_id = user_token_info.get("device_id", self.device_id)
            self.user_id = user_token_info.get("user_id")
            
            # 检查app_token是否有效
            ok, msg = zeppHelper.check_app_token(app_token)
            if ok:
                self.log_str += "[成功] 使用缓存的app_token\n"
                return app_token
            
            self.log_str += f"[警告] app_token已失效，尝试刷新...\n"
            
            # 尝试用login_token刷新app_token
            app_token, msg = zeppHelper.grant_app_token(login_token)
            if app_token:
                user_token_info["app_token"] = app_token
                user_token_info["app_token_time"] = get_timestamp()
                self.log_str += "[成功] app_token刷新成功\n"
                return app_token
            
            self.log_str += f"[警告] login_token已失效，重新登录...\n"
        
        # Token全部失效，重新登录
        access_token, msg = zeppHelper.login_access_token(self.user, self.password)
        if not access_token:
            self.log_str += f"[失败] 登录失败: {msg}\n"
            return None
        
        login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(
            access_token, self.device_id, self.is_phone
        )
        
        if not login_token:
            self.log_str += f"[失败] Token获取失败: {msg}\n"
            return None
        
        # 保存Token
        current_time = get_timestamp()
        self.user_tokens[self.user] = {
            "access_token": access_token,
            "login_token": login_token,
            "app_token": app_token,
            "user_id": user_id,
            "device_id": self.device_id,
            "access_token_time": current_time,
            "login_token_time": current_time,
            "app_token_time": current_time
        }
        
        self.user_id = user_id
        self.log_str += "[成功] 登录成功，Token已缓存\n"
        return app_token
    
    def execute(self, min_step: int, max_step: int) -> tuple:
        """
        执行刷步数
        :return: (message, success)
        """
        if self.invalid:
            return "[失败] 账号配置无效", False
        
        # 登录
        app_token = self.login()
        if not app_token:
            return "[失败] 登录失败", False
        
        # 生成随机步数
        step = random.randint(min_step, max_step)
        self.log_str += f"[随机步数] 范围: {min_step}~{max_step}，生成步数: {step}\n"
        
        # 提交步数
        ok, msg = zeppHelper.post_fake_brand_data(step, app_token, self.user_id)
        
        result_msg = f"[{'成功' if ok else '失败'}] {msg}"
        return result_msg, ok


# ==================== 主执行函数 ====================

def run_single_account(total: int, idx: int, user: str, password: str, 
                      min_step: int, max_step: int, user_tokens: dict) -> dict:
    """
    执行单个账号的刷步数任务
    :param total: 总账号数
    :param idx: 当前索引
    :param user: 用户名
    :param password: 密码
    :param min_step: 最小步数
    :param max_step: 最大步数
    :param user_tokens: Token缓存字典
    :return: 执行结果字典
    """
    idx_info = f"[{idx + 1}/{total}]"
    log_str = f"\n{'='*60}\n"
    log_str += f"[时间] {format_now()}\n"
    log_str += f"{idx_info} 账号: {desensitize_user_name(user)}\n"
    log_str += f"{'='*60}\n"
    
    try:
        runner = ZeppStepRunner(user, password, user_tokens)
        exec_msg, success = runner.execute(min_step, max_step)
        
        log_str += runner.log_str
        log_str += f"{exec_msg}\n"
        
        exec_result = {
            "user": desensitize_user_name(user),
            "success": success,
            "msg": exec_msg,
            "step": None  # 可以从runner中获取实际步数
        }
    except Exception as e:
        error_msg = f"[异常] {traceback.format_exc()}"
        log_str += error_msg
        
        exec_result = {
            "user": desensitize_user_name(user),
            "success": False,
            "msg": f"执行异常: {str(e)}"
        }
    
    print(log_str)
    return exec_result


def execute_all_accounts(users: str, passwords: str, min_step: int, max_step: int,
                        user_tokens: dict, use_concurrent: bool = False, 
                        sleep_seconds: float = 5.0) -> list:
    """
    执行所有账号的刷步数任务
    :param users: 用户名列表（用#分隔）
    :param passwords: 密码列表（用#分隔）
    :param min_step: 最小步数
    :param max_step: 最大步数
    :param user_tokens: Token缓存字典
    :param use_concurrent: 是否并发执行
    :param sleep_seconds: 账号间隔时间（秒）
    :return: 执行结果列表
    """
    user_list = users.split('#')
    passwd_list = passwords.split('#')
    
    if len(user_list) != len(passwd_list):
        print(f"[错误] 账号数[{len(user_list)}]和密码数[{len(passwd_list)}]不匹配")
        return []
    
    total = len(user_list)
    exec_results = []
    
    if use_concurrent:
        # 并发执行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(run_single_account, total, idx, user, passwd, 
                              min_step, max_step, user_tokens)
                for idx, (user, passwd) in enumerate(zip(user_list, passwd_list))
            ]
            exec_results = [future.result() for future in futures]
    else:
        # 串行执行
        for idx, (user, passwd) in enumerate(zip(user_list, passwd_list)):
            result = run_single_account(total, idx, user, passwd, min_step, max_step, user_tokens)
            exec_results.append(result)
            
            # 账号间隔
            if idx < total - 1:
                time.sleep(sleep_seconds)
    
    return exec_results


def push_notification(exec_results: list, sckey: str = None):
    """
    推送执行结果通知
    :param exec_results: 执行结果列表
    :param sckey: Server酱密钥
    """
    if not sckey or sckey == 'NO':
        return
    
    total = len(exec_results)
    success_count = sum(1 for r in exec_results if r.get('success'))
    fail_count = total - success_count
    
    # 构建推送消息
    msg = f"### 执行摘要\n\n"
    msg += f"- 总账号数: {total}\n"
    msg += f"- 成功: {success_count}\n"
    msg += f"- 失败: {fail_count}\n\n"
    msg += f"---\n\n"
    msg += f"### 详细结果\n\n"
    
    for idx, result in enumerate(exec_results, 1):
        user = result.get('user', '未知')
        success = result.get('success', False)
        res_msg = result.get('msg', '无信息')
        
        status = "[成功]" if success else "[失败]"
        msg += f"{idx}. {status} 账号: {user}\n   {res_msg}\n\n"
    
    server_send(msg, sckey)


# ==================== 主入口 ====================

def main():
    """主函数"""
    global time_bj
    time_bj = get_beijing_time()
    
    print(f"\n{'='*60}")
    print(f"Zepp自动刷步数程序")
    print(f"执行时间: {format_now()}")
    print(f"{'='*60}\n")
    
    # 检查配置
    if 'CONFIG' not in os.environ:
        print("[错误] 未配置CONFIG环境变量")
        return
    
    try:
        config = json.loads(os.environ.get('CONFIG', '{}'))
    except json.JSONDecodeError:
        print("[错误] CONFIG格式不正确，请检查JSON格式")
        traceback.print_exc()
        return
    
    # 获取配置参数
    users = config.get('USER', '')
    passwords = config.get('PWD', '')
    sckey = config.get('SCKEY', '')
    use_concurrent = config.get('USE_CONCURRENT', 'False') == 'True'
    sleep_seconds = float(config.get('SLEEP_GAP', 5))
    
    if not users or not passwords:
        print("[错误] 未正确配置账号密码")
        return
    
    # 加载Token缓存
    user_tokens = {}
    aes_key = get_aes_key()
    if aes_key:
        user_tokens = prepare_user_tokens()
        print(f"[信息] 已加载 {len(user_tokens)} 个账号的Token缓存")
    else:
        print("[警告] 未设置AES_KEY，无法使用Token缓存功能")
    
    # 计算步数范围
    min_step, max_step = get_min_max_by_time()
    print(f"[信息] 步数范围: {min_step} ~ {max_step}")
    print(f"[信息] 执行模式: {'并发' if use_concurrent else '串行'}")
    if not use_concurrent:
        print(f"[信息] 账号间隔: {sleep_seconds}秒")
    print()
    
    # 执行刷步数
    exec_results = execute_all_accounts(
        users, passwords, min_step, max_step, 
        user_tokens, use_concurrent, sleep_seconds
    )
    
    # 保存Token
    if aes_key:
        persist_user_tokens(user_tokens)
    
    # 统计结果
    total = len(exec_results)
    success_count = sum(1 for r in exec_results if r.get('success'))
    
    print(f"\n{'='*60}")
    print(f"执行完成")
    print(f"总账号数: {total}, 成功: {success_count}, 失败: {total - success_count}")
    print(f"{'='*60}\n")
    
    # 推送通知
    push_notification(exec_results, sckey)


if __name__ == "__main__":
    main()
