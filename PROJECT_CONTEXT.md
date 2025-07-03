# 项目上下文说明（Prompt for Agent）

本项目是一个可部署到 Azure 的 Python Flask Web App，主要用于多人台球计分，支持移动端浏览器访问。该应用已完成完整的开发，包含场次管理、详情查看、用户体验优化等功能。v1.6.0 版本实现了特殊胜利高亮系统与计分优化，提供完整的特殊胜利玩家高亮和最优的计分记录查看体验。

## 项目概述

EMS Pool Gamble 是一个功能完整的多人台球比赛计分系统，特别适合小团队或朋友圈内使用。经过 v1.6.0 特殊胜利高亮系统与计分优化，系统提供完整的场次管理、实时计分、详情查看、玩家档案管理和历史记录功能，特殊胜利玩家高亮显示，计分记录按时间降序显示，界面现代化美观，移动端体验优秀。

## 技术栈

- **后端**: Python 3.12 + Flask 3.1.1 + Werkzeug >=3.0.0
- **数据存储**: SQLite 数据库（v1.4.0 升级，完全替代JSON存储）
- **前端**: HTML + CSS + Jinja2 模板（响应式设计，适配移动端）
- **架构模式**: 模块化MVC架构（v1.3.4 重构）

## 主要功能

### 🎮 游戏管理（v1.5.0 优化）
- **完整的场次管理**：支持创建多个命名场次，每个场次可以有独特的名称
- **卡片布局重构**：玩家管理、计分面板、场次控制功能分工明确，层次清晰
- **快速添加玩家升级**：支持多选批量添加，动态按钮状态，选中数量实时显示
- **胜率智能显示**：快速添加按钮显示有效胜率（排除1分对局），新玩家显示"新手"
- **新建玩家交互优化**："+"号弹窗模式，支持ESC/外部点击关闭、回车提交
- **智能计分**：1-10分 + 特殊分数（14/20），支持两败者模式
- **界面美化**：按钮区域浅色背景、圆角设计、统一间距，提升视觉层次感

### 👥 玩家系统（v1.3.0 重构，v1.4.0 数据库升级）
- **独立档案**：每个玩家拥有唯一ID和完整档案
- **智能重命名**：支持更改显示名称，历史记录自动同步
- **玩家详情页**：专门页面展示个人统计、对手分析、历史记录
- **全局跳转**：所有页面的玩家名字均可点击查看详情
- **批量操作**：新增批量添加玩家功能，大幅提升操作效率

### 📊 统计分析（v1.3.0 新增，v1.4.0 优化）
- **个人统计**：总场次、胜局数、胜率、得分分布
- **对手分析**：与每个对手的详细对战记录和胜负关系
- **历史回顾**：按时间顺序展示所有参与的场次记录
- **排行榜系统**：全局排行榜和场次排行榜
- **有效胜率**：个人统计页面排除1分记录，避免误导性数据

### 🎨 用户体验（v1.5.0 重点优化）
- **响应式设计**：完美适配移动端和桌面端
- **智能按钮状态**：记录按钮始终显示，未满足条件时智能置灰
- **触摸友好**：按钮大小适合触摸操作，误触预防
- **中英文显示兼容**：经过多轮调整，确保按钮高度一致且文字不被截断
- **跨平台兼容**：完美支持iOS Chrome、Safari、Android Chrome等移动浏览器
- **智能时间处理**：前端生成基于用户本地时间的房间名称，避免时区不匹配

## 文件结构（v1.5.0 当前架构）

### 模块化架构（v1.3.4 重构）
```
d:\Projects\EMSPoolGamble\
├── app.py                    # 应用入口文件（50行）
├── requirements.txt          # 依赖配置
├── pool_gamble.db           # SQLite 数据库（v1.4.0 新增）
├── data.json                # 备用数据文件（兼容性保留）
├── README.md                # 项目说明
├── PROJECT_CONTEXT.md       # 项目上下文说明（本文档）
├── PROJECT_STATUS.md        # 项目状态总结
├── CHANGELOG.md             # 版本历史记录
├── LICENSE                  # MIT许可证
├── app/                     # 应用模块目录
│   ├── __init__.py          # 模块初始化，应用配置和版本信息
│   ├── utils.py             # 时间处理和工具函数
│   ├── models.py            # 数据模型和数据库操作
│   ├── database.py          # 数据库管理类（v1.4.0 新增）
│   ├── main_routes.py       # 主要路由（首页、历史等）
│   ├── game_routes.py       # 游戏相关路由（v1.5.0 新增批量操作）
│   └── player_routes.py     # 玩家相关路由
└── templates/
    ├── index.html           # 主页（场次列表）
    ├── game.html            # 游戏界面（v1.5.0 重点优化）
    ├── history.html         # 历史记录（全局排行榜）
    ├── session_detail.html  # 场次详情
    └── player_detail.html   # 玩家详情（v1.3.0 新增）
```

### 关键路由（v1.5.0 当前）
- **主要路由**: `/`, `/history`, `/session_detail/<session_id>`, `/delete_session/<session_id>`
- **游戏路由**: `/game/<session_id>`, `/add_score/<session_id>`, `/add_special_score/<session_id>`, `/end_session/<session_id>`
- **玩家路由**: `/add_player/<session_id>`, `/batch_add_players/<session_id>` (v1.5.0), `/create_and_select_player/<session_id>` (v1.5.0)
- **玩家管理**: `/player/<player_id>`, `/rename_player/<player_id>`

### 数据库结构（v1.4.0 升级）
```sql
-- 玩家表
CREATE TABLE players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

-- 场次表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    ended_at TEXT
);

-- 场次玩家关联表
CREATE TABLE session_players (
    session_id TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, player_id),
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (player_id) REFERENCES players(id)
);

-- 游戏记录表
CREATE TABLE game_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    winner_id INTEGER NOT NULL,
    loser_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (winner_id) REFERENCES players(id),
    FOREIGN KEY (loser_id) REFERENCES players(id)
);
```
## 数据模型（v1.4.0 数据库升级）

### 数据库实体关系
```python
# 核心数据模型（基于SQLite）
class DatabaseManager:
    # 玩家管理
    def create_player(name) -> player_id
    def get_player_by_id(player_id) -> player_info
    def get_all_players() -> [players]
    def get_available_players(session_id) -> [players_with_win_rate]
    
    # 场次管理  
    def create_session(session_id, name) -> bool
    def get_session(session_id) -> session_info
    def get_all_sessions() -> [sessions]
    
    # 玩家-场次关联
    def add_player_to_session(session_id, player_id) -> bool
    def get_session_players(session_id) -> [players_with_scores]
    
    # 游戏记录
    def add_game_record(session_id, winner_id, loser_id, score) -> bool
    def get_session_records(session_id) -> [records]
    
    # 统计功能
    def get_player_stats(player_id) -> stats_dict
    def get_player_effective_win_rate(player_id) -> win_rate
```

### 历史兼容（JSON格式，仅用于数据迁移）
```python
# 旧版本数据结构（v1.3.x及以前）
sessions = {
    "session_id": {
        "name": "周末台球赛",
        "players": set(),
        "records": [
            {
                "winner": "player1", 
                "loser": "player2",
                "score": 5,
                "timestamp": "2025-06-28 14:30:00"
            }
        ],
        "scores": {"player1": 5, "player2": -5},
        "active": True,
        "timestamp": "2025-06-28 14:00:00",
        "end_time": "2025-06-28 16:00:00"
    }
}

# 玩家数据（v1.3.0引入）
players = {
    "player_id": {
        "name": "张三",
        "created_at": "2025-06-28 10:00:00"
    }
}
```

## 用户流程（v1.5.0 优化）

### 场次管理流程
1. **创建场次**：用户访问首页，输入场次名称创建新场次
2. **加入游戏**：进入游戏界面，查看当前分数排名和玩家信息
3. **玩家管理**：
   - 快速添加玩家：多选批量添加，显示有效胜率或"新手"标识
   - 新建玩家："+"号弹窗模式，支持键盘快捷键
   - 智能推荐：按胜率排序，新玩家显示在底部
4. **计分操作**：
   - 选择分数（1-10，特殊分数14/20）
   - 选择胜者和败者（特殊分数支持两败者）
   - 实时更新分数排名
5. **场次结束**：结束比赛，查看最终排名

### 玩家系统流程
1. **玩家创建**：通过快速添加或新建玩家弹窗创建
2. **玩家档案**：点击玩家名字跳转到详情页
3. **统计查看**：查看个人统计、对手分析、历史记录
4. **玩家重命名**：在详情页修改显示名称，历史记录自动同步

### 数据查看流程
1. **历史记录**：主页查看所有场次列表和全局排行榜
2. **场次详情**：点击"查看详情"进入专门页面
3. **玩家详情**：点击任何玩家名字查看个人档案
4. **数据分析**：查看胜率、对手分析等统计信息

## 已实现特性（v1.5.0 当前状态）

### 🎯 核心功能
- **完整的场次生命周期管理**: 创建 → 进行 → 结束 → 查看详情 → 删除
- **独立玩家系统**: 玩家档案、统计分析、智能重命名、全局跳转
- **数据库架构**: SQLite存储，自动迁移，完全替代JSON文件
- **模块化代码**: 7个专业模块，代码行数从960行减少到50行入口文件

### 🎨 用户体验（v1.5.0 重点优化）
- **卡片布局重构**: 功能分工明确，层次清晰
- **快速添加玩家升级**: 多选批量添加，动态按钮状态，实时数量显示
- **胜率智能显示**: 有效胜率计算（排除1分），新手标识
- **新建玩家交互优化**: "+"号弹窗，ESC/外部点击关闭，回车提交
- **界面美化**: 浅色背景、圆角设计、统一间距，视觉层次感提升
- **中英文兼容**: 按钮高度一致，文字不截断
- **响应式设计**: 适配移动端和桌面浏览器
- **触摸友好**: 按钮大小、误触预防、拖拽友好

### 📊 统计分析
- **个人统计页**: 总场次、胜局数、有效胜率、得分分布
- **对手分析**: 与每个对手的对战记录和胜负关系  
- **历史回顾**: 按时间顺序展示所有参与场次
- **全局排行榜**: 总胜局数、总场次数、胜率排行
- **场次排行榜**: 单场次得分排名和详细记录

### 🔧 技术特性
- **数据完整性**: 数据库约束，分数自动计算，记录一致性验证
- **性能优化**: 数据库查询替代文件读写，支持并发访问
- **兼容性处理**: 自动JSON数据迁移，零停机升级
- **错误处理**: 完善的异常处理和用户反馈
- **消息通知系统**: Flask flash功能提供操作反馈

## 部署信息

- **环境变量配置**:
  - SECRET_KEY: 会话安全密钥
  - PORT: 应用运行端口（默认5000）
  - FLASK_DEBUG: 调试模式开关（生产环境设为False）
- **默认配置**: 监听0.0.0.0:5000，方便局域网内访问
- **Azure部署**: README中包含Azure App Service部署指南
- **数据库**: SQLite文件，自动创建和迁移

## 版本历史关键节点

- **v1.5.0 (2025-06-28)**: 游戏页面UI/UX深度优化，批量玩家操作，界面美化
- **v1.4.0 (2025-06-27)**: 数据库架构升级，JSON -> SQLite迁移
- **v1.3.4 (2025-06-26)**: 模块化重构，代码拆分为7个专业模块
- **v1.3.0 (2025-06-26)**: 玩家系统重构，独立档案，统计分析
- **v1.2.x**: 界面优化，响应式设计，移动端适配
- **v1.1.x**: 核心功能完善，场次管理，计分系统
- **v1.0.x**: 基础版本，简单计分功能

## 潜在扩展方向

### 短期扩展
- **撤销功能**: 允许修正记分错误，增加撤销操作
- **数据导出**: 支持CSV/PDF格式导出成绩单
- **规则定制**: 支持不同台球游戏规则和计分方式
- **多场次并行**: 支持同时进行多个活跃场次

### 中期扩展  
- **用户认证系统**: 添加账号注册和密码保护
- **数据可视化**: 添加统计图表展示，胜率趋势分析
- **移动应用**: 开发移动端原生应用
- **实时通知**: WebSocket实时更新，多人协作

### 长期扩展
- **云端同步**: 多设备数据同步
- **社交功能**: 好友系统，比赛邀请
- **比赛模式**: 锦标赛，排名赛等复杂赛制
- **AI分析**: 玩家表现分析，改进建议

## 使用说明

应用已经完成开发，达到生产可用状态。代码结构清晰，有完善注释，容易理解和扩展。如需添加新功能，请在现有代码基础上继续开发，保持代码风格一致。

### 开发规范
- **模块化原则**: 新功能按模块组织，保持单一职责
- **数据库优先**: 所有数据操作通过DatabaseManager类
- **用户体验**: 保持响应式设计，移动端优先
- **错误处理**: 完善的异常处理和用户反馈
- **兼容性**: 保持向后兼容，平滑升级

### 代码质量
- **类型提示**: 关键函数使用类型注解
- **文档字符串**: 重要函数和类有详细说明
- **单元测试**: 核心功能有对应测试用例
- **代码审查**: 重要更改需要代码审查

## 最新更新（v1.5.0 - 2025-06-28）

### 🎨 游戏页面UI/UX深度优化
- **卡片布局重构**: 玩家管理卡片和计分面板卡片分工明确，场次控制卡片独立
- **快速添加玩家功能升级**: 支持多选批量添加，动态按钮状态，选中数量实时显示
- **胜率智能显示**: 快速添加按钮显示有效胜率（排除1分对局），新玩家显示"新手"
- **新建玩家交互优化**: "+"号弹窗模式，支持ESC/外部点击关闭、回车提交
- **批量操作后端支持**: 新增批量添加和单独创建玩家路由
- **界面美化**: 按钮区域浅色背景、圆角设计、统一间距
- **中英文显示兼容**: 多轮CSS调整，确保按钮高度一致且文字不被截断

### 当前项目状态
- ✅ **功能完整**: 所有核心功能开发完成，用户体验现代化
- ✅ **架构稳定**: 数据库架构成熟，模块化代码结构清晰
- ✅ **界面美观**: UI/UX达到产品级标准，移动端体验优秀
- ✅ **性能优化**: 数据库查询高效，支持并发访问
- ✅ **部署就绪**: 完全可部署到Azure等云平台

应用已达到企业级生产标准，无需进一步核心开发。后续可根据用户反馈进行功能扩展。
