# 🎱 EMS Pool

> 仓库代号：**EMSPoolGamble**

一个功能完整的多人台球计分 Python Flask Web 应用，支持移动端浏览器访问。

**当前版本：[v1.9.0](./CHANGELOG.md)（2026-05-09）**

## ✨ 核心功能

### 🎮 游戏管理
- **场次管理**：创建、进行、结束、查看、删除的完整生命周期
- **简化流程**：无需登录，任何人可直接参与游戏
- **智能计分**：1–10 分 + 特殊分数（小金 8/14、大金 10/20），支持双败者模式
- **批量玩家管理**：多选批量添加玩家，新建玩家弹窗带键盘快捷键
- **🆕 计分不刷新整页（v1.9.0）**：所有计分入口改走 AJAX，提交后顶部 toast 提示并就地刷新分数表

### 👥 玩家系统
- **唯一档案**：每个玩家拥有唯一 `player_id`，重命名后历史记录自动同步
- **玩家详情页**：个人统计、对手分析、累计分数趋势图（Chart.js）
- **🆕 时间筛选（v1.9.0）**：玩家详情支持按月份 / 自定义日期范围过滤，所有派生数据（统计、对手、趋势、特殊胜利计数）随窗口重算
- **全站玩家跳转**：任何页面点击玩家名字都能进入详情
- **特殊胜利高亮**：小金（橙色）/ 大金（紫色）光环全站可见

### 🏆 成就系统
- **6 种成就**：小金、大金、小金达人、大金达人、大金传奇、大吃一金（负面）
- **独立详情页**：每种成就有自己的排行榜、达成统计、达成历史
- **统一主题配色**：每类成就独立色系；负面成就用红色边框区分
- **多败者记录展示**：大金支持 "胜 A + B" 双败者形式

### 📊 统计分析
- **个人统计**：总记录、有效对局、胜率（排除 1 分）、特殊胜利次数
- **1 分收益**：送出 / 收到 1 分次数与净收益
- **对手分析**：与每个对手的胜负、胜率、总分差
- **历史排行榜**：全局月份 / 自定义日期范围切换，全时段或单月聚合分数 + 胜率

### 🆕 终局之战入口（v1.9.0）
- 首页加入「EMS 微软苏州第三届『终局之战』杯」赛事入口卡片
- `/tournament` 当前为占位页，赛程 / 对阵 / 实时积分将在后续版本上线

### 🔒 安全保护
- **管理员密码认证**：删除场次 / 删除记录 / 重命名玩家等关键操作需要管理员模式
- **CSRF 保护**：所有表单都包含 CSRF token
- **IP 白名单**（可选）：通过 `ALLOWED_IPS` 环境变量限制访问

## 🏗️ 技术栈

| 层 | 实现 |
|---|---|
| **后端** | Flask 3.1.1 + Werkzeug 3.1.3 + Jinja2 |
| **数据库** | SQLite（`ems_pool_gamble.db`），自动初始化与迁移 |
| **前端** | 服务端渲染（Jinja2）+ 原生 HTML/CSS/JS + Chart.js |
| **前端基础设施（v1.9.0）** | `templates/base.html`、`static/css/main.css`、`static/js/main.js`（含 `EMS.showToast` / `EMS.ajaxSubmit` 工具） |
| **部署** | Azure App Service（Python 3.12） |

> v1.9.0 起前端正在分阶段从"每页内联样式"迁移到 base.html + 共享 CSS/JS。首页 `index.html` 与新增的占位 `tournament.html` 已迁移；其余页面保留各自内联样式，将在后续 CSS 整理轮次中迁移。

## 📁 项目结构

```
EMSPoolGamble/
├── app.py                      # 启动入口（创建 Flask 应用）
├── app/                        # 后端模块化包
│   ├── __init__.py             # APP_VERSION / APP_NAME / DEFAULT_SCORE_OPTIONS
│   ├── database.py             # SQLite 操作（场次、玩家、计分、成就、统计）
│   ├── models.py               # 业务模型层 wrapper
│   ├── main_routes.py          # 首页 / 历史 / 场次详情 / 终局之战占位
│   ├── game_routes.py          # 游戏界面、计分（含 AJAX 分支）
│   ├── player_routes.py        # 玩家详情（含月份筛选）、重命名
│   ├── achievement_routes.py   # 成就系统所有路由
│   ├── security.py             # 管理员认证 / CSRF / IP 白名单
│   └── utils.py                # 工具函数
├── templates/
│   ├── base.html               # 全站骨架（v1.9.0）
│   ├── index.html              # 首页（已迁移到 base.html）
│   ├── tournament.html         # 终局之战占位页（v1.9.0）
│   ├── game.html               # 游戏 / 计分界面
│   ├── history.html            # 历史 + 全局排行榜
│   ├── session_detail.html     # 场次详情
│   ├── player_detail.html      # 玩家详情（含时间筛选 v1.9.0）
│   ├── achievements.html       # 旧入口（保留）
│   └── achievements/           # 各成就详情页
│       ├── index.html
│       ├── small_gold.html / small_gold_master.html
│       ├── big_gold.html / big_gold_master.html / big_gold_legend.html
│       └── gold_loser.html
├── static/
│   ├── css/main.css            # 全站共享样式（v1.9.0）
│   ├── js/main.js              # 全站共享 JS（含 toast / ajaxSubmit）
│   ├── js/chart.js             # Chart.js 离线副本
│   └── icons/                  # 应用图标
├── ems_pool_gamble.db          # SQLite 数据库（运行时生成）
├── requirements.txt
├── CHANGELOG.md
├── PROJECT_STATUS.md
└── README.md
```

## 🚀 快速开始

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. （推荐）设置安全环境变量

```bash
# Linux / macOS
export ADMIN_PASSWORD="your_secure_password"
export CSRF_SECRET_KEY="your_csrf_key"
export SECRET_KEY="your_flask_secret"

# Windows PowerShell
$env:ADMIN_PASSWORD="your_secure_password"
$env:CSRF_SECRET_KEY="your_csrf_key"
$env:SECRET_KEY="your_flask_secret"
```

> 未设置时使用默认管理员密码 `admin123`（仅适合本地试用）。完整安全配置见 [SECURITY.md](./SECURITY.md)。

### 3. 启动

```bash
python app.py
```

浏览器访问 <http://localhost:5000>。

## ☁️ 部署到 Azure

### 使用 Azure Portal

1. 在 [Azure Portal](https://portal.azure.com) 创建 Web App
2. 选择运行时 **Python 3.12**
3. 配置部署源（GitHub Actions / 本地 git / Zip Deploy 均可）
4. 配置环境变量（Settings → Configuration）：
   - `SECRET_KEY` — Flask session 密钥（建议随机生成）
   - `ADMIN_PASSWORD` — 管理员密码
   - `CSRF_SECRET_KEY` — CSRF 保护密钥
   - `ALLOWED_IPS`（可选）— IP 白名单，逗号分隔
   - `FLASK_DEBUG=False`

### 使用 Azure CLI

```bash
az login
az group create --name myResourceGroup --location eastus
az appservice plan create --name myAppServicePlan --resource-group myResourceGroup --sku B1 --is-linux
az webapp create --resource-group myResourceGroup --plan myAppServicePlan --name myWebAppName --runtime "PYTHON|3.12"
az webapp config appsettings set --resource-group myResourceGroup --name myWebAppName \
    --settings SECRET_KEY="..." ADMIN_PASSWORD="..." CSRF_SECRET_KEY="..." FLASK_DEBUG="False"
```

## 🎯 使用流程

1. **进入主页**：查看进行中的场次、终局之战入口、最近结束的场次
2. **创建场次**：点"快速创建 - 4月29日下午场"按钮（场次名按本地时区自动生成）
3. **加入与计分**：进入场次后批量添加玩家，选择 胜者 / 败者 / 分数 / 游戏种类（普胜 / 双吃 / 小金 / 大金）
4. **记录与刷新**：点"记录"提交 → 顶部 toast 即时反馈，分数表就地更新（不再整页刷新）
5. **结束场次**：完赛后结束，可在历史页和场次详情查看完整数据
6. **探索玩家**：点任意玩家名进入详情，**用月份下拉或自定义日期切换时间窗口**
7. **查看成就**：从底部"成就"链接进入，每种成就都有自己的排行榜

## 📜 版本历史

详见 [CHANGELOG.md](./CHANGELOG.md)。

最新里程碑：

- **v1.9.0**（2026-05-09）— 前端架构整理（base.html + main.css/js）、计分 AJAX、玩家详情时间筛选、终局之战入口、徽章换行修复、UI 标题精简
- **v1.8.4** — game 页面与历史自定义时间 UI 修复
- **v1.8.0–v1.8.3** — 成就系统、模块化架构、自定义筛选时间
- **v1.3.0** — 玩家系统重构、唯一 ID、玩家详情页

## 🔮 后续计划

- **终局之战赛事页**（取代 `/tournament` 占位）：赛程、对阵、实时积分
- **CSS 整理收尾**：把剩余页面全部迁移到 `base.html` + 抽组件类（`leaderboard-row`、`entity-badge`、`achievement-banner` 等），消除重复样式
- **PWA / 离线支持**
- **数据可视化增强**：更多趋势 / 对比图表

## 📄 许可证

MIT License — 详见 [LICENSE](./LICENSE)。

## 🤝 贡献

欢迎 Issues 和 Pull Requests。

## 📞 联系

- GitHub: [xiaoyuin/EMSPoolGamble](https://github.com/xiaoyuin/EMSPoolGamble)
- 项目状态：[PROJECT_STATUS.md](./PROJECT_STATUS.md)
- 完整版本历史：[CHANGELOG.md](./CHANGELOG.md)

---

**🎱 EMS Pool v1.9.0 — 现代化前端基础上线，玩家详情可按时间维度回溯。**
