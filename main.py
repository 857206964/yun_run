import os
import time
import json
import random
import requests
from datetime import datetime
from config import Config
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64

class StepCounter:
    def __init__(self):
        self.user = os.getenv('USER')
        self.pwd = os.getenv('PWD')
        self.sckey = os.getenv('SCKEY')
        self.aes_key = os.getenv('AES_KEY')
        self.session = requests.Session()
        self.token = None
        
    def get_random_ip(self):
        """生成随机IP地址（包括39开头）"""
        ip_prefixes = ['39', '117', '112', '183', '163', '223']
        prefix = random.choice(ip_prefixes)
        
        if prefix == '39':
            return f"39.{random.randint(96, 111)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
        else:
            return f"{prefix}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
    
    def get_headers(self):
        """获取请求头"""
        return {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; MI 8) AppleWebKit/537.36',
            'X-Forwarded-For': self.get_random_ip(),
            'X-Real-IP': self.get_random_ip(),
            'Content-Type': 'application/json'
        }
    
    def decrypt_token(self):
        """解密token"""
        try:
            if not os.path.exists('encrypted_tokens.data'):
                self.server_send("❌ encrypted_tokens.data 文件不存在", self.sckey)
                return None
                
            with open('encrypted_tokens.data', 'rb') as f:
                encrypted_data = f.read()
            
            key = self.aes_key.encode('utf-8')[:16].ljust(16, b'0')
            cipher = AES.new(key, AES.MODE_ECB)
            decrypted = unpad(cipher.decrypt(encrypted_data), AES.block_size)
            
            token_data = json.loads(decrypted.decode('utf-8'))
            self.token = token_data.get('token')
            
            return self.token
        except Exception as e:
            self.server_send(f"❌ Token解密失败: {str(e)}", self.sckey)
            return None
    
    def login(self):
        """登录获取token"""
        try:
            login_url = Config.LOGIN_URL
            data = {
                'username': self.user,
                'password': self.pwd
            }
            
            response = self.session.post(
                login_url, 
                json=data, 
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:
                    self.token = result.get('data', {}).get('token')
                    self.server_send(f"✅ 登录成功", self.sckey)
                    return True
                else:
                    self.server_send(f"❌ 登录失败: {result.get('msg')}", self.sckey)
                    return False
            else:
                self.server_send(f"❌ 登录请求失败: {response.status_code}", self.sckey)
                return False
                
        except Exception as e:
            self.server_send(f"❌ 登录异常: {str(e)}", self.sckey)
            return False
    
    def get_step_range(self):
        """根据当前时间获取步数范围"""
        beijing_hour = (datetime.utcnow().hour + 8) % 24
        
        if 8 <= beijing_hour < 14:
            # 上午时段
            return random.randint(1000, 10000)
        elif 14 <= beijing_hour < 19:
            # 下午时段
            return random.randint(15000, 25000)
        else:
            # 晚上时段
            return random.randint(30000, 40000)
    
    def update_steps(self, steps):
        """更新步数"""
        try:
            if not self.token:
                self.server_send("❌ Token不存在，无法更新步数", self.sckey)
                return False
            
            update_url = Config.STEP_URL
            headers = self.get_headers()
            headers['Authorization'] = f'Bearer {self.token}'
            
            data = {
                'step': steps
            }
            
            response = self.session.post(
                update_url,
                json=data,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:
                    self.server_send(
                        f"✅ 步数更新成功\n📊 当前步数: {steps}\n🕐 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
                        self.sckey
                    )
                    return True
                else:
                    self.server_send(f"❌ 更新失败: {result.get('msg')}", self.sckey)
                    return False
            else:
                self.server_send(f"❌ 更新请求失败: {response.status_code}", self.sckey)
                return False
                
        except Exception as e:
            self.server_send(f"❌ 更新异常: {str(e)}", self.sckey)
            return False
    
    def server_send(self, msg, sckey=None):
        """Server酱推送"""
        if not sckey:
            print(msg)
            return
        
        try:
            server_url = f"https://sctapi.ftqq.com/{sckey}.send"
            data = {
                'text': msg,
                'desp': msg
            }
            requests.post(server_url, data=data, timeout=10)
            print(msg)
        except Exception as e:
            print(f"推送失败: {str(e)}")
    
    def run(self):
        """主运行逻辑"""
        print("=" * 50)
        print("开始执行自动步数任务")
        print("=" * 50)
        
        # 尝试解密token
        if not self.decrypt_token():
            # 解密失败，尝试登录
            if not self.login():
                return
        
        # 获取步数范围并更新
        steps = self.get_step_range()
        self.update_steps(steps)
        
        print("=" * 50)
        print("任务执行完成")
        print("=" * 50)

if __name__ == '__main__':
    counter = StepCounter()
    counter.run()
