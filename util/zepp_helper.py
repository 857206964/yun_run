import json
import re
import time
import traceback
import urllib
import uuid
from datetime import datetime
from util.constants import DATA_JSON
import pytz
import requests

from util.aes_help import encrypt_data, HM_AES_KEY, HM_AES_IV

#feat: 通过AES加密保存账号token，避免经常登录导致429. 需要配置secret：AES_KEY
#通过账号密码获取access_token和refresh_token 但是refresh_token不知道怎么使用
def login_access_token(user, password) -> (str | None, str | None):
    """登录获取access_token(加密方式)"""
    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "user-agent": "MiFit6.14.0 (M2007J1SC; Android 12; Density/2.75)",
        "app_name": "com.xiaomi.hm.health",
        "appname": "com.xiaomi.hm.health",
        "appplatform": "android_phone",
        "x-hm-ekv": "1",
        "hm-privacy-ceip": "false"
    }
    
    login_data = {
        'emailOrPhone': user,
        'password': password,
        'state': 'REDIRECTION',
        'client_id': 'HuaMi',
        'country_code': 'CN',
        'token': 'access',
        'redirect_uri': 'https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html',
    }
    
    
    query = urllib.parse.urlencode(login_data)
    plaintext = query.encode('utf-8')
    
    # 检查加密参数
    print(f"[加密] 明文长度: {len(plaintext)} 字节")
    print(f"[加密] 密钥长度: {len(HM_AES_KEY)} 字节")
    print(f"[加密] IV长度: {len(HM_AES_IV)} 字节")
    
    try:
        cipher_data = encrypt_data(plaintext, HM_AES_KEY, HM_AES_IV)
        print(f"[加密] 密文长度: {len(cipher_data)} 字节")
    except Exception as e:
        error_msg = f"加密失败: {str(e)}"
        print(f"[错误] {error_msg}")
        return None, error_msg
    
    url1 = 'https://api-user.zepp.com/v2/registrations/tokens'
    
    try:
        r1 = requests.post(url1, data=cipher_data, headers=headers, 
                          allow_redirects=False, timeout=10)
        
        # print(f"[响应] 状态码: {r1.status_code}")
        # print(f"[响应] Headers: {dict(r1.headers)}")
        
        if r1.status_code != 303:
            return None, f"登录异常，status: {r1.status_code}"
            
        location = r1.headers.get("Location", "")
        # print(f"[重定向] Location: {location[:100]}...")
        
        code = get_access_token(location)
        if code is None:
            error_code = get_error_code(location)
            return None, f"获取accessToken失败: {error_code}"
            
        print(f"[成功] access_token长度: {len(code)}")
        return code, None
        
    except Exception as e:
        error_msg = f"请求异常: {str(e)}"
        print(f"[异常] {error_msg}")
        import traceback
        print(f"[堆栈] {traceback.format_exc()[:300]}")
        return None, error_msg


# 获取登录code
def get_access_token(location):
    code_pattern = re.compile("(?<=access=).*?(?=&)")
    result = code_pattern.findall(location)
    if result is None or len(result) == 0:
        return None
    return result[0]


def get_error_code(location):
    code_pattern = re.compile("(?<=error=).*?(?=&)")
    result = code_pattern.findall(location)
    if result is None or len(result) == 0:
        return None
    return result[0]


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


# 获取login_token，app_token，userid
def grant_login_tokens(access_token, device_id, is_phone=False) -> (str | None, str | None, str | None, str | None):
    url = "https://account.huami.com/v2/client/login"
    headers = {
        "app_name": "com.xiaomi.hm.health",
        "x-request-id": f"{str(uuid.uuid4())}",
        "accept-language": "zh-CN",
        "appname": "com.xiaomi.hm.health",
        "cv": "50818_6.14.0",
        "v": "2.0",
        "appplatform": "android_phone",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    if is_phone:
        data = {
            "app_name": "com.xiaomi.hm.health",
            "app_version": "6.14.0",
            "code": access_token,
            "country_code": "CN",
            "device_id": device_id,
            "device_model": "phone",
            "grant_type": "access_token",
            "third_name": "huami_phone",
        }
    else:
        data = {
            "allow_registration=": "false",
            "app_name": "com.xiaomi.hm.health",
            "app_version": "6.14.0",
            "code": access_token,
            "country_code": "CN",
            "device_id": device_id,
            "device_model": "android_phone",
            "dn": "account.zepp.com,api-user.zepp.com,api-mifit.zepp.com,api-watch.zepp.com,app-analytics.zepp.com,api-analytics.huami.com,auth.zepp.com",
            "grant_type": "access_token",
            "lang": "zh_CN",
            "os_version": "1.5.0",
            "source": "com.xiaomi.hm.health:6.14.0:50818",
            "third_name": "email",
        }
    resp = requests.post(url, data=data, headers=headers).json()
    # print("请求客户端登录成功：%s" % json.dumps(resp, ensure_ascii=False, indent=2))  #
    _login_token, _userid, _app_token = None, None, None
    try:
        result = resp.get("result")
        if result != "ok":
            return None, None, None, "客户端登录失败：%s" % result
        _login_token = resp["token_info"]["login_token"]
        _app_token = resp["token_info"]["app_token"]
        _userid = resp["token_info"]["user_id"]
    except:
        print("提取login_token失败：%s" % json.dumps(resp, ensure_ascii=False, indent=2))
    return _login_token, _app_token, _userid, None


# 获取app_token 用于提交数据变更
def grant_app_token(login_token: str) -> (str | None, str | None):
    url = f"https://account-cn.huami.com/v1/client/app_tokens?app_name=com.xiaomi.hm.health&dn=api-user.huami.com%2Capi-mifit.huami.com%2Capp-analytics.huami.com&login_token={login_token}"
    headers = {'User-Agent': 'MiFit/5.3.0 (iPhone; iOS 14.7.1; Scale/3.00)'}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return None, "请求异常：%d" % resp.status_code
    resp = resp.json()
    print("grant_app_token: %s" % json.dumps(resp))

    result = resp.get("result")
    if result != "ok":
        error_code = resp.get("error_code")
        return None, "请求失败：%s" % error_code
    app_token = resp['token_info']['app_token']
    return app_token, None


# 获取用户信息 主要用于检查app_token是否有效
def check_app_token(app_token) -> (bool, str | None):
    url = "https://api-mifit-cn3.zepp.com/huami.health.getUserInfo.json"

    params = {
        "r": "00b7912b-790a-4552-81b1-3742f9dd1e76",
        "userid": "1188760659",
        "appid": "428135909242707968",
        "channel": "Normal",
        "country": "CN",
        "cv": "50818_6.14.0",
        "device": "android_31",
        "device_type": "android_phone",
        "lang": "zh_CN",
        "timezone": "Asia/Shanghai",
        "v": "2.0"
    }

    headers = {
        "User-Agent": "MiFit6.14.0 (M2007J1SC; Android 12; Density/2.75)",
        "Accept-Encoding": "gzip",
        "hm-privacy-diagnostics": "false",
        "country": "CN",
        "appplatform": "android_phone",
        "hm-privacy-ceip": "true",
        "x-request-id": str(uuid.uuid4()),
        "timezone": "Asia/Shanghai",
        "channel": "Normal",
        "cv": "50818_6.14.0",
        "appname": "com.xiaomi.hm.health",
        "v": "2.0",
        "apptoken": app_token,
        "lang": "zh_CN",
        "clientid": "428135909242707968"
    }
    response = requests.get(url, params=params, headers=headers)
    if response.status_code != 200:
        return False, "请求异常：%d" % response.status_code
    response = response.json()
    message = response["message"]
    if message == "success":
        return True, None
    else:
        return False, message


def renew_login_token(login_token) -> (str | None, str | None):
    url = "https://account-cn3.zepp.com/v1/client/renew_login_token"
    params = {
        "os_version": "v0.8.1",
        "dn": "account.zepp.com,api-user.zepp.com,api-mifit.zepp.com,api-watch.zepp.com,app-analytics.zepp.com,api-analytics.huami.com,auth.zepp.com",
        "login_token": login_token,
        "source": "com.xiaomi.hm.health:6.14.0:50818",
        "timestamp": get_time()
    }
    headers = {
        "User-Agent": "MiFit6.14.0 (M2007J1SC; Android 12; Density/2.75)",
        "Accept-Encoding": "gzip",
        "app_name": "com.xiaomi.hm.health",
        "hm-privacy-ceip": "false",
        "x-request-id": str(uuid.uuid4()),
        "accept-language": "zh-CN",
        "appname": "com.xiaomi.hm.health",
        "cv": "50818_6.14.0",
        "v": "2.0",
        "appplatform": "android_phone"
    }

    resp = requests.get(url, params=params, headers=headers)
    if resp.status_code != 200:
        return None, "请求异常：%d" % resp.status_code
    resp = resp.json()
    result = resp["result"]

    if result != "ok":
        return None, "请求失败：%s" % result
    login_token = resp["token_info"]["login_token"]
    return login_token, None


def update_step(app_token, userid, step, ip):
    t = get_time()

    today = time.strftime("%F")

    data_json = DATA_JSON

    find_date = re.compile(r".*?date%22%3A%22(.*?)%22%2C%22data.*?")
    find_step = re.compile(r".*?ttl%5C%22%3A(.*?)%2C%5C%22dis.*?")
    data_json = re.sub(find_date.findall(data_json)[0], today, str(data_json))
    data_json = re.sub(find_step.findall(data_json)[0], str(step), str(data_json))

    url = f'https://api-mifit-cn.huami.com/v1/data/band_data.json?&t={t}&r={str(uuid.uuid4())}'
    head = {
        "apptoken": app_token,
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Forwarded-For": ip  # 添加IP伪装
    }

    data = f'userid={userid}&last_sync_data_time=1597306380&device_type=0&last_deviceid=DA932FFFFE8816E7&data_json={data_json}'

    try:
        response = requests.post(url, data=data, headers=head, timeout=30)  # 使用 Config.REQUEST_TIMEOUT，如果有
        # print(f"[响应] 状态码: {response.status_code}")
    
        if response.status_code != 200:
            return False, f"请求修改步数异常：{response.status_code}"
    
        response_json = response.json()
        message = response_json.get("message", "未知错误")
        if message == "success":
            return True, message
        else:
            return False, message
    
    except requests.exceptions.Timeout:
        return False, "请求超时"
    except requests.exceptions.RequestException as e:
        return False, f"网络异常: {str(e)}"
    except ValueError as e:  # JSON 解析错误
        return False, f"响应解析失败: {str(e)}"
    except Exception as e:
        print(f"[异常] 更新步数失败: {traceback.format_exc()}")  # 打印堆栈
        return False, f"未知异常: {str(e)}"
