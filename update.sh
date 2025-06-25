#!/bin/bash
# EMS Pool Gamble 更新部署脚本
# 用于更新代码而不丢失数据

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查当前目录
check_directory() {
    if [[ ! -f "app.py" ]] || [[ ! -f "requirements.txt" ]]; then
        log_error "请在 EMS Pool Gamble 项目根目录下运行此脚本"
        exit 1
    fi
}

# 备份数据
backup_data() {
    log_info "备份当前数据..."
    if [[ -f "./backup.sh" ]]; then
        chmod +x ./backup.sh
        ./backup.sh backup
    else
        log_warning "备份脚本不存在，跳过数据备份"
    fi
}

# 停止服务
stop_services() {
    log_info "停止应用服务..."
    sudo supervisorctl stop ems-pool-gamble || true
}

# 更新代码
update_code() {
    log_info "更新应用代码..."

    # 如果是 git 仓库，拉取最新代码
    if [[ -d ".git" ]]; then
        git pull origin main || git pull origin master || true
    fi

    # 激活虚拟环境
    source venv/bin/activate

    # 更新 Python 依赖
    pip install --upgrade pip
    pip install -r requirements.txt

    log_success "代码更新完成"
}

# 数据库迁移
migrate_database() {
    log_info "检查数据库迁移..."

    source venv/bin/activate

    # 检查是否需要数据迁移
    if [[ -f "data.json" ]]; then
        log_info "发现旧数据文件，执行数据迁移..."
        python3 migrate_data.py
    fi

    # 确保数据库表结构是最新的
    python3 -c "from app import app, db; app.app_context().push(); db.create_all(); print('数据库结构检查完成')"

    log_success "数据库迁移完成"
}

# 重启服务
restart_services() {
    log_info "重启应用服务..."

    # 重新加载 supervisor 配置
    sudo supervisorctl reread
    sudo supervisorctl update

    # 启动应用
    sudo supervisorctl start ems-pool-gamble

    # 重新加载 nginx
    sudo nginx -t && sudo systemctl reload nginx

    log_success "服务重启完成"
}

# 检查服务状态
check_services() {
    log_info "检查服务状态..."

    sleep 3  # 等待服务启动

    # 检查应用状态
    if sudo supervisorctl status ems-pool-gamble | grep -q "RUNNING"; then
        log_success "应用服务运行正常"
    else
        log_error "应用服务启动失败"
        log_info "查看日志: sudo tail -f /var/log/ems-pool-gamble.log"
        exit 1
    fi

    # 检查 nginx 状态
    if sudo systemctl is-active --quiet nginx; then
        log_success "Nginx 服务运行正常"
    else
        log_error "Nginx 服务异常"
        exit 1
    fi

    # 测试 HTTP 响应
    if curl -s -o /dev/null -w "%{http_code}" http://localhost | grep -q "200"; then
        log_success "HTTP 服务响应正常"
    else
        log_warning "HTTP 服务响应异常，请检查配置"
    fi
}

# 显示更新信息
show_update_info() {
    echo
    log_success "========================================="
    log_success "     应用更新完成！"
    log_success "========================================="
    echo
    log_info "应用访问地址: http://$(hostname -I | awk '{print $1}')"
    log_info "应用状态: sudo supervisorctl status ems-pool-gamble"
    log_info "应用日志: sudo tail -f /var/log/ems-pool-gamble.log"
    echo
}

# 回滚功能
rollback() {
    log_warning "执行回滚操作..."

    if [[ -z "$1" ]]; then
        log_error "请指定要回滚到的备份文件"
        ./backup.sh list
        exit 1
    fi

    ./backup.sh restore "$1"
    restart_services
    check_services

    log_success "回滚完成"
}

# 显示帮助信息
show_help() {
    echo "EMS Pool Gamble 更新部署工具"
    echo
    echo "用法:"
    echo "  $0 update          - 更新应用（默认操作）"
    echo "  $0 rollback <file> - 回滚到指定备份"
    echo "  $0 status          - 检查服务状态"
    echo "  $0 help            - 显示此帮助信息"
    echo
    echo "示例:"
    echo "  $0 update"
    echo "  $0 rollback ems_pool_gamble_backup_20231225_120000.db.gz"
    echo "  $0 status"
}

# 主函数
main() {
    case "${1:-update}" in
        update)
            echo "========================================"
            echo "    EMS Pool Gamble 更新部署"
            echo "========================================"
            echo

            check_directory
            backup_data
            stop_services
            update_code
            migrate_database
            restart_services
            check_services
            show_update_info
            ;;
        rollback)
            rollback "$2"
            ;;
        status)
            check_services
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
