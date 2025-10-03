
# -*- coding: utf8 -*-
import math
import traceback
from datetime import datetime
import pytz
import uuid

import json
import random
import re
import time
import os
import sys

import requests
from util.aes_help import encrypt_data, decrypt_data
import util.zepp_helper as zeppHelper

# 获取默认值转int
def get_int_value_default(_config: dict, _key, default):
    _config.setdefault(_key, default)
    return int(_config.get(_key))


# 根据时间获取步数范围
def get_steps_by_time():
    hour = time_bj.hour
    minute = time_bj.minute
    
    # 上午9点运行一次(随机步数1000-10000)
    if hour == 9 and minute <= 59:
        return 1000, 10000
    # 下午3点运行一次(随机步数15000-25000)
    elif hour == 15 and minute <= 59:
        return 15000, 25000
    # 晚上7:30运行一次(随机步数30000-40000)
    elif hour == 19 and minute >= 30:
        return 30000, 40000
    # 默认范围
    else:
        return 1000, 10000


# 虚拟ip地址
def fake_ip():
    # 随便找的国内IP段：223.64.0.0 - 223.117.255.255
    return f"{223}.{random.randint(64, 117)}.{random.randint(0, 255)}.{random.randint(0, 255)}"


# 账号脱敏
def desensitize_user_name(user):
    if len(user) <= 8:
        ln = max(math.floor(len(user) / 3), 1)
        return f'{user[:ln]}***{user[-ln:]}'
    return f'{user[:3]}****{user[-4:]}'


# 获取北京时间
def get_beijing_time():
    target_timezone = pytz.timezone('Asia/Shanghai')
    # 获取当前时间
    return datetime.now().astimezone(target_timezone)


# 格式化时间
def format_now():
    return get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")


# 获取时间戳
def get_time():
    current_time = get_beijing_time()
    return "%.0f" % (current_time.timestamp() * 1000)


# Server酱推送
def server_send(msg, sckey=None):
    if sckey == '' or sckey is None:
        return
    server_url = "https://sctapi.ftqq.com/" + str(sckey) + ".send"

    data = {
        'text': msg,
        'desp': msg
    }
    try:
        requests.post(server_url, data=data)
    except Exception as e:
        print(f"Server酱推送异常: {e}")


class MiMotionRunner:
    def __init__(self, _user, _passwd):
        self.user_id = None
        self.device_id = str(uuid.uuid4())
        user = str(_user)
        password = str(_passwd)
        self.invalid = False
        self.log_str = ""
        if user == '' or password == '':
            self.error = "用户名或密码填写有误！"
            self.invalid = True
            pass
        self.password = password
        if (user.startswith("+86")) or "@" in user:
            user = user
        else:
            user = "+86" + user
        if user.startswith("+86"):
            self.is_phone = True
        else:
            self.is_phone = False
        self.user = user
        self.fake_ip_addr = fake_ip()
        self.log_str += f"创建虚拟ip地址：{self.fake_ip_addr}\n"

    # 登录
    def login(self):
        user_token_info = user_tokens.get(self.user)
        if user_token_info is not None:
            access_token = user_token_info.get("access_token")
            login_token = user_token_info.get("login_token")
            app_token = user_token_info.get("app_token")
            self.device_id = user_token_info.get("device_id")
            self.user_id = user_token_info.get("user_id")
            if self.device_id is None:
                self.device_id = str(uuid.uuid4())
                user_token_info["device_id"] = self.device_id
            ok,msg = zeppHelper.check_app_token(app_token)
            if ok:
                self.log_str += "使用加密保存的app_token\n"
                return app_token
            else:
                self.log_str += f"app_token失效 重新获取 last grant time: {user_token_info.get('app_token_time')}\n"
                # 检查login_token是否可用
                app_token, msg = zeppHelper.grant_app_token(login_token)
                if app_token is None:
                    self.log_str += f"login_token 失效 重新获取 last grant time: {user_token_info.get('login_token_time')}\n"
                    login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(access_token, self.device_id, self.is_phone)
                    if login_token is None:
                        self.log_str += f"access_token 已失效：{msg} last grant time:{user_token_info.get('access_token_time')}\n"
                    else:
                        user_token_info["login_token"] = login_token
                        user_token_info["app_token"] = app_token
                        user_token_info["user_id"] = user_id
                        user_token_info["login_token_time"] = get_time()
                        user_token_info["app_token_time"] = get_time()
                        self.user_id = user_id
                        return app_token
                else:
                    self.log_str += "重新获取app_token成功\n"
                    user_token_info["app_token"] = app_token
                    user_token_info["app_token_time"] = get_time()
                    return app_token

        # access_token 失效 或者没有保存加密数据
        access_token, msg = zeppHelper.login_access_token(self.user, self.password)
        if access_token is None:
            self.log_str += "登录获取accessToken失败：%s" % msg
            return None
        # print(f"device_id:{self.device_id} isPhone: {self.is_phone}")
        login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(access_token, self.device_id, self.is_phone)
        if login_token is None:
            self.log_str += f"登录提取的 access_token 无效：{msg}"
            return None

        user_token_info = dict()
        user_token_info["access_token"] = access_token
        user_token_info["login_token"] = login_token
        user_token_info["app_token"] = app_token
        user_token_info["user_id"] = user_id
        # 记录token获取时间
        user_token_info["access_token_time"] = get_time()
        user_token_info["login_token_time"] = get_time()
        user_token_info["app_token_time"] = get_time()
        if self.device_id is None:
            self.device_id = uuid.uuid4()
        user_token_info["device_id"] = self.device_id
        user_tokens[self.user] = user_token_info
        return app_token


    # 主函数
    def login_and_post_step(self, min_step, max_step):
        if self.invalid:
            return "账号或密码配置有误", False
        app_token = self.login()
        if app_token is None:
            return "登陆失败！", False

        step = str(random.randint(min_step, max_step))
        self.log_str += f"已设置为随机步数范围({min_step}~{max_step}) 随机值:{step}\n"
        ok, msg = zeppHelper.post_fake_brand_data(step, app_token, self.user_id)
        return f"修改步数（{step}）[" + msg + "]", ok


def run_single_account(user_mi, passwd_mi, sckey=None):
    log_str = f"[{format_now()}]\n账号：{desensitize_user_name(user_mi)}\n"
    try:
        runner = MiMotionRunner(user_mi, passwd_mi)
        exec_msg, success = runner.login_and_post_step(min_step, max_step)
        log_str += runner.log_str
        log_str += f'{exec_msg}\n'
        exec_result = {"user": user_mi, "success": success,
                       "msg": exec_msg}
        # 推送消息
        if sckey:
            server_send(f"账号：{desensitize_user_name(user_mi)} 刷步数{'成功' if success else '失败'}\n{exec_msg}", sckey)
    except:
        log_str += f"执行异常:{traceback.format_exc()}\n"
        log_str += traceback.format_exc()
        exec_result = {"user": user_mi, "success": False,
                       "msg": f"执行异常:{traceback.format_exc()}"}
        # 推送异常消息
        if sckey:
            server_send(f"账号：{desensitize_user_name(user_mi)} 刷步数异常\n{traceback.format_exc()}", sckey)
    print(log_str)
    return exec_result


def prepare_user_tokens() -> dict:
    data_path = r"encrypted_tokens.data"
    if os.path.exists(data_path):
        with open(data_path, 'rb') as f:
            data = f.read()
        try:
            decrypted_data = decrypt_data(data, aes_key, None)
            # 假设原始明文为 UTF-8 编码文本
            return json.loads(decrypted_data.decode('utf-8', errors='strict'))
        except:
            print("密钥不正确或者加密内容损坏 放弃token")
            return dict()
    else:
        return dict()

def persist_user_tokens():
    data_path = r"encrypted_tokens.data"
    origin_str = json.dumps(user_tokens, ensure_ascii=False)
    cipher_data = encrypt_data(origin_str.encode("utf-8"), aes_key, None)
    with open(data_path, 'wb') as f:
        f.write(cipher_data)
        f.flush()
        f.close()

if __name__ == "__main__":
    # 北京时间
    time_bj = get_beijing_time()
    encrypt_support = False
    user_tokens = dict()
    
    # 从命令行参数或环境变量获取账号密码
    if len(sys.argv) >= 3:
        user = sys.argv[1]
        password = sys.argv[2]
        sckey = sys.argv[3] if len(sys.argv) > 3 else None
    else:
        user = os.environ.get("USER")
        password = os.environ.get("PWD")
        sckey = os.environ.get("SCKEY")
        
    if not user or not password:
        print("未正确配置账号密码，无法执行")
        exit(1)
        
    # AES_KEY处理
    if os.environ.__contains__("AES_KEY") is True:
        aes_key = os.environ.get("AES_KEY")
        if aes_key is not None:
            aes_key = aes_key.encode('utf-8')
            if len(aes_key) == 16:
                encrypt_support = True
        if encrypt_support:
            user_tokens = prepare_user_tokens()
        else:
            print("AES_KEY未设置或者无效 无法使用加密保存功能")
            
    # 获取步数范围
    min_step, max_step = get_steps_by_time()
    
    # 执行刷步数
    result = run_single_account(user, password, sckey)
    
    # 保存token
    if encrypt_support:
        persist_user_tokens()
        
    # 根据执行结果退出
    if not result['success']:
        exit(1)
