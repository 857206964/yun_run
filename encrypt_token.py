import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import os

def encrypt_token(token, aes_key):
    """加密token并保存"""
    try:
        # 准备数据
        token_data = {
            'token': token
        }
        
        # 转为JSON字符串
        json_str = json.dumps(token_data)
        
        # 准备AES密钥（16字节）
        key = aes_key.encode('utf-8')[:16].ljust(16, b'0')
        
        # 加密
        cipher = AES.new(key, AES.MODE_ECB)
        encrypted = cipher.encrypt(pad(json_str.encode('utf-8'), AES.block_size))
        
        # 保存到文件
        with open('encrypted_tokens.data', 'wb') as f:
            f.write(encrypted)
        
        print("✅ Token加密成功，已保存到 encrypted_tokens.data")
        return True
        
    except Exception as e:
        print(f"❌ 加密失败: {str(e)}")
        return False

if __name__ == '__main__':
    print("=" * 50)
    print("Token加密工具")
    print("=" * 50)
    
    token = input("请输入Token: ").strip()
    aes_key = input("请输入AES密钥: ").strip()
    
    if token and aes_key:
        encrypt_token(token, aes_key)
    else:
        print("❌ Token或密钥不能为空")
