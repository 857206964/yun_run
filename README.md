# 自动步数更新项目

自动更新步数的GitHub Actions项目，支持每日三次定时运行。覆盖白天晚上为总步数。

## 🚀 功能特点

- ✅ 自动登录并更新步数
- ✅ 支持Token加密存储
- ✅ 随机IP地址（包括39开头）
- ✅ Server酱消息推送
- ✅ 每日三次定时运行
- ✅ 智能步数范围

## ⏰ 运行时间

| 时间段 | 北京时间 | UTC时间 | 步数范围 |
|--------|----------|---------|----------|
| 上午 | 09:00 | 01:00 | 1000-10000 |
| 下午 | 15:00 | 07:00 | 15000-25000 |
| 晚上 | 19:30 | 11:30 | 30000-40000 |

## 📝 配置步骤

### 1. Fork本仓库

点击右上角Fork按钮，将项目复制到你的账户下

### 2. 配置Secrets

进入仓库设置 → Secrets and variables → Actions → New repository secret

添加以下4个secrets：

| Name | Description | Example |
|------|-------------|---------|
| `USER` | 用户名 | your_username |
| `PWD` | 密码 | your_password |
| `SCKEY` | Server酱推送密钥 | SCT123456... |
| `AES_KEY` | AES加密密钥 | your_secret_key |

### 3. 创建encrypted_tokens.data（可选）

如果你已有token，可以使用加密工具：

```bash
python encrypt_token.py
