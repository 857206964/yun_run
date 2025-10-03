# -*- coding: utf-8 -*-
"""
Zepp API 封装
处理登录、Token获取、步数提交等操作
"""
import requests
import time
import random
import hmac
import hashlib
import json


class ZeppAPI:
    """Zepp API 封装类"""
    
    BASE_URL = "https://api-mifit-cn2.huami.com"
    APP_NAME = "com.xiaomi.hm.health"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'MiFit/4.6.0 (iPhone; iOS 14.7.1; Scale/3.00)',
            'Content-Type': 'application/x-www-form-urlencoded'
        })
    
    @staticmethod
    def generate_device_id():
        """生成设备ID"""
        import uuid
        return str(uuid.uuid4())
    
    @staticmethod
    def generate_signature(params: dict, secret: str = None) -> str:
        """
        生成请求签名
        :param params: 请求参数字典
        :param secret: 签名密钥
        :return: 签名字符串
        """
        # 按键排序并拼接
        sorted_params = sorted(params.items())
        sign_str = '&'.join([f"{k}={v}" for k, v in sorted_params])
        
        if secret:
            sign_str += f"&key={secret}"
        
        # MD5签名
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest()
    
    def login_access_token(self, user: str, password: str) -> tuple:
        """
        第一步：获取 access_token
        :param user: 用户名（手机号/邮箱）
        :param password: 密码
        :return: (access_token, error_msg)
        """
        url = f"{self.BASE_URL}/v2/user/login"
        
        params = {
            'country_code': 'CN',
            'device_id': self.generate_device_id(),
            'device_model': 'iPhone13,2',
            'app_version': '6.0.0',
            'source': 'com.xiaomi.hm.health',
            'third_name': 'email' if '@' in user else 'huami',
            'lang': 'zh_CN'
        }
        
        data = {
            'dn': user,
            'password': hashlib.md5(password.encode()).hexdigest(),  # MD5加密密码
            'grant_type': 'password'
        }
        
        try:
            response = self.session.post(url, params=params, data=data, timeout=10)
            result = response.json()
            
            if result.get('code') == 0 or result.get('access_token'):
                return result.get('access_token'), None
            else:
                return None, result.get('error_msg', '登录失败')
        except Exception as e:
            return None, f"登录异常: {str(e)}"
    
    def grant_login_tokens(self, access_token: str, device_id: str, is_phone: bool = True) -> tuple:
        """
        第二步：用 access_token 换取 login_token 和 app_token
        :param access_token: 访问令牌
        :param device_id: 设备ID
        :param is_phone: 是否手机号登录
        :return: (login_token, app_token, user_id, error_msg)
        """
        url = f"{self.BASE_URL}/v2/user/login"
        
        params = {
            'country_code': 'CN',
            'device_id': device_id,
            'device_model': 'iPhone13,2',
            'app_version': '6.0.0',
            'source': self.APP_NAME,
            'third_name': 'huami_phone' if is_phone else 'huami_email',
            'lang': 'zh_CN',
            'grant_type': 'access_token',
            'access_token': access_token
        }
        
        try:
            response = self.session.post(url, params=params, timeout=10)
            result = response.json()
            
            if result.get('code') == 0:
                token_info = result.get('token_info', {})
                return (
                    token_info.get('login_token'),
                    token_info.get('app_token'),
                    token_info.get('user_id'),
                    None
                )
            else:
                return None, None, None, result.get('error_msg', 'Token换取失败')
        except Exception as e:
            return None, None, None, f"Token换取异常: {str(e)}"
    
    def grant_app_token(self, login_token: str) -> tuple:
        """
        第三步：刷新 app_token
        :param login_token: 登录令牌
        :return: (app_token, error_msg)
        """
        url = f"{self.BASE_URL}/v2/user/app_tokens"
        
        params = {
            'country_code': 'CN',
            'device_id': self.generate_device_id(),
            'device_model': 'iPhone13,2',
            'app_version': '6.0.0',
            'source': self.APP_NAME,
            'lang': 'zh_CN',
            'login_token': login_token
        }
        
        try:
            response = self.session.post(url, params=params, timeout=10)
            result = response.json()
            
            if result.get('code') == 0:
                token_info = result.get('token_info', {})
                return token_info.get('app_token'), None
            else:
                return None, result.get('error_msg', 'app_token刷新失败')
        except Exception as e:
            return None, f"app_token刷新异常: {str(e)}"
    
    def check_app_token(self, app_token: str) -> tuple:
        """
        检查 app_token 是否有效
        :param app_token: 应用令牌
        :return: (is_valid, error_msg)
        """
        url = f"{self.BASE_URL}/v1/sport/run/history.json"
        
        headers = {
            'apptoken': app_token
        }
        
        try:
            response = self.session.get(url, headers=headers, timeout=10)
            result = response.json()
            
            # 如果返回数据正常，说明token有效
            if 'data' in result or result.get('code') == 0:
                return True, None
            else:
                return False, 'Token已失效'
        except Exception as e:
            return False, f"Token验证异常: {str(e)}"
    
    def post_fake_brand_data(self, step: int, app_token: str, user_id: str) -> tuple:
        """
        提交虚假步数数据
        :param step: 步数
        :param app_token: 应用令牌
        :param user_id: 用户ID
        :return: (success, error_msg)
        """
        url = f"{self.BASE_URL}/v1/data/band_data.json"
        
        timestamp = int(time.time() * 1000)
        date_str = time.strftime('%Y-%m-%d', time.localtime())
        
        data = {
            'userid': user_id,
            'last_sync_data_time': timestamp,
            'device_type': '1',
            'data_json': json.dumps([{
                'data_hr': f'{random.randint(60, 100)},1,{timestamp}',
                'data_id': timestamp,
                'data_source': 1,
                'date': date_str,
                'device_type': 1,
                'is_local': 0,
                'last_update_time': timestamp,
                'source_id': random.randint(1000000, 9999999),
                'steps': step,
                'timestamp': timestamp,
                'user_id': user_id
            }])
        }
        
        headers = {
            'apptoken': app_token
        }
        
        try:
            response = self.session.post(url, headers=headers, data=data, timeout=10)
            result = response.json()
            
            if result.get('code') == 0 or result.get('message') == 'success':
                return True, f"成功提交 {step} 步"
            else:
                return False, result.get('message', '提交失败')
        except Exception as e:
            return False, f"提交异常: {str(e)}"


# 全局API实例
zepp_api = ZeppAPI()

# 导出便捷函数
login_access_token = zepp_api.login_access_token
grant_login_tokens = zepp_api.grant_login_tokens
grant_app_token = zepp_api.grant_app_token
check_app_token = zepp_api.check_app_token
post_fake_brand_data = zepp_api.post_fake_brand_data
