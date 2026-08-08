# 🎱 EMS Pool

> 仓库代号：**EMSPoolGamble**

面向小团体的多人台球计分 Flask Web 应用，支持手机浏览器访问、组织隔离、普通对局、特殊记录、玩家统计和单淘汰赛事。

**当前版本：[v1.13.0](./CHANGELOG.md)（2026-08-08）**

## ✨ 核心功能

### 🏢 多组织

- 每个组织拥有独立的玩家、场次、计分记录、排行榜、特殊记录、退役状态和赛事
- 组织页面使用 `/o/<组织短标识>/...`；资源 ID 即使泄露，也不能跨组织读取或修改
- 根页面不公开组织目录，通过组织名称/短标识进入
- 浏览器本地保存“之前进入过”的组织，记录不会上传服务器，也不会跨设备同步
- 创建组织时自动生成拼音 URL：如“车联天下”→ `/o/cheliantianxia/`
- 现有历史数据在 v1.13.0 首次启动时整体迁移到 `/o/ems/`

### 🎮 游戏与计分

- 创建、加入、结束、查看和删除场次
- 普通访客无需登录即可进入组织、加入场次和计分
- 支持 1v1、1胜2败、2胜1败、小金、大金与双吃
- 计分使用 AJAX，成功后局部刷新比分
- 删除计分记录时自动反向恢复各玩家分数
- 游戏页和场次详情包含“比分流向”关系图

### 👥 玩家与统计

- 同名玩家可以分别存在于不同组织；组织内每个玩家拥有稳定 UUID
- 玩家详情包含胜负、有效胜率、对手分析、累计分数趋势和赛事历史
- 历史页支持月份与自定义时间范围筛选
- 支持小金、大金、达人/传奇、大吃一金、好兄弟、有难同当和榜上有名
- 玩家可由管理员退役或复出

### 🏆 单淘汰赛事

- 组织内独立创建赛事、报名、设置种子、随机预览和生成 bracket
- 支持轮空、每轮独立 best-of-N、逐局录分、一次性录分、撤回和重置
- 支持比赛视频链接和玩家赛事历史

### 📲 PWA

- 每个组织拥有独立 manifest `start_url` 与 `scope`
- 可安装到手机主屏幕，安装后直接返回对应组织
- 当前 Service Worker 不缓存业务数据，因此不提供离线操作

## 🔐 权限模型

| 身份 | 权限 |
|---|---|
| 普通访客 | 查看组织数据、创建/加入场次、公开计分、录入赛事局分 |
| 组织管理员 | 管理本组织玩家、场次、记录和赛事 |
| 超级管理员 | 管理任意已进入的组织 |

- 新组织创建时设置独立管理员密码，只保存 Werkzeug 密码哈希
- 部署环境变量 `ADMIN_PASSWORD` 是超级管理员凭据，同时用于 EMS 组织
- 管理员会话按组织绑定；另一个组织的管理员权限不会被复用
- 详细安全配置见 [SECURITY.md](./SECURITY.md)

## 🏗️ 技术栈

| 层 | 实现 |
|---|---|
| 后端 | Python 3.12、Flask 3.1.1、Werkzeug 3.1.3 |
| 数据库 | SQLite，直接 DAO + 启动迁移 |
| 前端 | Jinja2 SSR、原生 HTML/CSS/JS、Chart.js、vis-network |
| 拼音短标识 | pypinyin |
| 测试 | 标准库 `unittest` + 临时 SQLite |
| 部署 | Azure App Service |

## 📁 结构

```text
app.py                         # App factory、tenant Blueprint、WSGI 入口
app/
├── tenancy.py                 # 多组织 schema、slug、EMS 迁移
├── database.py                # 组织化 SQLite DAO
├── models.py                  # 业务 wrapper
├── organization_routes.py     # 根组织入口、创建、旧 URL 网关
├── security.py                # 组织管理员 / 超级管理员 / CSRF
├── main_routes.py             # 组织首页、历史、场次详情、PWA
├── game_routes.py             # 玩家加入与计分
├── player_routes.py           # 玩家详情与管理
├── achievement_routes.py      # 特殊记录
└── tournament.py / tournament_routes.py
templates/
├── organization_portal.html   # 根组织入口 + 本地最近组织
├── organization_new.html
├── admin_login.html
├── base.html                  # 已迁移页面共享骨架
└── ...                        # 游戏、历史、玩家、成就、赛事页面
static/
├── css/main.css
├── js/main.js / chart.js
└── icons/
tests/test_multi_org.py        # 迁移、隔离、权限和路由回归测试
```

## 🚀 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="local-dev-secret"
export ADMIN_PASSWORD="local-super-admin-password"
python app.py
```

浏览器访问 <http://localhost:5000>。首次启动会创建 EMS 组织；如果数据库是旧版单组织结构，会自动迁移到 EMS。

### 运行测试

```bash
python -m unittest discover -s tests -v
```

测试在临时 SQLite 数据库运行，不会修改仓库根目录的 `ems_pool_gamble.db`。

## 🗄️ v1.13.0 数据库迁移

升级前必须：

1. 停止写入并只保留一个应用实例执行迁移
2. 复制 Azure `/home/data/ems_pool_gamble.db` 到 App Service 之外并验证备份可读
3. 先用生产数据库副本运行新版本与测试
4. 确认 `SECRET_KEY` 和 `ADMIN_PASSWORD` 已正确配置

首次启动将：

- 建立固定 `EMS` 组织
- 保留所有原玩家、场次、记录和赛事 ID
- 将所有旧数据归入 EMS
- 重建组织复合外键和索引
- 执行 `PRAGMA foreign_key_check`
- 写入幂等的 `schema_migrations` 记录

如果迁移或上线验证失败，停止应用并同时恢复旧应用版本与迁移前数据库备份。不要只回滚代码后继续使用已经迁移的数据库。

## ☁️ Azure 配置

必需或强烈建议的应用设置：

```text
SECRET_KEY=<随机且长期稳定的 Flask session 密钥>
ADMIN_PASSWORD=<强超级管理员密码>
ALLOWED_IPS=<可选，逗号分隔的管理端 IP>
FLASK_DEBUG=False
```

Azure 环境下数据库默认位于 `/home/data/ems_pool_gamble.db`。

## 使用流程

1. 从根页面输入组织名称/短标识，或创建新组织
2. 在组织首页创建或进入场次
3. 加入已有玩家；管理员可以创建新玩家
4. 选择胜者、败者和分数进行 AJAX 计分
5. 从历史、玩家和特殊记录页面查看组织内统计
6. 从赛事入口创建和管理单淘汰赛

旧的 `/history`、`/game/<id>`、`/player/<id>` 等 GET 地址会先显示组织输入页，再进入该组织下的相同路径。旧写操作地址不兼容。

## 📜 版本历史

详见 [CHANGELOG.md](./CHANGELOG.md)。

## 🔮 后续计划

- 完成剩余页面的 `base.html` / 共享 CSS 与 JS 迁移
- 根据实际需求扩展离线 PWA
- 增加更多趋势与对比图表
- 继续完善安全默认配置、CSRF 一致性和数据查询性能

## 📄 许可证

MIT License — 详见 [LICENSE](./LICENSE)。
