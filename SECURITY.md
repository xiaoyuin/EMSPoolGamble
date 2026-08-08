# EMS Pool 安全配置说明

## 权限模型

v1.13.0 使用两级管理员权限：

- **组织管理员**：只管理登录时所在的组织；权限绑定该组织的不可变 `org_id`
- **超级管理员**：由部署环境的 `ADMIN_PASSWORD` 验证，可以管理任意已进入的组织；EMS 组织也使用该凭据

普通访客仍可公开浏览组织数据、创建/加入场次、普通计分和录入赛事局分。这是当前产品的协作模型，不等同于管理员权限。

以下操作要求当前组织管理员或超级管理员：

- 创建新玩家
- 删除计分记录、结束/删除场次
- 玩家重命名、退役和复出
- 创建/删除赛事、报名管理、生成对阵、视频管理、撤回和重置

新组织创建时设置独立管理员密码。数据库只保存 Werkzeug 密码哈希，不保存明文。

## 组织隔离

- Canonical URL 为 `/o/<org_slug>/...`
- 请求先解析组织到 `g.organization`，再把 `org_id` 显式传入所有 DAO
- 玩家、场次、计分、统计、特殊记录和赛事查询都带组织条件
- 跨组织 UUID 与不存在资源统一返回 404
- SQLite 复合外键阻止跨组织玩家、场次、计分和赛事关联
- 根页面不提供服务端组织目录；“之前进入过”仅保存在浏览器 localStorage

组织 URL 不是私密访问控制。知道组织名称或链接的访客可以查看和执行上述公开协作操作。

## 环境变量

### `SECRET_KEY`

Flask session 签名密钥。生产环境应设置为随机、长期稳定的值；更换后所有已有管理员会话失效。

```bash
export SECRET_KEY="your-long-random-session-secret"
```

### `ADMIN_PASSWORD`

全站超级管理员凭据，同时用于 EMS 组织。生产环境必须改掉默认值。

```bash
export ADMIN_PASSWORD="your-strong-super-admin-password"
```

### `ALLOWED_IPS`（可选）

逗号分隔的管理功能 IP 白名单；未设置时不限制来源 IP。

```bash
export ALLOWED_IPS="192.168.1.100,10.0.0.50"
```

## 会话和 CSRF

- 管理员状态保存在 Flask 签名 session 中，默认有效期 7 天
- 组织管理员 claim 为 `organization_admin_org_id`
- 超级管理员 claim 为 `super_admin_authenticated`
- 旧版 `admin_authenticated` 不再授予权限
- 管理员退出使用 POST + CSRF
- 组织选择、创建、管理员登录和受保护的写操作使用 session CSRF token
- 登录 continuation 只允许服务器生成的当前组织内路径

## Azure 部署

在 App Service 的 Configuration 中至少设置：

```text
SECRET_KEY=<随机 session 密钥>
ADMIN_PASSWORD=<强超级管理员密码>
FLASK_DEBUG=False
ALLOWED_IPS=<可选>
```

数据库位于 `/home/data/ems_pool_gamble.db`。v1.13.0 首次部署涉及核心表重建，必须：

1. 停止业务写入并保留单实例启动
2. 将数据库复制到 App Service 之外并验证备份
3. 先在生产数据库副本上演练迁移
4. 启动后验证 EMS、组织入口、管理员登录、计分和赛事
5. 失败时同时恢复旧应用与迁移前数据库

## 安全边界说明

- UUID 是资源标识，不是授权依据；服务端始终同时检查 `org_id`
- 组织短标识用于导航，不提供保密性
- PWA Service Worker 当前不缓存业务页面或数据
- localStorage 的最近组织记录只用于快捷入口，服务端不会据此授权
- 管理员密码、CSRF token 和 session cookie 不应写入日志或客户端持久存储

## 后续安全工作

现有项目仍计划逐步统一所有公开写操作的 CSRF 覆盖、移除修改状态的兼容 GET 路由、加强生产默认配置与安全响应头。这些工作不改变 v1.13.0 已实现的组织数据隔离边界。
