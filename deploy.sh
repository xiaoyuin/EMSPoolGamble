#!/bin/bash
# EMS Pool Gamble 一键部署脚本
# 适用于全新的 Linux 环境

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# 检查是否为 root 用户
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_warning "检测到 root 用户，建议使用普通用户运行此脚本"
        read -p "是否继续？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# 检测操作系统
detect_os() {
    if [[ -f /etc/redhat-release ]]; then
        OS="centos"
        PACKAGE_MANAGER="yum"
    elif [[ -f /etc/debian_version ]]; then
        OS="ubuntu"
        PACKAGE_MANAGER="apt"
    else
        log_error "不支持的操作系统，仅支持 CentOS/RHEL 和 Ubuntu/Debian"
        exit 1
    fi
    log_info "检测到操作系统: $OS"
}

# 安装系统依赖
install_system_dependencies() {
    log_info "安装系统依赖..."

    if [[ $OS == "ubuntu" ]]; then
        sudo apt update
        sudo apt install -y python3 python3-pip python3-venv git nginx supervisor
    elif [[ $OS == "centos" ]]; then
        sudo yum update -y
        sudo yum install -y python3 python3-pip git nginx supervisor
    fi

    log_success "系统依赖安装完成"
}

# 安装 Python 依赖
install_python_dependencies() {
    log_info "创建 Python 虚拟环境..."

    # 创建虚拟环境
    python3 -m venv venv
    source venv/bin/activate

    # 升级 pip
    pip install --upgrade pip

    # 安装项目依赖
    pip install -r requirements.txt

    # 安装生产环境依赖
    pip install gunicorn

    log_success "Python 依赖安装完成"
}

# 设置数据持久化目录
setup_data_persistence() {
    log_info "设置数据持久化..."

    # 创建数据目录
    DATA_DIR="/opt/ems-pool-gamble-data"
    sudo mkdir -p $DATA_DIR
    sudo chown $USER:$USER $DATA_DIR

    # 创建实例目录软链接
    if [[ ! -d "instance" ]]; then
        mkdir -p instance
    fi

    # 如果数据库不存在，初始化
    if [[ ! -f "$DATA_DIR/ems_pool_gamble.db" ]]; then
        log_info "初始化数据库..."
        source venv/bin/activate
        python3 -c "from app import app, db; app.app_context().push(); db.create_all(); print('数据库初始化完成')"

        # 移动数据库到持久化目录
        if [[ -f "instance/ems_pool_gamble.db" ]]; then
            mv instance/ems_pool_gamble.db $DATA_DIR/
        fi
    fi

    # 创建软链接指向持久化目录
    rm -f instance/ems_pool_gamble.db
    ln -sf $DATA_DIR/ems_pool_gamble.db instance/ems_pool_gamble.db

    log_success "数据持久化设置完成，数据将保存在: $DATA_DIR"
}

# 配置 Nginx
configure_nginx() {
    log_info "配置 Nginx..."

    # 创建 Nginx 配置文件
    sudo tee /etc/nginx/sites-available/ems-pool-gamble > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 4M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /static {
        alias $(pwd)/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

    # 启用站点
    if [[ $OS == "ubuntu" ]]; then
        sudo ln -sf /etc/nginx/sites-available/ems-pool-gamble /etc/nginx/sites-enabled/
        sudo rm -f /etc/nginx/sites-enabled/default
    elif [[ $OS == "centos" ]]; then
        sudo cp /etc/nginx/sites-available/ems-pool-gamble /etc/nginx/conf.d/ems-pool-gamble.conf
    fi

    # 测试配置
    sudo nginx -t

    log_success "Nginx 配置完成"
}

# 配置 Supervisor
configure_supervisor() {
    log_info "配置 Supervisor..."

    # 创建 Supervisor 配置文件
    sudo tee /etc/supervisor/conf.d/ems-pool-gamble.conf > /dev/null <<EOF
[program:ems-pool-gamble]
command=$(pwd)/venv/bin/gunicorn --bind 127.0.0.1:8000 --workers 2 --timeout 60 app:app
directory=$(pwd)
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/ems-pool-gamble.log
environment=SECRET_KEY="$(openssl rand -hex 32)",DATABASE_URL="sqlite:///$(pwd)/instance/ems_pool_gamble.db"
EOF

    log_success "Supervisor 配置完成"
}

# 启动服务
start_services() {
    log_info "启动服务..."

    # 重新加载 Supervisor 配置
    sudo supervisorctl reread
    sudo supervisorctl update

    # 启动应用
    sudo supervisorctl start ems-pool-gamble

    # 启动 Nginx
    sudo systemctl enable nginx
    sudo systemctl restart nginx

    # 启动 Supervisor
    sudo systemctl enable supervisor
    sudo systemctl restart supervisor

    log_success "服务启动完成"
}

# 显示部署信息
show_deployment_info() {
    echo
    log_success "========================================="
    log_success "     EMS Pool Gamble 部署完成！"
    log_success "========================================="
    echo
    log_info "应用访问地址: http://$(hostname -I | awk '{print $1}')"
    log_info "数据持久化目录: /opt/ems-pool-gamble-data"
    log_info "应用日志: /var/log/ems-pool-gamble.log"
    echo
    log_info "常用管理命令:"
    echo "  查看应用状态: sudo supervisorctl status ems-pool-gamble"
    echo "  重启应用:     sudo supervisorctl restart ems-pool-gamble"
    echo "  查看日志:     sudo tail -f /var/log/ems-pool-gamble.log"
    echo "  停止应用:     sudo supervisorctl stop ems-pool-gamble"
    echo
    log_warning "重要提示:"
    echo "  1. 数据库文件保存在 /opt/ems-pool-gamble-data/ 目录"
    echo "  2. 重新部署时数据不会丢失"
    echo "  3. 建议定期备份数据库文件"
    echo
}

# 主函数
main() {
    echo "========================================"
    echo "    EMS Pool Gamble 自动部署脚本"
    echo "========================================"
    echo

    check_root
    detect_os
    install_system_dependencies
    install_python_dependencies
    setup_data_persistence
    configure_nginx
    configure_supervisor
    start_services
    show_deployment_info
}

# 运行主函数
main "$@"
