zepp-step-counter/
├── .github/
│   └── workflows/
│       └── run.yml           # GitHub Actions 配置
├── util/
│   ├── __init__.py          # 空文件
│   ├── aes_help.py          # AES加密工具
│   └── zepp_helper.py       # Zepp API封装
├── main.py                   # 主程序
├── requirements.txt          # 依赖包
└── README.md                # 说明文档


# 🏃 Zepp/华米运动自动刷步数

> 基于GitHub Actions的全自动刷步数工具，支持多账户、Token持久化、随机时间执行

## ✨ 特性

- ✅ **全自动化**：基于GitHub Actions，无需服务器
- 🔐 **安全加密**：AES-128加密存储Token，支持自定义密钥
- 🎲 **智能随机**：
  - 随机步数（可配置范围）
  - 随机执行时间（反检测机制）
- 👥 **多账户支持**：支持多个账户批量刷步
- 📊 **Token缓存**：避免频繁登录

## 🚀 快速开始

### 1️⃣ Fork本仓库

点击右上角 Fork 按钮

### 2️⃣ 配置Secrets

进入 `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

必需配置：

| 名称 | 说明 | 示例 |
|------|------|------|
| `ZEPP_ACCOUNT` | 华米账号（多账户用逗号分隔） | `user1@example.com,user2@example.com` |
| `ZEPP_PASSWORD` | 统一密码 | `your_password` |
| `AES_KEY` | 16字节AES密钥 | `MySecretKey12345` |
| `PAT` | Personal Access Token | `ghp_xxxxxxxxxxxx` |

### 3️⃣ 配置Variables

进入 `Settings` → `Secrets and variables` → `Actions` → `Variables` → `New repository variable`

可选配置：

| 名称 | 说明 | 默认值 |
|------|------|--------|
| `STEP_MIN` | 最小步数 | `8000` |
| `STEP_MAX` | 最大步数 | `15000` |
| `CRON_HOURS` | 执行小时范围 | `8-22` |

### 4️⃣ 获取PAT (Personal Access Token)

1. 访问 https://github.com/settings/tokens
2. 点击 `Generate new token` → `Generate new token (classic)`
3. 勾选权限(默认)：
   - ✅ `repo` (完整仓库访问)
   - ✅ `workflow` (修改workflow)
   
4. 权限自定义
  -   点击 `Repository permissions` 展开菜单，并勾选以下四个权限即可，其他的可以不勾选
  -  `Actions Access`: `Read and write` 用于获取Actions的权限
  -  `Contents Access`: `Read and write` 用于更新定时任务和日志文件的权限
  -  `Metadata Access`: `Read-only` 这个自带的必选
  -  `Workflows Access`: `Read and write` 获取用于更新 `.github/workflow` 下文件的权限
5. 生成后复制Token，添加到Secrets中
  

### 5️⃣ 启用Actions

1. 进入仓库的 `Actions` 标签页
2. 点击 `I understand my workflows, go ahead and enable them`
3. 手动触发测试：
   - 选择 `刷步数` workflow
   - 点击 `Run workflow`

## 📅 执行逻辑

```mermaid
graph TD
    A[定时触发/手动触发] --> B[刷步数任务]
    B --> C{执行成功?}
    C -->|Yes| D[触发Random Cron]
    C -->|No| E[结束]
    D --> F[随机生成新的cron时间]
    F --> G[更新workflow文件]
    G --> H[提交到仓库]
    H --> I[下次按新时间执行]
