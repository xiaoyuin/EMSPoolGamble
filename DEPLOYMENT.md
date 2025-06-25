# EMS Pool Gamble 部署指南

这是一个完整的部署解决方案，包含了在全新 Linux 环境中部署 EMS Pool Gamble 应用所需的所有脚本和工具。

## 🚀 快速部署

### 方法一：使用管理工具（推荐）

```bash
# 下载项目代码
git clone <repository-url>
cd EMSPoolGamble

# 运行管理工具
./manage.sh
```

然后选择 "1) 首次部署" 即可自动完成所有配置。

### 方法二：直接运行部署脚本

```bash
# 运行一键部署脚本
./deploy.sh
```

## 📋 部署脚本说明

### 1. `deploy.sh` - 一键部署脚本
- **功能**: 在全新的 Linux 环境中自动部署应用
- **支持**: Ubuntu/Debian 和 CentOS/RHEL
- **包含**:
  - 系统依赖安装 (Python3, Nginx, Supervisor)
  - Python 虚拟环境创建
  - 数据持久化配置
  - Nginx 反向代理配置
  - Supervisor 进程管理配置
  - 服务启动和状态检查

### 2. `update.sh` - 更新部署脚本
- **功能**: 更新应用代码但保留数据
- **包含**:
  - 自动数据备份
  - 代码更新 (支持 Git)
  - 依赖更新
  - 数据库迁移
  - 服务重启

### 3. `backup.sh` - 数据备份脚本
- **功能**: 完整的数据备份和恢复解决方案
- **支持操作**:
  - `./backup.sh backup` - 创建备份
  - `./backup.sh list` - 列出备份
  - `./backup.sh restore <file>` - 恢复数据
  - `./backup.sh cleanup` - 清理旧备份

### 4. `check.sh` - 环境检查脚本
- **功能**: 全面的系统和应用健康检查
- **检查项目**:
  - 系统信息和资源
  - 必需命令和依赖
  - Python 环境
  - 数据持久化配置
  - 服务状态
  - 网络连通性
  - 日志文件
  - 性能指标

### 5. `manage.sh` - 统一管理工具
- **功能**: 交互式管理界面
- **包含**: 所有常用管理操作的图形化菜单

## 🗄️ 数据持久化

### 数据存储位置
- **数据目录**: `/opt/ems-pool-gamble-data/`
- **数据库文件**: `/opt/ems-pool-gamble-data/ems_pool_gamble.db`
- **应用软链接**: `instance/ems_pool_gamble.db` → 数据目录

### 备份策略
- **自动备份**: 每次更新前自动创建备份
- **压缩存储**: 备份文件自动 gzip 压缩
- **自动清理**: 保留 30 天内的备份文件
- **备份位置**: `/opt/ems-pool-gamble-backups/`

## 🔧 服务配置

### Nginx 配置
- **端口**: 80 (HTTP)
- **代理**: 转发到内部 8000 端口
- **配置文件**: `/etc/nginx/sites-available/ems-pool-gamble`

### Supervisor 配置
- **服务名**: `ems-pool-gamble`
- **进程数**: 2 个 Gunicorn worker
- **自动重启**: 启用
- **日志文件**: `/var/log/ems-pool-gamble.log`

### 环境变量
- **SECRET_KEY**: 自动生成的安全密钥
- **DATABASE_URL**: SQLite 数据库路径

## 🚦 常用管理命令

### 服务管理
```bash
# 查看服务状态
sudo supervisorctl status ems-pool-gamble

# 重启应用
sudo supervisorctl restart ems-pool-gamble

# 查看日志
sudo tail -f /var/log/ems-pool-gamble.log

# 重启 Nginx
sudo systemctl restart nginx
```

### 数据管理
```bash
# 创建备份
./backup.sh backup

# 查看备份列表
./backup.sh list

# 恢复数据
./backup.sh restore <backup_file>
```

### 系统检查
```bash
# 快速检查
./check.sh

# 生成详细报告
./check.sh --report
```

## 🔄 更新流程

1. **备份数据**
   ```bash
   ./backup.sh backup
   ```

2. **更新代码**
   ```bash
   ./update.sh
   ```

3. **验证部署**
   ```bash
   ./check.sh
   ```

## 🆘 故障排除

### 常见问题

1. **应用无法启动**
   - 检查日志: `sudo tail -f /var/log/ems-pool-gamble.log`
   - 检查配置: `./check.sh`
   - 重启服务: `sudo supervisorctl restart ems-pool-gamble`

2. **数据库连接失败**
   - 检查数据目录权限: `ls -la /opt/ems-pool-gamble-data/`
   - 检查软链接: `ls -la instance/ems_pool_gamble.db`
   - 重新创建链接: 运行 `./deploy.sh` 中的数据持久化部分

3. **网页无法访问**
   - 检查 Nginx 状态: `sudo systemctl status nginx`
   - 检查端口占用: `netstat -tlpn | grep :80`
   - 测试配置: `sudo nginx -t`

### 日志文件位置
- **应用日志**: `/var/log/ems-pool-gamble.log`
- **Nginx 访问日志**: `/var/log/nginx/access.log`
- **Nginx 错误日志**: `/var/log/nginx/error.log`
- **系统日志**: `/var/log/syslog` (Ubuntu) 或 `/var/log/messages` (CentOS)

## 📊 监控和维护

### 定期维护建议
1. **每日**: 检查服务状态和日志
2. **每周**: 创建数据备份
3. **每月**: 清理旧日志和备份文件
4. **按需**: 更新应用代码和系统补丁

### 自动化建议
可以将以下命令添加到 crontab 实现自动化：

```bash
# 每天凌晨 2 点备份数据
0 2 * * * /path/to/project/backup.sh backup

# 每周日凌晨 3 点清理旧备份
0 3 * * 0 /path/to/project/backup.sh cleanup
```

## 🔒 安全建议

1. **定期更新系统**: `sudo apt update && sudo apt upgrade` (Ubuntu)
2. **防火墙配置**: 只开放必要端口 (80, 443, 22)
3. **SSL 证书**: 建议配置 HTTPS
4. **备份加密**: 重要数据备份建议加密存储
5. **访问控制**: 限制管理脚本的执行权限

## 📞 支持

如果遇到问题：
1. 运行 `./check.sh --report` 生成诊断报告
2. 查看相关日志文件
3. 检查本文档的故障排除部分
