# -*- coding: utf-8 -*-
"""
Zepp自动刷步数主程序
支持多账号、Token缓存、自动推送、错误重试
直接读取环境变量
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
import sys
from typing import Optional, Tuple, Dict, List

import requests
from util.aes_help import encrypt_data, decrypt_data, get_aes_key
import util.zepp_helper as zeppHelper


# ==================== 全局配置 ====================

class Config:
    """全局配置类"""
    TOKEN_FILE = "encrypted_tokens.data"
    DEFAULT_MIN_STEP = 15000
    DEFAULT_MAX_STEP = 25000
    DEFAULT_SLEEP_GAP = 5.0
    REQUEST_TIMEOUT = 30
    MAX_RETRY = 3
    RETRY_DELAY = 2
    
    # 时间段步数配置（手动触发）
    MANUAL_STEP_RANGES = {
        'morning': (10000, 20000),    # 6-12点
        'afternoon': (21000, 30000),  # 13-18点
        'evening': (31000, 35000),    # 19-24点
        'night': (10000, 20000)       # 1-5点
    }


# ==================== 工具函数 ====================

def get_int_value_default(value: str, default: int) -> int:
    """获取环境变量的整数值，提供默认值"""
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        print(f"[警告] 值 {value} 无效，使用默认值: {default}")
        return default


def get_float_value_default(value: str, default: float) -> float:
    """获取环境变量的浮点值，提供默认值"""
    try:
        return float(value) if value else default
    except (ValueError, TypeError):
        print(f"[警告] 值 {value} 无效，使用默认值: {default}")
        return default


def get_bool_value_default(value: str, default: bool) -> bool:
    """获取环境变量的布尔值，提供默认值"""
    if not value:
        return default
    return value.upper() in ('TRUE', '1', 'YES', 'ON')


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
    IP段：223.64.0.0 - 223.117.255.255 或 39.0.0.0 - 39.255.255.255
    加入39移动网段
    """
    if random.choice([True, False]):
        return f"39.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
    else:
        return f"223.{random.randint(64, 117)}.{random.randint(0, 255)}.{random.randint(0, 255)}"


def desensitize_user_name(user: str) -> str:
    """账号脱敏显示"""
    if not user:
        return "***"
    if len(user) <= 8:
        ln = max(math.floor(len(user) / 3), 1)
        return f'{user[:ln]}***{user[-ln:]}'
    return f'{user[:3]}****{user[-4:]}'


def is_manual_trigger() -> bool:
    """判断是否为手动触发"""
    return os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'


def get_min_max_by_time(hour: int = None, minute: int = None) -> Tuple[int, int]:
    """
    根据当前北京时间智能计算步数范围
    
    手动触发模式：
    - 凌晨1-5点  -> 10000-20000步（归到上午）
    - 上午6-12点 -> 10000-20000步
    - 下午13-18点-> 21000-30000步
    - 晚上19-24点-> 31000-35000步
    
    自动触发模式：
    - 根据时间比例线性计算
    """
    if hour is None:
        hour = get_beijing_time().hour
    if minute is None:
        minute = get_beijing_time().minute
    
    if is_manual_trigger():
        # 手动触发：根据时间段选择
        if 1 <= hour <= 5:
            return Config.MANUAL_STEP_RANGES['night']
        elif 6 <= hour <= 12:
            return Config.MANUAL_STEP_RANGES['morning']
        elif 13 <= hour <= 18:
            return Config.MANUAL_STEP_RANGES['afternoon']
        elif 19 <= hour <= 23 or hour == 0:
            return Config.MANUAL_STEP_RANGES['evening']
        else:
            return Config.DEFAULT_MIN_STEP, Config.DEFAULT_MAX_STEP
    else:
        # 自动触发：线性计算
        time_rate = min((hour * 60 + minute) / (22 * 60), 1)
        min_step = int(time_rate * 18000)
        max_step = int(time_rate * 30000)
        return max(min_step, 5000), max(max_step, 10000)


def server_send(msg: str, sckey: str = None):
    """
    Server酱推送（支持Server酱Turbo）
    :param msg: 推送消息
    :param sckey: Server酱密钥
    """
    if not sckey or sckey.upper() == 'NO':
        return
    
    server_url = f"https://sctapi.ftqq.com/{sckey}.send"
    
    data = {
        'title': f'Zepp刷步数通知 - {format_now()}',
        'desp': msg
    }
    
    try:
        response = requests.post(server_url, data=data, timeout=Config.REQUEST_TIMEOUT)
        if response.status_code == 200:
            result = response.json()
            if result.get('code') == 0:
                print(f"[成功] Server酱推送成功")
            else:
                print(f"[失败] Server酱推送失败: {result.get('message', '未知错误')}")
        else:
            print(f"[失败] Server酱推送失败: HTTP {response.status_code}")
    except requests.exceptions.Timeout:
        print(f"[超时] Server酱推送超时")
    except Exception as e:
        print(f"[异常] Server酱推送异常: {str(e)}")


# ==================== Token管理 ====================

def prepare_user_tokens() -> Dict:
    """从加密文件加载Token缓存"""
    if not os.path.exists(Config.TOKEN_FILE):
        print(f"[信息] Token缓存文件不存在，将创建新文件")
        return {}
    
    try:
        with open(Config.TOKEN_FILE, 'rb') as f:
            encrypted_data = f.read()
        
        if not encrypted_data:
            print(f"[警告] Token缓存文件为空")
            return {}
        
        decrypted_data = decrypt_data(encrypted_data, get_aes_key(), None)
        tokens = json.loads(decrypted_data.decode('utf-8', errors='strict'))
        
        print(f"[成功] 已加载 {len(tokens)} 个账号的Token缓存")
        return tokens
    except json.JSONDecodeError as e:
        print(f"[错误] Token文件JSON解析失败: {str(e)}")
        return {}
    except Exception as e:
        print(f"[警告] Token解密失败（可能是密钥错误）: {str(e)}")
        return {}


def persist_user_tokens(user_tokens: Dict) -> bool:
    """
    保存Token到加密文件
    :return: 是否保存成功
    """
    try:
        origin_str = json.dumps(user_tokens, ensure_ascii=False, indent=2)
        encrypted_data = encrypt_data(origin_str.encode("utf-8"), get_aes_key(), None)
        
        with open(Config.TOKEN_FILE, 'wb') as f:
            f.write(encrypted_data)
        
        print(f"[成功] Token已加密保存（{len(user_tokens)} 个账号）")
        return True
    except Exception as e:
        print(f"[失败] Token保存失败: {str(e)}")
        traceback.print_exc()
        return False


# ==================== 核心业务类 ====================

class ZeppStepRunner:
    """Zepp刷步数执行器"""
    
    def __init__(self, user: str, password: str, user_tokens: Dict):
        self.user_id = None
        self.device_id = str(uuid.uuid4())
        self.invalid = False
        self.log_str = ""
        self.user_tokens = user_tokens
        self.error = None
        self.actual_step = 0
        
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
    
    def login(self) -> Optional[str]:
    """
    登录并获取app_token
    支持三级Token缓存：access_token -> login_token -> app_token
    :return: app_token 或 None
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
        try:
            ok, msg = zeppHelper.check_app_token(app_token)
            if ok:
                self.log_str += "[成功] 使用缓存的app_token\n"
                return app_token
            # 添加详细日志
            self.log_str += f"[详细] app_token验证失败: {msg}\n"
        except Exception as e:
            self.log_str += f"[警告] app_token验证异常: {str(e)}\n"
        
        self.log_str += f"[警告] app_token已失效，尝试刷新...\n"
        
        # 尝试用login_token刷新app_token
        try:
            app_token, msg = zeppHelper.grant_app_token(login_token)
            if app_token:
                user_token_info["app_token"] = app_token
                user_token_info["app_token_time"] = get_timestamp()
                self.log_str += "[成功] app_token刷新成功\n"
                return app_token
            #  添加详细日志
            self.log_str += f"[详细] app_token刷新失败: {msg}\n"
        except Exception as e:
            self.log_str += f"[警告] app_token刷新异常: {str(e)}\n"
        
        self.log_str += f"[警告] login_token已失效，重新登录...\n"
    
    # Token全部失效，重新登录
    try:
        # 添加登录请求日志
        self.log_str += f"[请求] 正在向认证服务器发送登录请求...\n"
        self.log_str += f"[详细] 用户: {desensitize_user_name(self.user)}\n"
        
        access_token, msg = zeppHelper.login_access_token(self.user, self.password)
        
        # 添加响应日志
        if not access_token:
            self.log_str += f"[失败] 获取access_token失败\n"
            self.log_str += f"[详细] 错误信息: {msg}\n"
            # 检查是否401错误
            if "401" in str(msg):
                self.log_str += f"[分析] 401错误通常表示用户名或密码错误\n"
            return None
        
        self.log_str += f"[成功] access_token获取成功（长度: {len(access_token)}）\n"
        
        # 添加grant token请求日志
        self.log_str += f"[请求] 正在获取login_token和app_token...\n"
        
        login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(
            access_token, self.device_id, self.is_phone
        )
        
        if not login_token:
            self.log_str += f"[失败] Token获取失败\n"
            self.log_str += f"[详细] 错误信息: {msg}\n"
            return None
        
        #  添加成功日志
        self.log_str += f"[成功] 所有Token获取成功\n"
        self.log_str += f"[详细] user_id: {user_id}\n"
        self.log_str += f"[详细] device_id: {self.device_id[:8]}...\n"
        
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
    except Exception as e:
        self.log_str += f"[异常] 登录过程异常: {str(e)}\n"
        # 添加详细异常信息
        self.log_str += f"[详细] 异常类型: {type(e).__name__}\n"
        import traceback
        self.log_str += f"[堆栈] {traceback.format_exc()[:500]}\n"  # 限制长度
        return None

    
    def execute(self, min_step: int, max_step: int) -> Tuple[str, bool]:
        """
        执行刷步数
        :return: (message, success)
        """
        if self.invalid:
            return self.error or "[失败] 账号配置无效", False
        
        # 登录
        app_token = self.login()
        if not app_token:
            return "[失败] 登录失败", False
        
        # 生成随机步数
        self.actual_step = random.randint(min_step, max_step)
        self.log_str += f"[随机步数] 范围: {min_step}~{max_step}，生成步数: {self.actual_step}\n"
        
        # 提交步数
        try:
            ok, msg = zeppHelper.post_fake_brand_data(
                self.actual_step, app_token, self.user_id
            )
            
            result_msg = f"[{'成功' if ok else '失败'}] {msg}"
            if ok:
                result_msg += f" | 步数: {self.actual_step}"
            
            return result_msg, ok
        except Exception as e:
            error_msg = f"[异常] 提交步数异常: {str(e)}"
            self.log_str += error_msg + "\n"
            traceback.print_exc()
            return error_msg, False


# ==================== 主执行函数 ====================

def run_single_account(total: int, idx: int, user: str, password: str, 
                      min_step: int, max_step: int, user_tokens: Dict) -> Dict:
    """
    执行单个账号的刷步数任务
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
            "step": runner.actual_step if success else None
        }
    except Exception as e:
        error_msg = f"[异常] {str(e)}"
        log_str += error_msg + "\n"
        log_str += traceback.format_exc()
        
        exec_result = {
            "user": desensitize_user_name(user),
            "success": False,
            "msg": f"执行异常: {str(e)}"
        }
    
    print(log_str, flush=True)
    return exec_result


def execute_all_accounts(users: str, passwords: str, min_step: int, max_step: int,
                        user_tokens: Dict, use_concurrent: bool = False, 
                        sleep_seconds: float = Config.DEFAULT_SLEEP_GAP) -> List[Dict]:
    """执行所有账号的刷步数任务"""
    user_list = [u.strip() for u in users.split('#') if u.strip()]
    passwd_list = [p.strip() for p in passwords.split('#') if p.strip()]
    
    if len(user_list) != len(passwd_list):
        print(f"[错误] 账号数[{len(user_list)}]和密码数[{len(passwd_list)}]不匹配", flush=True)
        return []
    
    total = len(user_list)
    exec_results = []
    
    if use_concurrent:
        # 并发执行
        import concurrent.futures
        print(f"[信息] 使用并发模式执行（最大线程数: {min(total, 5)}）\n", flush=True)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(total, 5)) as executor:
            futures = [
                executor.submit(run_single_account, total, idx, user, passwd, 
                              min_step, max_step, user_tokens)
                for idx, (user, passwd) in enumerate(zip(user_list, passwd_list))
            ]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result(timeout=Config.REQUEST_TIMEOUT * 2)
                    exec_results.append(result)
                except concurrent.futures.TimeoutError:
                    print(f"[警告] 账号执行超时", flush=True)
                    exec_results.append({
                        "user": "超时账号",
                        "success": False,
                        "msg": "执行超时"
                    })
                except Exception as e:
                    print(f"[错误] 账号执行异常: {str(e)}", flush=True)
                    exec_results.append({
                        "user": "异常账号",
                        "success": False,
                        "msg": f"执行异常: {str(e)}"
                    })
    else:
        # 串行执行
        print(f"[信息] 使用串行模式执行（间隔: {sleep_seconds}秒）\n", flush=True)
        
        for idx, (user, passwd) in enumerate(zip(user_list, passwd_list)):
            result = run_single_account(total, idx, user, passwd, min_step, max_step, user_tokens)
            exec_results.append(result)
            
            if idx < total - 1:
                print(f"[等待] {sleep_seconds}秒后执行下一个账号...\n", flush=True)
                time.sleep(sleep_seconds)
    
    return exec_results


def push_notification(exec_results: List[Dict], sckey: str = None):
    """推送执行结果通知"""
    if not sckey or sckey.upper() == 'NO':
        print("[信息] 未配置推送或已禁用推送", flush=True)
        return
    
    total = len(exec_results)
    success_count = sum(1 for r in exec_results if r.get('success'))
    fail_count = total - success_count
    total_steps = sum(r.get('step', 0) for r in exec_results if r.get('success'))
    
    # 构建推送消息
    msg = f"### [执行摘要]\n\n"
    msg += f"- **执行时间**: {format_now()}\n"
    msg += f"- **触发方式**: {'手动触发' if is_manual_trigger() else '自动触发'}\n"
    msg += f"- **总账号数**: {total}\n"
    msg += f"- **成功**: {success_count} 个\n"
    msg += f"- **失败**: {fail_count} 个\n"
    if success_count > 0:
        msg += f"- **总步数**: {total_steps:,} 步\n"
        msg += f"- **平均步数**: {total_steps // success_count:,} 步/账号\n"
    msg += f"\n---\n\n"
    msg += f"### [详细结果]\n\n"
    
    for idx, result in enumerate(exec_results, 1):
        user = result.get('user', '未知')
        success = result.get('success', False)
        res_msg = result.get('msg', '无信息')
        step = result.get('step')
        
        status = "[成功]" if success else "[失败]"
        msg += f"{idx}. {status} **账号**: `{user}`\n"
        if step:
            msg += f"   - **步数**: {step:,} 步\n"
        msg += f"   - **结果**: {res_msg}\n\n"
    
    print(f"[信息] 正在发送推送通知...", flush=True)
    server_send(msg, sckey)


# ==================== 主入口 ====================

def main():
    """主函数 - 直接读取环境变量"""
    print(f"\n{'='*60}", flush=True)
    print(f"Zepp自动刷步数程序", flush=True)
    print(f"执行时间: {format_now()}", flush=True)
    print(f"触发方式: {'手动触发' if is_manual_trigger() else '自动触发'}", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    # 直接读取环境变量
    users = os.environ.get('USER', '').strip()
    passwords = os.environ.get('PWD', '').strip()
    sckey = os.environ.get('SCKEY', '').strip()
    use_concurrent = get_bool_value_default(os.environ.get('USE_CONCURRENT', ''), False)
    sleep_seconds = get_float_value_default(os.environ.get('SLEEP_GAP', ''), Config.DEFAULT_SLEEP_GAP)
    
    # 验证必需参数
    print("[检查] 环境变量配置...", flush=True)
    print(f"  - USER存在: {bool(users)}", flush=True)
    print(f"  - PWD存在: {bool(passwords)}", flush=True)
    print(f"  - SCKEY存在: {bool(sckey)}", flush=True)
    print(f"  - AES_KEY存在: {bool(os.environ.get('AES_KEY'))}\n", flush=True)
    
    if not users or not passwords:
        print("[错误] 缺少必需的环境变量: USER 或 PWD", flush=True)
        sys.exit(1)
    
    # 验证账号密码数量
    user_list = [u.strip() for u in users.split('#') if u.strip()]
    passwd_list = [p.strip() for p in passwords.split('#') if p.strip()]
    
    if len(user_list) != len(passwd_list):
        print(f"[错误] 账号数量({len(user_list)})与密码数量({len(passwd_list)})不匹配", flush=True)
        sys.exit(1)
    
    print(f"[成功] 配置验证通过（{len(user_list)} 个账号）\n", flush=True)
    
    # 加载Token缓存
    user_tokens = {}
    aes_key = get_aes_key()
    
    if aes_key:
        try:
            user_tokens = prepare_user_tokens()
        except Exception as e:
            print(f"[警告] Token加载失败: {str(e)}", flush=True)
            user_tokens = {}
    else:
        print("[警告] 未设置AES_KEY，无法使用Token缓存功能", flush=True)
    
    # 计算步数范围
    min_step, max_step = get_min_max_by_time()
    print(f"[信息] 步数范围: {min_step:,} ~ {max_step:,}", flush=True)
    print(f"[信息] 执行模式: {'并发' if use_concurrent else '串行'}", flush=True)
    
    if not use_concurrent:
        print(f"[信息] 账号间隔: {sleep_seconds}秒", flush=True)
    
    print(f"[信息] 推送通知: {'已启用' if sckey and sckey != 'NO' else '未启用'}\n", flush=True)
    
    # 执行刷步数
    try:
        exec_results = execute_all_accounts(
            users, passwords, min_step, max_step, 
            user_tokens, use_concurrent, sleep_seconds
        )
    except Exception as e:
        print(f"\n[错误] 执行过程中发生异常: {str(e)}", flush=True)
        traceback.print_exc()
        sys.exit(1)
    
    # 保存Token
    if aes_key and user_tokens:
        try:
            persist_user_tokens(user_tokens)
        except Exception as e:
            print(f"[警告] Token保存失败: {str(e)}", flush=True)
    
    # 统计结果
    total = len(exec_results)
    success_count = sum(1 for r in exec_results if r.get('success'))
    fail_count = total - success_count
    total_steps = sum(r.get('step', 0) for r in exec_results if r.get('success'))
    
    print(f"\n{'='*60}", flush=True)
    print(f"[执行完成]", flush=True)
    print(f"- 总账号数: {total}", flush=True)
    print(f"- 成功: {success_count} 个", flush=True)
    print(f"- 失败: {fail_count} 个", flush=True)
    if success_count > 0:
        print(f"- 总步数: {total_steps:,} 步", flush=True)
        print(f"- 平均步数: {total_steps // success_count:,} 步/账号", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    # 推送通知
    if sckey and sckey.upper() != 'NO':
        try:
            push_notification(exec_results, sckey)
        except Exception as e:
            print(f"[警告] 推送通知失败: {str(e)}", flush=True)
    
    # 返回退出码
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
