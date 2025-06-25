#!/bin/bash
# EMS Pool Gamble 数据备份脚本

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 配置
DATA_DIR="/opt/ems-pool-gamble-data"
BACKUP_DIR="/opt/ems-pool-gamble-backups"
DB_FILE="$DATA_DIR/ems_pool_gamble.db"
RETENTION_DAYS=30

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 创建备份目录
create_backup_dir() {
    if [[ ! -d "$BACKUP_DIR" ]]; then
        sudo mkdir -p "$BACKUP_DIR"
        sudo chown $USER:$USER "$BACKUP_DIR"
        log_info "创建备份目录: $BACKUP_DIR"
    fi
}

# 备份数据库
backup_database() {
    if [[ ! -f "$DB_FILE" ]]; then
        log_error "数据库文件不存在: $DB_FILE"
        exit 1
    fi

    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    BACKUP_FILE="$BACKUP_DIR/ems_pool_gamble_backup_$TIMESTAMP.db"

    log_info "开始备份数据库..."
    cp "$DB_FILE" "$BACKUP_FILE"

    # 压缩备份文件
    gzip "$BACKUP_FILE"
    BACKUP_FILE="$BACKUP_FILE.gz"

    log_info "备份完成: $BACKUP_FILE"

    # 显示备份文件大小
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log_info "备份文件大小: $BACKUP_SIZE"
}

# 清理旧备份
cleanup_old_backups() {
    log_info "清理 $RETENTION_DAYS 天前的备份文件..."

    OLD_BACKUPS=$(find "$BACKUP_DIR" -name "ems_pool_gamble_backup_*.db.gz" -mtime +$RETENTION_DAYS)

    if [[ -n "$OLD_BACKUPS" ]]; then
        echo "$OLD_BACKUPS" | while read -r backup; do
            rm -f "$backup"
            log_info "删除旧备份: $(basename "$backup")"
        done
    else
        log_info "没有需要清理的旧备份文件"
    fi
}

# 列出所有备份
list_backups() {
    log_info "当前所有备份文件:"
    if [[ -d "$BACKUP_DIR" ]]; then
        ls -lah "$BACKUP_DIR"/ems_pool_gamble_backup_*.db.gz 2>/dev/null | while read -r line; do
            echo "  $line"
        done
    else
        log_warning "备份目录不存在"
    fi
}

# 恢复数据库
restore_database() {
    if [[ -z "$1" ]]; then
        log_error "请指定要恢复的备份文件"
        echo "用法: $0 restore <backup_file>"
        list_backups
        exit 1
    fi

    BACKUP_FILE="$1"

    if [[ ! -f "$BACKUP_FILE" ]]; then
        # 尝试在备份目录中查找
        BACKUP_FILE="$BACKUP_DIR/$1"
        if [[ ! -f "$BACKUP_FILE" ]]; then
            log_error "备份文件不存在: $1"
            list_backups
            exit 1
        fi
    fi

    log_warning "警告: 这将覆盖当前的数据库文件"
    read -p "是否继续? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "取消恢复操作"
        exit 0
    fi

    # 停止应用
    log_info "停止应用..."
    sudo supervisorctl stop ems-pool-gamble || true

    # 备份当前数据库
    if [[ -f "$DB_FILE" ]]; then
        CURRENT_BACKUP="$BACKUP_DIR/current_backup_$(date +"%Y%m%d_%H%M%S").db"
        cp "$DB_FILE" "$CURRENT_BACKUP"
        log_info "当前数据库已备份到: $CURRENT_BACKUP"
    fi

    # 恢复数据库
    log_info "恢复数据库从: $BACKUP_FILE"
    if [[ "$BACKUP_FILE" == *.gz ]]; then
        gunzip -c "$BACKUP_FILE" > "$DB_FILE"
    else
        cp "$BACKUP_FILE" "$DB_FILE"
    fi

    # 重启应用
    log_info "重启应用..."
    sudo supervisorctl start ems-pool-gamble

    log_info "数据库恢复完成"
}

# 显示帮助信息
show_help() {
    echo "EMS Pool Gamble 数据备份工具"
    echo
    echo "用法:"
    echo "  $0 backup          - 创建数据库备份"
    echo "  $0 list            - 列出所有备份文件"
    echo "  $0 restore <file>  - 从备份文件恢复数据库"
    echo "  $0 cleanup         - 清理旧备份文件"
    echo "  $0 help            - 显示此帮助信息"
    echo
    echo "示例:"
    echo "  $0 backup"
    echo "  $0 restore ems_pool_gamble_backup_20231225_120000.db.gz"
    echo "  $0 cleanup"
}

# 主函数
main() {
    case "${1:-backup}" in
        backup)
            create_backup_dir
            backup_database
            cleanup_old_backups
            ;;
        list)
            list_backups
            ;;
        restore)
            restore_database "$2"
            ;;
        cleanup)
            create_backup_dir
            cleanup_old_backups
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
