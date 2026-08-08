# CLAUDE.md

> 给 Claude / 其他 AI 编程助手看的项目说明。维护者请保持简洁、可操作。

## 项目定位

**EMS Pool**（仓库代号 `EMSPoolGamble`）是面向小团体的多人台球计分 Flask Web 应用，主要用户通过手机浏览器访问。只有一个真实部署（Azure App Service），但应用从 v1.13.0 起支持多个相互隔离的组织。

## 当前版本

`app/__init__.py` 的 `APP_VERSION` 是真相来源。当前 **v1.13.0**（2026-08-08）。

发布时同步更新：

1. `app/__init__.py` 的 `APP_VERSION` / `VERSION_DATE`
2. `CHANGELOG.md` 顶部版本段落
3. `README.md` 的当前版本

## 技术栈

| 层 | 实现 | 重要文件 |
|---|---|---|
| Python | 3.12 | `requirements.txt` |
| Web | Flask 3.1.1、Jinja2 SSR | `app.py`, `app/*_routes.py` |
| 数据库 | SQLite 直接 DAO | `app/database.py`, `app/tenancy.py` |
| 前端 | 原生 HTML/CSS/JS、Chart.js、vis-network | `templates/`, `static/` |
| 测试 | 标准库 unittest + 临时 SQLite | `tests/test_multi_org.py` |

所有持久数据在 SQLite。`data.json.backup` 只是历史迁移残留，不是活跃数据源。

## 架构

```text
app.py                         # app factory、tenant Blueprint、WSGI
app/
├── tenancy.py                 # 目标 schema、组织 slug、EMS 迁移
├── database.py                # org_id-first DAO
├── models.py                  # 业务 wrapper
├── organization_routes.py     # 根入口、创建组织、旧 URL 网关
├── security.py                # 组织管理员 / 超级管理员 / CSRF
├── main_routes.py             # 首页、历史、场次详情、PWA
├── game_routes.py             # 玩家加入与计分
├── player_routes.py           # 玩家详情与管理
├── achievement_routes.py      # 特殊记录
├── tournament.py              # 赛事领域与 SQL
└── tournament_routes.py
templates/
├── organization_portal.html / organization_new.html
├── admin_login.html
├── base.html / index.html / tournament_*.html
├── game.html / history.html / session_detail.html / player_detail.html
└── achievements/*.html
```

## 多组织硬约束

### 路由上下文

- 所有业务 canonical URL 位于 `/o/<org_slug>/...`
- tenant Blueprint 在 handler 前解析组织到 `g.organization`
- 根 `/` 只提供组织名称/slug 输入与创建入口，不得返回服务端组织目录
- “之前进入过”只保存在 localStorage，不是授权来源
- 旧只读 URL 可显示组织选择网关；不要恢复旧写操作 URL，也不要默认猜 EMS

### 数据访问

- 所有玩家、场次、计分、统计、成就、退役和赛事 DAO 必须显式接收 `org_id` 首参
- entity ID 查询、UPDATE 和 DELETE 必须同时限定 `org_id`
- join/subquery 必须保持组织条件；禁止先做全局查询再在 Python 层过滤
- 不要恢复 `SessionsProxy` / `PlayersProxy` 之类隐藏组织上下文的全局代理
- 跨组织资源与不存在资源统一按 404/空结果处理，不泄露归属
- 玩家名称只要求组织内唯一；同名玩家可存在于不同组织

### 数据库迁移

- 新迁移记录到 `schema_migrations` 并保持幂等
- 连接必须启用 `PRAGMA foreign_keys = ON`
- v1.13.0 已因复合外键和唯一约束重建核心表；以后优先使用非破坏性迁移，但约束变化可在备份、事务、预检、回滚和测试齐全时重建
- 生产迁移前必须备份 Azure `/home/data/ems_pool_gamble.db`，单实例执行，并在生产副本上演练
- 测试迁移只能使用临时库或复制品，绝不直接修改仓库数据库

## 权限模型

- 公开访客可浏览、创建/加入场次、计分和录入赛事局分
- 新组织保存独立管理员密码 hash
- `ADMIN_PASSWORD` 是全站超级管理员凭据，同时管理 EMS
- 管理判断使用 `is_current_org_admin()` / `@require_admin_auth`，不得检查旧 `session['admin_authenticated']`
- `organization_admin_org_id` 必须等于当前 `g.organization['org_id']`；超级管理员可跨组织
- 写操作按现有约定使用 `@require_csrf_protection`，新路由不得绕过

## 前端约定

### UI 名称

所有用户可见文字使用 **EMS Pool**，不要写 “EMS Pool Gamble”。仓库和文档名称可以保留。

### AJAX 计分

- `add_score` / `add_special_score` / `add_reverse_double` 的 AJAX 分支返回 `{ok, message}`
- 普通 POST 的 flash + redirect 分支用于兼容，不能删除
- 成功后调用 `refreshGameData()` 局部刷新，不回退到整页计分跳转
- URL 必须由租户 `url_for('tenant....')` 或服务器下发的 JSON-safe 值生成，不手拼组织 ID

### 时间筛选

玩家详情与历史页复用：

- `?month=YYYY-MM`
- `?month=all`
- `?month=custom&start_date=...&end_date=...`
- 日期时间使用 `YYYY-MM-DDTHH:MM`
- 特殊胜利光环按该组织内全时段身份显示，其他统计按筛选窗口重算

### 模板迁移状态

`index.html` 与赛事模板使用 `base.html`。游戏、历史、场次详情、玩家详情和成就页仍保留大量内联 CSS/JS。

- 改未迁移页面样式：继续改其内联 `<style>`，不要为单页半迁移到 `main.css`
- 改已迁移页面：共享规则优先放 `main.css`，页面规则用 block
- 所有 tenant 页面需要记录 `_tenant_presence.html` 并使用租户 manifest/service worker

## 本地开发与验证

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
SECRET_KEY=x ADMIN_PASSWORD=x python app.py
python -m unittest discover -s tests -v
```

数据库文件 `ems_pool_gamble.db` 不得 commit。

功能验证优先使用临时数据库：

```bash
DATABASE_PATH=/tmp/ems-pool-test.db SECRET_KEY=x ADMIN_PASSWORD=x python app.py
```

## 提交规范

- commit 主题使用英文，必要时在 body 解释原因
- 不在同一 commit 混杂无关重构和新功能
- 推送使用 SSH remote

## 后续工作

1. 修复安全默认值与 CSRF/GET 状态变更等既有问题
2. 完成剩余模板的共享 CSS/JS 迁移
3. 优化排行榜和可选玩家查询的 N+1
4. 决定是否实现真正离线的 PWA
5. 增加更多趋势与对比图表

不在路线图：

- 切换 Node 后端
- 用 React/Vue 重写前端

---

最后更新：v1.13.0（2026-08-08）
