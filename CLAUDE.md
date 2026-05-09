# CLAUDE.md

> 给 Claude / 其他 AI 编程助手看的项目说明。维护者请保持简洁、可操作。

## 这是什么项目

**EMS Pool**（仓库代号 `EMSPoolGamble`）是一个多人台球计分 Flask Web 应用，
用于在小团体内（微软苏州 EMS 同事）记录每周的台球对局、胜负、特殊胜利
和成就。**只有一个真实部署**（Azure App Service），主要用户在手机浏览器上访问。

## 当前版本

`app/__init__.py` 里的 `APP_VERSION` 是真相来源。当前 **v1.9.0**（2026-05-09）。

每次发布版本时同时更新：
1. `app/__init__.py` 的 `APP_VERSION` 与 `VERSION_DATE`
2. `CHANGELOG.md` 顶部新增段落
3. `README.md` 顶部 "当前版本" 一行（如适用）

## 技术栈速查

| 层 | 实现 | 重要文件 |
|---|---|---|
| Python | 3.12 | `requirements.txt` |
| Web 框架 | Flask 3.1.1 | `app.py`（入口）、`app/` 包 |
| 模板 | Jinja2（SSR） | `templates/` |
| 数据库 | **SQLite**，文件 `ems_pool_gamble.db` | `app/database.py`（DAO） |
| 前端 | 服务端渲染 + 原生 HTML/CSS/JS + Chart.js（趋势图） | `templates/`、`static/` |
| 测试 | 暂无自动化测试套件 | — |

⚠️ **常见误解**：早期文档说"JSON 持久化"，**已不再适用**。所有持久数据都在
SQLite 里。`data.json.backup` 只是历史迁移残留，不要把它当作活跃数据源。

## 架构

```
app.py                       # 启动入口：create_app() + 数据库初始化
app/
├── __init__.py              # APP_VERSION / APP_NAME / DEFAULT_SCORE_OPTIONS
├── database.py              # SQLite 直接操作的 DAO 层
├── models.py                # 业务模型 wrapper（薄薄一层，模板里通过它取数据）
├── main_routes.py           # /, /history, /session_detail, /tournament 占位
├── game_routes.py           # /game, /add_score, /add_special_score 等
├── player_routes.py         # /player/<id>, /player/<id>/rename
├── achievement_routes.py    # /achievements + /achievement/<type>
├── security.py              # 管理员认证 / CSRF / IP 白名单
└── utils.py
templates/
├── base.html                # 全站骨架（v1.9.0 新增）
├── index.html               # 已迁移到 base.html
├── tournament.html          # 已迁移到 base.html
├── game.html / history.html / session_detail.html / player_detail.html / achievements.html
└── achievements/*.html      # 各成就独立详情页
static/
├── css/main.css             # 全站共享样式（v1.9.0 新增）
├── js/main.js               # 全站共享 JS（含 EMS.showToast / EMS.ajaxSubmit）
├── js/chart.js              # Chart.js 离线副本
└── icons/
```

## 进行中的迁移（v1.9.0 起）

**前端正在分阶段从"每页内联样式 / 内联脚本"迁移到 `base.html` + `main.css` + `main.js`。**

- ✅ 已迁移：`index.html`, `tournament.html`
- ⏳ **未迁移**：`game.html`, `history.html`, `session_detail.html`, `player_detail.html`, `achievements.html`, 以及 `templates/achievements/` 下 7 个成就页

未迁移页面**继续保留各自的内联 `<style>` 和内联 `<script>`**（包括重复实现的 `convertUtcToLocal`、Toast、按钮颜色、卡片样式等）。这是已知技术债，将来会做一次"CSS 整理收尾"统一处理。在那之前：

- 改未迁移页面的样式 → 直接改它的内联 `<style>`，**不要为单个页面新增 main.css 类**（避免半半拉拉）
- 改已迁移页面（index/tournament）→ 优先在 `main.css` 里加类、`extra_styles` block 里写页面专属

## 重要约定

### 1. 所有 UI 文字用 "EMS Pool"，不要再写 "EMS Pool Gamble"
- 仓库名是 EMSPoolGamble，但用户可见标题已统一精简为 "EMS Pool"
- README/CLAUDE.md/CHANGELOG 这类文档文件 OK，但 `<title>`、`<h2>`、footer 版权、APP_NAME、邮件标题等都用 "EMS Pool"

### 2. 计分入口已经走 AJAX，不要回退到表单跳转
- `add_score` / `add_special_score` 检测 `X-Requested-With: XMLHttpRequest` 头返回 JSON `{ok, message}`
- 普通表单 POST 仍按原 flash + redirect 兼容（不要删这个分支，向后兼容用得着）
- 前端用 `EMS.ajaxSubmit({...})` 或直接 `fetch + new FormData(form)`，成功后调用 `refreshGameData()` 局部刷新

### 3. 玩家详情时间筛选协议
- URL: `?month=YYYY-MM` / `?month=all`（默认） / `?month=custom&start_date=...&end_date=...`
- `start_date` / `end_date` 用 ISO `YYYY-MM-DDTHH:MM` 格式（`<input type="date">` + 客户端补全 `T00:00` / `T23:59`）
- 这个协议和 `/history` 完全一致，未来如果做新的"按时间筛选"页面请复用同一协议
- 顶部"小金/大金"光环按**全时段身份**显示，不随筛选窗口变；其它派生统计全部按窗口重算

### 4. 数据库迁移
- `app/database.py` 的 `_init_database()` 在启动时跑，已支持 `loser_id2`（多败者）等字段
- 新加列要走 ADD COLUMN + 默认值，不要写"破坏性"迁移

### 5. 时间显示
- DB 存 UTC（ISO 字符串）
- 模板上输出时给元素加 `data-utc-time="..."` 属性，由 `static/js/main.js` 的 `EMS.convertUtcToLocal()` 在浏览器端转本地时区

### 6. 安全
- 管理员模式开关靠 session（`security.py`）
- 关键操作装饰器：`@require_admin_auth` + `@require_csrf_protection`
- 不要在新路由里直接读取 `request.form` 后做删除/修改而不加保护

## 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ADMIN_PASSWORD=x python app.py    # 默认 5000 端口
```

数据库文件 `ems_pool_gamble.db` 在仓库根目录，**不要 commit**。已经在 `.gitignore` 里了。

## 提交规范

按现状（项目维护者偏好）：

- commit 主题用英文，能多解释就多解释（这个项目里不少 commit body 写了为什么这么改）
- 同一 PR 不混杂"重构"和"新功能"，分开 commit
- 推送用 SSH（remote 已设置为 `git@github.com:xiaoyuin/EMSPoolGamble.git`）

## 未来工作清单（按优先级）

1. **CSS / 模板整理收尾** — 把剩余 7 个页面迁到 `base.html`，抽 `leaderboard-row`、`entity-badge`、`achievement-banner` 等组件类，删掉重复 CSS/JS
2. **终局之战赛事页** — 取代 `/tournament` 占位，加赛程 / 对阵 / 实时积分
3. **PWA** — 离线、桌面安装
4. **更多趋势图表** — 已有 player 累计分数曲线，可拓展月度对比、对手雷达图等

不在路线图（被否定过）：
- ❌ 切到 Node 后端（讨论过，结论是切了对实际痛点没帮助）
- ❌ 用 React/Vue 重写前端（过度方案；当前规模 Jinja2 + 渐进 AJAX 够用）

## 在做改动前的快速 checklist

- [ ] 这个改动应该改 `main.css` 还是页面内联？看上面"进行中的迁移"那段
- [ ] 用户可见文案里是不是用 "EMS Pool"（不带 Gamble）
- [ ] 表单提交需不需要 CSRF / admin 装饰器
- [ ] 时间字段是不是 UTC 存 + `data-utc-time` 输出
- [ ] 改了版本号？同步 `CHANGELOG.md`、可能还要 `README.md`

---

最后更新：v1.9.0（2026-05-09）
