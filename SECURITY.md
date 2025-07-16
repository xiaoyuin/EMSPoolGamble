# EMS Pool Gamble 安全配置说明

## 管理员密码设置

为了防止恶意访问，系统已为以下关键操作添加了管理员验证：

- **删除对战记录** (`/delete_record`)
- **结束场次** (`/end_session`)
- **删除场次** (`/delete_session`)
- **玩家重命名** (`/player/*/rename`)

## 环境变量配置

### 1. 管理员密码 (必需)
```bash
# 设置管理员密码（默认为 admin123，强烈建议修改）
export ADMIN_PASSWORD="your_secure_password_here"
```

### 2. CSRF 保护密钥 (推荐)
```bash
# 设置CSRF保护密钥（用于防止跨站请求伪造）
export CSRF_SECRET_KEY="your_csrf_secret_key_here"
```

### 3. IP 白名单 (可选)
```bash
# 设置允许访问的IP地址列表（用逗号分隔，如果不设置则允许所有IP）
export ALLOWED_IPS="192.168.1.100,10.0.0.50,127.0.0.1"
```

### 4. Flask 会话密钥 (推荐)
```bash
# Flask 会话密钥（用于session加密）
export SECRET_KEY="your_flask_secret_key_here"
```

## Windows 环境设置示例

### PowerShell
```powershell
$env:ADMIN_PASSWORD="MySecurePassword123"
$env:CSRF_SECRET_KEY="csrf_key_12345"
$env:SECRET_KEY="flask_secret_key_67890"
# 可选：设置IP白名单
$env:ALLOWED_IPS="127.0.0.1,192.168.1.100"

# 然后启动应用
python app.py
```

### Command Prompt
```cmd
set ADMIN_PASSWORD=MySecurePassword123
set CSRF_SECRET_KEY=csrf_key_12345
set SECRET_KEY=flask_secret_key_67890
REM 可选：设置IP白名单
set ALLOWED_IPS=127.0.0.1,192.168.1.100

REM 然后启动应用
python app.py
```

## Linux/macOS 环境设置示例

```bash
export ADMIN_PASSWORD="MySecurePassword123"
export CSRF_SECRET_KEY="csrf_key_12345"
export SECRET_KEY="flask_secret_key_67890"
# 可选：设置IP白名单
export ALLOWED_IPS="127.0.0.1,192.168.1.100"

# 然后启动应用
python app.py
```

## Azure 部署环境变量设置

在 Azure App Service 中，可以通过以下方式设置环境变量：

1. 在 Azure 门户中，导航到你的 App Service
2. 选择 "配置" > "应用程序设置"
3. 添加以下键值对：
   - `ADMIN_PASSWORD`: `your_secure_password`
   - `CSRF_SECRET_KEY`: `your_csrf_secret_key`
   - `SECRET_KEY`: `your_flask_secret_key`
   - `ALLOWED_IPS`: `ip1,ip2,ip3`（可选）

## 安全特性

### 1. 管理员认证
- 关键操作需要输入管理员密码
- 认证状态会保存7天（可以随时退出）
- 在首页显示管理员模式状态

### 2. CSRF 保护
- 所有POST表单都包含CSRF token
- 防止跨站请求伪造攻击
- **重要**：所有删除操作都改为POST请求，避免GET请求的CSRF风险

### 3. IP 白名单（可选）
- 可以限制只有特定IP地址才能访问管理功能
- 适用于内网环境或固定办公场所

## 安全修复说明

### CSRF 防护升级
在v1.5.0版本中，我们发现了一个重要的安全漏洞：删除场次操作使用GET请求，容易受到CSRF攻击。恶意脚本可以通过简单的URL访问来删除场次，例如：

```html
<!-- 恶意页面可以通过图片标签触发删除 -->
<img src="http://your-app.com/delete_session/session_id" style="display:none">
```

**修复措施**：
1. 将删除场次操作从GET请求改为POST请求
2. 添加CSRF token验证
3. 所有删除操作都需要表单提交，而不是简单的链接点击

## 使用说明

1. **首次访问管理功能**：系统会要求输入管理员密码
2. **认证成功后**：在首页顶部会显示"管理员模式已启用"
3. **退出管理模式**：点击"退出管理员模式"链接
4. **密码安全**：请使用强密码，不要使用默认密码 `admin123`

## 注意事项

- 如果没有设置 `ADMIN_PASSWORD` 环境变量，系统将使用默认密码 `admin123`
- 在生产环境中，请务必设置强密码
- 建议定期更换管理员密码
- IP白名单为空时，将允许所有IP访问（仅密码保护）
