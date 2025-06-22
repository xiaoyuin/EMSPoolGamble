# 台球计分工具 (EMS Pool Gamble)

这是一个可部署到 Azure 的多人台球计分Python Flask Web App，支持移动端浏览器访问。

## 功能特点

- **场次管理**：支持创建多个命名场次，每个场次独立计分
- **灵活的玩家管理**：支持动态添加玩家，无需预先注册
- **用户身份**：用户可选择"玩家"或"观战者"身份参与
- **简化的计分系统**：分数范围为1-10的正整数，操作简单直观
- **直观的分数选择**：使用按钮平铺方式选择分数，比下拉菜单更便捷
- **智能缓存**：自动记住用户上次使用的用户名
- **游戏结构**：按"场"与"局"两级结构记录，每场可进行多局比赛
- **实时排名**：动态显示分数排名和历史记录查询
- **移动端友好**：简洁美观的响应式界面，适配各种设备

## 快速开始

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 本地运行：
   ```bash
   python app.py
   ```

3. 在浏览器访问 http://localhost:5000

## 部署到 Azure

### 使用 Azure Portal

1. 在 [Azure Portal](https://portal.azure.com) 创建一个 Web App 服务
2. 选择运行时堆栈为 Python 3.12
3. 配置部署选项，可以选择GitHub Actions或其他CI/CD方式
4. 设置环境变量:
   - `SECRET_KEY`: 生产环境的密钥（建议随机生成）
   - `PORT`: 应用运行端口（默认5000）
   - `FLASK_DEBUG`: 生产环境设为"False"

### 使用 Azure CLI

```bash
# 登录Azure
az login

# 创建资源组
az group create --name myResourceGroup --location eastus

# 创建App Service计划
az appservice plan create --name myAppServicePlan --resource-group myResourceGroup --sku B1 --is-linux

# 创建Web App
az webapp create --resource-group myResourceGroup --plan myAppServicePlan --name myWebAppName --runtime "PYTHON|3.12"

# 部署代码
az webapp deployment source config --name myWebAppName --resource-group myResourceGroup --repo-url https://github.com/yourusername/EMSPoolGamble --branch main

# 设置环境变量
az webapp config appsettings set --resource-group myResourceGroup --name myWebAppName --settings SECRET_KEY="your-secret-key" FLASK_DEBUG="False"
```

## 使用流程

1. **进入主页**：查看当前正在进行的场次列表，或创建新场次
2. **创建场次**：输入场次名称（如"周末台球赛"），创建新的比赛场次
3. **加入场次**：输入用户名，选择身份（玩家/观战者），加入已有场次
4. **游戏中**：
   - 玩家可以记录每局比赛结果（选择胜者、败者、分数1-10）
   - 使用按钮平铺方式选择分数，点击即可选中
   - 可以动态添加新玩家到当前场次中
   - 观战者只能查看，不能操作
5. **局数管理**：每局结束后可点击"开始下一局"继续记录
6. **场次结束**：玩家可以选择"结束本场"完成当前场次
7. **历史查看**：查看所有场次的详细记录和总排名

## 新功能亮点

- **场次命名**：每个场次都可以有独特的名称，便于识别和管理
- **主页场次列表**：清晰显示所有正在进行的场次，支持快速加入
- **游戏中添加玩家**：无需预先注册，可在游戏过程中临时添加新玩家
- **简化分数系统**：只使用1-10的正整数，去除负数，更符合台球计分习惯
- **按钮式分数选择**：替代下拉菜单，使用网格布局的按钮，点击更便捷
- **用户名缓存**：自动记住上次使用的用户名，提升用户体验

## 主要文件

- `app.py`：主应用逻辑，包含路由和数据处理
- `templates/`：前端页面模板
  - `index.html`: 首页，显示场次列表和创建新场次
  - `game.html`: 游戏主界面，包含计分和玩家管理
  - `history.html`: 历史记录查询页面
- `requirements.txt`：依赖列表
- `data.json`：数据持久化存储（自动生成）

## 开发注意事项

- 默认使用内存数据结构存储，重启会自动保存/加载到data.json
- 可扩展为使用数据库（如SQLite, PostgreSQL或Azure CosmosDB）
- 默认监听所有网卡 (0.0.0.0)，方便局域网内测试

## 后续功能计划

- 添加用户账号系统
- 支持多场次并行进行
- 添加撤销操作功能
- 支持分数统计和图表展示
- 增加数据导出功能

## 许可证

MIT

如需进一步开发或部署指导，请告知！
