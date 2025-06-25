#!/bin/bash
# EMS Pool Gamble 环境检查脚本

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
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

# 检查命令是否存在
check_command() {
    if command -v "$1" &> /dev/null; then
        log_success "$1 已安装: $(command -v $1)"
        return 0
    else
        log_error "$1 未安装"
        return 1
    fi
}

# 检查系统信息
check_system() {
    log_info "=== 系统信息 ==="
    echo "操作系统: $(uname -s)"
    echo "内核版本: $(uname -r)"
    echo "架构: $(uname -m)"

    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        echo "发行版: $NAME $VERSION"
    fi

    echo "内存: $(free -h | awk '/^Mem:/ {print $2}')"
    echo "磁盘空间: $(df -h / | awk 'NR==2 {print $4}') 可用"
    echo
}

# 检查必需的命令
check_required_commands() {
    log_info "=== 检查必需的命令 ==="

    local commands=("python3" "pip3" "git" "curl" "nginx" "supervisorctl")
    local missing_commands=()

    for cmd in "${commands[@]}"; do
        if ! check_command "$cmd"; then
            missing_commands+=("$cmd")
        fi
    done

    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        log_error "缺少必需的命令: ${missing_commands[*]}"
        log_info "请先运行部署脚本安装依赖"
        return 1
    fi

    echo
    return 0
}

# 检查 Python 环境
check_python_environment() {
    log_info "=== 检查 Python 环境 ==="

    if [[ -d "venv" ]]; then
        log_success "虚拟环境存在"

        if [[ -f "venv/bin/activate" ]]; then
            source venv/bin/activate
            echo "Python 版本: $(python --version)"
            echo "Pip 版本: $(pip --version)"

            # 检查关键依赖
            if pip show flask flask-sqlalchemy &> /dev/null; then
                log_success "Flask 依赖已安装"
            else
                log_error "Flask 依赖缺失"
            fi

            deactivate
        else
            log_error "虚拟环境损坏"
        fi
    else
        log_error "虚拟环境不存在"
    fi

    echo
}

# 检查数据持久化
check_data_persistence() {
    log_info "=== 检查数据持久化 ==="

    DATA_DIR="/opt/ems-pool-gamble-data"
    DB_FILE="$DATA_DIR/ems_pool_gamble.db"

    if [[ -d "$DATA_DIR" ]]; then
        log_success "数据目录存在: $DATA_DIR"
        echo "目录权限: $(ls -ld $DATA_DIR | awk '{print $1, $3, $4}')"

        if [[ -f "$DB_FILE" ]]; then
            log_success "数据库文件存在"
            echo "文件大小: $(du -h $DB_FILE | cut -f1)"
            echo "修改时间: $(stat -c %y $DB_FILE 2>/dev/null || stat -f %Sm $DB_FILE)"
        else
            log_warning "数据库文件不存在"
        fi

        if [[ -L "instance/ems_pool_gamble.db" ]]; then
            log_success "数据库软链接正确"
        else
            log_error "数据库软链接缺失或错误"
        fi
    else
        log_error "数据目录不存在: $DATA_DIR"
    fi

    echo
}

# 检查服务状态
check_services() {
    log_info "=== 检查服务状态 ==="

    # 检查 Supervisor
    if sudo supervisorctl status ems-pool-gamble &> /dev/null; then
        STATUS=$(sudo supervisorctl status ems-pool-gamble)
        if echo "$STATUS" | grep -q "RUNNING"; then
            log_success "应用服务运行中"
        else
            log_error "应用服务未运行: $STATUS"
        fi
    else
        log_error "无法获取应用服务状态"
    fi

    # 检查 Nginx
    if sudo systemctl is-active --quiet nginx; then
        log_success "Nginx 服务运行中"
    else
        log_error "Nginx 服务未运行"
    fi

    echo
}

# 检查网络连通性
check_network() {
    log_info "=== 检查网络连通性 ==="

    # 检查本地端口
    if netstat -tlpn 2>/dev/null | grep -q ":8000 "; then
        log_success "应用端口 8000 监听中"
    else
        log_error "应用端口 8000 未监听"
    fi

    if netstat -tlpn 2>/dev/null | grep -q ":80 "; then
        log_success "HTTP 端口 80 监听中"
    else
        log_error "HTTP 端口 80 未监听"
    fi

    # 测试 HTTP 响应
    if curl -s -o /dev/null -w "%{http_code}" http://localhost | grep -q "200"; then
        log_success "HTTP 服务响应正常"
    else
        log_error "HTTP 服务响应异常"
    fi

    echo
}

# 检查日志文件
check_logs() {
    log_info "=== 检查日志文件 ==="

    LOG_FILE="/var/log/ems-pool-gamble.log"

    if [[ -f "$LOG_FILE" ]]; then
        log_success "应用日志文件存在"
        echo "文件大小: $(du -h $LOG_FILE | cut -f1)"
        echo "最近修改: $(stat -c %y $LOG_FILE 2>/dev/null || stat -f %Sm $LOG_FILE)"

        # 显示最近的错误
        if grep -i error "$LOG_FILE" | tail -5 | grep -q .; then
            log_warning "发现最近的错误日志:"
            grep -i error "$LOG_FILE" | tail -5 | while read -r line; do
                echo "  $line"
            done
        else
            log_success "最近无错误日志"
        fi
    else
        log_error "应用日志文件不存在"
    fi

    echo
}

# 性能检查
check_performance() {
    log_info "=== 性能检查 ==="

    # CPU 使用率
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    echo "CPU 使用率: ${CPU_USAGE}%"

    # 内存使用率
    MEMORY_USAGE=$(free | awk 'NR==2{printf "%.1f", $3*100/$2}')
    echo "内存使用率: ${MEMORY_USAGE}%"

    # 磁盘使用率
    DISK_USAGE=$(df / | awk 'NR==2{printf "%s", $5}')
    echo "根分区使用率: $DISK_USAGE"

    # 应用进程
    APP_PROCESSES=$(pgrep -f "gunicorn.*app:app" | wc -l)
    echo "应用进程数: $APP_PROCESSES"

    echo
}

# 生成诊断报告
generate_report() {
    log_info "=== 生成诊断报告 ==="

    REPORT_FILE="/tmp/ems-pool-gamble-diagnostic-$(date +%Y%m%d_%H%M%S).txt"

    {
        echo "EMS Pool Gamble 诊断报告"
        echo "生成时间: $(date)"
        echo "================================"
        echo

        # 重新运行所有检查并输出到文件
        check_system
        check_required_commands
        check_python_environment
        check_data_persistence
        check_services
        check_network
        check_logs
        check_performance

    } > "$REPORT_FILE"

    log_success "诊断报告已生成: $REPORT_FILE"
}

# 显示帮助信息
show_help() {
    echo "EMS Pool Gamble 环境检查工具"
    echo
    echo "用法:"
    echo "  $0 [选项]"
    echo
    echo "选项:"
    echo "  --report     生成详细诊断报告"
    echo "  --help       显示此帮助信息"
    echo
}

# 主函数
main() {
    echo "========================================"
    echo "    EMS Pool Gamble 环境检查"
    echo "========================================"
    echo

    case "${1:-check}" in
        --report)
            generate_report
            ;;
        --help|-h)
            show_help
            ;;
        *)
            check_system
            check_required_commands
            check_python_environment
            check_data_persistence
            check_services
            check_network
            check_logs
            check_performance

            echo "========================================"
            echo "环境检查完成！"
            echo "如需详细报告，请运行: $0 --report"
            echo "========================================"
            ;;
    esac
}

# 运行主函数
main "$@"
