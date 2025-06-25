# EMS Pool Gamble

这是一个多人台球计分 Python Flask Web App，支持移动端浏览器访问，具有完整的场次管理和详情查看功能。**现在使用 SQLite 数据库进行数据持久化**。

## 功能特点

- **数据库持久化**：使用 SQLite 数据库替代内存存储，确保数据安全性和持久性
- **完整的场次管理**：支持创建多个命名场次，每个场次独立计分
- **场次详情页**：专门的详情页展示完整的计分记录和玩家排名
- **主页概览**：显示进行中场次列表和最近结束的场次
- **安全的删除机制**：删除场次按钮移至详情页，避免误操作
- **灵活的玩家管理**：支持动态添加玩家，无需预先注册，记住最近添加的玩家
- **用户身份**：用户可选择"玩家"或"观战者"身份参与
- **简化的计分系统**：分数范围为1-10的正整数，操作简单直观
- **直观的分数选择**：使用按钮平铺方式选择分数，胜者败者选择也为按钮形式
- **智能缓存**：自动记住用户上次使用的用户名
- **一体化记录结构**：所有计分记录统一管理，取消了局的概念
- **实时排名**：动态显示分数排名和详细历史记录查询
- **移动端友好**：简洁美观的响应式界面，适配各种设备
- **统一的UI设计**：所有页面使用一致的按钮和卡片样式
- **数据迁移支持**：自动从旧的 JSON 文件格式迁移到数据库

## 版本更新

### v2.0.0 (2025-06-25)
- **重大更新**：使用 SQLite 数据库替代内存存储和 JSON 文件
- 添加数据库模型和服务层
- 支持从旧版本 JSON 数据自动迁移
- 提升数据安全性和并发性能
- 优化了代码架构，提高了可维护性

## 快速开始

### 方法一：使用启动脚本（推荐）

```bash
python start.py
```

启动脚本会自动：
1. 检查并安装依赖包
2. 初始化数据库
3. 迁移旧数据（如果存在 data.json 文件）
4. 启动应用

### 方法二：手动安装

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 初始化数据库（首次运行）：
   ```bash
   python -c "from app import app, db; app.app_context().push(); db.create_all()"
   ```

3. 数据迁移（如果有旧的 data.json 文件）：
   ```bash
   python migrate_data.py
   ```

4. 本地运行：
   ```bash
   python app.py
   ```

5. 在浏览器访问 http://localhost:5000

## 数据库结构

项目使用 SQLite 数据库，包含以下表：

- `game_sessions`: 游戏场次信息
- `players`: 玩家信息
- `viewers`: 观众信息
- `player_scores`: 玩家分数
- `game_records`: 游戏记录
- `recent_players`: 最近使用的玩家名

数据库文件默认保存为 `ems_pool_gamble.db`。

## 部署说明

### 环境变量配置

- `SECRET_KEY`: Flask 应用密钥（生产环境必须设置）
- `DATABASE_URL`: 数据库连接字符串（默认使用 SQLite）
- `PORT`: 应用运行端口（默认5000）
- `FLASK_DEBUG`: 调试模式（生产环境设为"False"）
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
   - 玩家可以记录每次计分结果（选择胜者、败者、分数1-10）
   - 胜者、败者和分数选择均使用按钮形式，点击即可选中
   - 可以动态添加新玩家到当前场次中，支持最近玩家快捷添加
   - 观战者只能查看，不能操作
   - 可以随时结束本场比赛
5. **查看详情**：
   - 从主页或历史记录页面点击"查看详情"进入场次详情页
   - 详情页显示完整的玩家排名表格和所有计分记录
   - 已结束的场次可以在详情页删除
6. **历史查看**：查看所有场次的概要信息和总排名

## 最新功能亮点

- **场次详情页**：新增专门的详情页面，展示完整的场次信息和计分记录
- **安全删除**：删除场次功能移至详情页面，放在单独卡片中，避免主页误操作
- **统一样式**：所有按钮使用一致的宽度和样式，提升用户体验
- **最近玩家**：记住最近添加的玩家，快捷添加功能
- **记录结构简化**：取消局的概念，所有计分直接记录在场次中
- **按钮式选择**：胜者、败者、分数选择全部使用按钮，移动端友好
- **响应式布局**：退出登录等功能按钮独立放置，避免误触

## 主要文件

- `app.py`：主应用逻辑，包含路由和数据处理
- `templates/`：前端页面模板
  - `index.html`: 首页，显示场次列表和创建新场次
  - `game.html`: 游戏主界面，包含计分和玩家管理
  - `history.html`: 历史记录查询页面
  - `session_detail.html`: 场次详情页面，显示完整计分记录
- `requirements.txt`：依赖列表
- `data.json`：数据持久化存储（自动生成）

## 开发注意事项

- 使用 JSON 文件数据持久化，重启会自动保存/加载到 data.json
- 兼容旧数据格式，自动升级数据结构
- 可扩展为使用数据库（如SQLite, PostgreSQL或Azure CosmosDB）
- 默认监听所有网卡 (0.0.0.0)，方便局域网内测试

## 已完成的功能优化

- **多轮界面优化**：按钮布局、卡片设计、响应式适配
- **数据兼容性**：自动处理旧数据格式升级
- **用户体验**：统一的按钮样式、防误操作设计
- **场次管理**：完整的创建、查看、删除流程
- **移动端适配**：触摸友好的界面设计

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交 Issues 和 Pull Requests 来改进这个项目！

## 联系方式

- GitHub: [xiaoyuin/EMSPoolGamble](https://github.com/xiaoyuin/EMSPoolGamble)
- 如需进一步开发或部署指导，请告知！
