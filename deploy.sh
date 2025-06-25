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

# 显示系统信息
show_system_info() {
    log_info "系统信息检测..."
    echo "操作系统: $(uname -s)"
    echo "内核版本: $(uname -r)"
    echo "架构: $(uname -m)"

    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        echo "发行版: $NAME ${VERSION:-$VERSION_ID}"
    elif [[ -f /etc/redhat-release ]]; then
        echo "发行版: $(cat /etc/redhat-release)"
    elif [[ -f /etc/debian_version ]]; then
        echo "发行版: Debian $(cat /etc/debian_version)"
    fi

    echo "内存: $(free -h 2>/dev/null | awk '/^Mem:/ {print $2}' || echo '未知')"
    echo "磁盘空间: $(df -h / 2>/dev/null | awk 'NR==2 {print $4}' || echo '未知') 可用"
    echo
}

# 检测操作系统
detect_os() {
    # 尝试检测基于 RPM 的系统（CentOS/RHEL/Fedora/Rocky/AlmaLinux/openSUSE/Amazon Linux等）
    if command -v yum &> /dev/null || command -v dnf &> /dev/null || command -v zypper &> /dev/null || \
       [[ -f /etc/redhat-release ]] || [[ -f /etc/centos-release ]] || [[ -f /etc/rocky-release ]] || \
       [[ -f /etc/almalinux-release ]] || [[ -f /etc/fedora-release ]] || [[ -f /etc/amazon-linux-release ]] || \
       [[ -f /etc/SuSE-release ]] || [[ -f /etc/opensuse-release ]] || [[ -f /etc/oracle-release ]] || \
       [[ -f /etc/system-release ]] || grep -qi "red hat\|centos\|rocky\|alma\|fedora\|amazon\|oracle" /etc/os-release 2>/dev/null; then

        OS="rpm_based"
        # 优先级：dnf > yum > zypper
        if command -v dnf &> /dev/null; then
            PACKAGE_MANAGER="dnf"
        elif command -v yum &> /dev/null; then
            PACKAGE_MANAGER="yum"
        elif command -v zypper &> /dev/null; then
            PACKAGE_MANAGER="zypper"
        else
            # 最后的尝试
            PACKAGE_MANAGER="yum"
        fi
        log_info "检测到基于 RPM 的系统，使用包管理器: $PACKAGE_MANAGER"

    # 检测基于 DEB 的系统（Ubuntu/Debian/Mint/Pop!_OS等）
    elif command -v apt &> /dev/null || command -v apt-get &> /dev/null || \
         [[ -f /etc/debian_version ]] || [[ -f /etc/ubuntu-release ]] || \
         grep -qi "ubuntu\|debian\|mint\|pop" /etc/os-release 2>/dev/null; then

        OS="deb_based"
        PACKAGE_MANAGER="apt"
        log_info "检测到基于 DEB 的系统，使用包管理器: $PACKAGE_MANAGER"

    # 检测 Arch Linux 及其衍生版
    elif command -v pacman &> /dev/null || \
         [[ -f /etc/arch-release ]] || grep -qi "arch\|manjaro\|endeavour" /etc/os-release 2>/dev/null; then

        OS="arch_based"
        PACKAGE_MANAGER="pacman"
        log_info "检测到基于 Arch 的系统，使用包管理器: $PACKAGE_MANAGER"

    # 检测 Alpine Linux
    elif command -v apk &> /dev/null || grep -qi "alpine" /etc/os-release 2>/dev/null; then

        OS="alpine"
        PACKAGE_MANAGER="apk"
        log_info "检测到 Alpine Linux，使用包管理器: $PACKAGE_MANAGER"

    else
        # 如果无法自动检测，让用户选择
        log_warning "无法自动检测操作系统类型"
        echo "请选择您的系统类型："
        echo "1) 基于 RPM 的系统 (CentOS/RHEL/Rocky/AlmaLinux/Fedora/Amazon Linux/Oracle Linux等)"
        echo "2) 基于 DEB 的系统 (Ubuntu/Debian/Mint/Pop!_OS等)"
        echo "3) 基于 Arch 的系统 (Arch Linux/Manjaro/EndeavourOS等)"
        echo "4) Alpine Linux"
        read -p "请输入选项 (1-4): " choice

        case $choice in
            1)
                OS="rpm_based"
                if command -v dnf &> /dev/null; then
                    PACKAGE_MANAGER="dnf"
                elif command -v yum &> /dev/null; then
                    PACKAGE_MANAGER="yum"
                elif command -v zypper &> /dev/null; then
                    PACKAGE_MANAGER="zypper"
                else
                    PACKAGE_MANAGER="yum"
                fi
                log_info "手动选择: 基于 RPM 的系统，使用包管理器: $PACKAGE_MANAGER"
                ;;
            2)
                OS="deb_based"
                PACKAGE_MANAGER="apt"
                log_info "手动选择: 基于 DEB 的系统，使用包管理器: $PACKAGE_MANAGER"
                ;;
            3)
                OS="arch_based"
                PACKAGE_MANAGER="pacman"
                log_info "手动选择: 基于 Arch 的系统，使用包管理器: $PACKAGE_MANAGER"
                ;;
            4)
                OS="alpine"
                PACKAGE_MANAGER="apk"
                log_info "手动选择: Alpine Linux，使用包管理器: $PACKAGE_MANAGER"
                ;;
            *)
                log_error "无效选择，退出安装"
                exit 1
                ;;
        esac
    fi
}

# 安装系统依赖
install_system_dependencies() {
    log_info "安装系统依赖..."

    if [[ $OS == "deb_based" ]]; then
        log_info "更新软件包列表..."
        sudo apt update
        log_info "安装必需软件包..."
        sudo apt install -y python3 python3-pip python3-venv git nginx supervisor curl wget

    elif [[ $OS == "rpm_based" ]]; then
        log_info "更新软件包列表..."
        if [[ "$PACKAGE_MANAGER" == "zypper" ]]; then
            sudo zypper refresh
        else
            sudo $PACKAGE_MANAGER update -y
        fi

        # 安装 EPEL 源（对于 RHEL/CentOS 系列）
        if [[ "$PACKAGE_MANAGER" == "yum" ]] && command -v yum &> /dev/null; then
            sudo yum install -y epel-release || log_warning "EPEL 源安装失败，继续尝试..."
        elif [[ "$PACKAGE_MANAGER" == "dnf" ]] && grep -qi "rhel\|centos\|rocky\|alma\|oracle" /etc/os-release 2>/dev/null; then
            sudo dnf install -y epel-release || log_warning "EPEL 源安装失败，继续尝试..."
        fi

        log_info "安装必需软件包..."
        # 根据不同的包管理器使用不同的安装命令
        if [[ "$PACKAGE_MANAGER" == "zypper" ]]; then
            sudo zypper install -y python3 python3-pip git nginx supervisor curl wget || {
                log_warning "标准安装失败，尝试替代软件包名..."
                sudo zypper install -y python36 python36-pip git nginx supervisor curl wget || \
                sudo zypper install -y python38 python38-pip git nginx supervisor curl wget || \
                sudo zypper install -y python39 python39-pip git nginx supervisor curl wget
            }
        else
            # yum/dnf
            sudo $PACKAGE_MANAGER install -y python3 python3-pip git nginx supervisor curl wget || {
                log_warning "标准安装失败，尝试替代软件包名..."
                # 一些系统可能使用不同的包名
                sudo $PACKAGE_MANAGER install -y python36 python36-pip git nginx supervisor curl wget || \
                sudo $PACKAGE_MANAGER install -y python38 python38-pip git nginx supervisor curl wget || \
                sudo $PACKAGE_MANAGER install -y python39 python39-pip git nginx supervisor curl wget
            }
        fi

        # 确保 python3-venv 可用（在某些系统上可能需要单独安装）
        if ! python3 -m venv --help &> /dev/null; then
            log_info "安装 python3-venv..."
            if [[ "$PACKAGE_MANAGER" == "zypper" ]]; then
                sudo zypper install -y python3-venv || \
                sudo zypper install -y python36-venv || \
                sudo zypper install -y python38-venv || \
                sudo zypper install -y python39-venv || \
                log_warning "python3-venv 安装失败，将尝试使用 virtualenv"
            else
                sudo $PACKAGE_MANAGER install -y python3-venv || \
                sudo $PACKAGE_MANAGER install -y python36-venv || \
                sudo $PACKAGE_MANAGER install -y python38-venv || \
                sudo $PACKAGE_MANAGER install -y python39-venv || \
                log_warning "python3-venv 安装失败，将尝试使用 virtualenv"
            fi
        fi

    elif [[ $OS == "arch_based" ]]; then
        log_info "更新软件包列表..."
        sudo pacman -Sy
        log_info "安装必需软件包..."
        sudo pacman -S --needed --noconfirm python python-pip git nginx supervisor curl wget

    elif [[ $OS == "alpine" ]]; then
        log_info "更新软件包列表..."
        sudo apk update
        log_info "安装必需软件包..."
        sudo apk add python3 py3-pip git nginx supervisor curl wget

    else
        log_error "不支持的操作系统类型: $OS"
        exit 1
    fi

    # 验证关键命令是否可用
    log_info "验证安装结果..."
    local missing_commands=()

    for cmd in python3 git nginx; do
        if ! command -v $cmd &> /dev/null; then
            missing_commands+=("$cmd")
        fi
    done

    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        log_error "以下命令安装失败: ${missing_commands[*]}"
        log_error "请手动安装这些软件包后重新运行脚本"
        exit 1
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

    # 确定 Nginx 配置目录结构
    local nginx_config_dir="/etc/nginx"
    local nginx_sites_available="$nginx_config_dir/sites-available"
    local nginx_sites_enabled="$nginx_config_dir/sites-enabled"
    local nginx_conf_d="$nginx_config_dir/conf.d"

    # 创建必要的目录（如果不存在）
    if [[ $OS == "deb_based" ]]; then
        sudo mkdir -p "$nginx_sites_available" "$nginx_sites_enabled"
        config_file="$nginx_sites_available/ems-pool-gamble"
    else
        # RPM系列、Arch、Alpine 通常使用 conf.d 目录
        sudo mkdir -p "$nginx_conf_d"
        config_file="$nginx_conf_d/ems-pool-gamble.conf"
    fi

    # 创建 Nginx 配置文件
    sudo tee "$config_file" > /dev/null <<EOF
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

    # 启用站点配置
    if [[ $OS == "deb_based" ]]; then
        # Debian/Ubuntu 使用 sites-available/sites-enabled 结构
        sudo ln -sf "$nginx_sites_available/ems-pool-gamble" "$nginx_sites_enabled/"
        # 禁用默认站点
        sudo rm -f "$nginx_sites_enabled/default"
    else
        # 其他系统直接使用 conf.d，配置已经放在正确位置
        log_info "配置文件已放置在: $config_file"
    fi

    # 测试配置
    if ! sudo nginx -t; then
        log_error "Nginx 配置测试失败"
        exit 1
    fi

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

    # 启动并启用 Nginx
    if command -v systemctl &> /dev/null; then
        # 使用 systemd
        sudo systemctl enable nginx
        sudo systemctl restart nginx
        sudo systemctl enable supervisor
        sudo systemctl restart supervisor
    elif command -v service &> /dev/null; then
        # 使用传统的 service 命令
        sudo service nginx restart
        sudo service supervisor restart
        # 尝试启用服务（如果支持）
        if command -v chkconfig &> /dev/null; then
            sudo chkconfig nginx on
            sudo chkconfig supervisor on
        elif command -v update-rc.d &> /dev/null; then
            sudo update-rc.d nginx enable
            sudo update-rc.d supervisor enable
        fi
    elif [[ $OS == "alpine" ]]; then
        # Alpine Linux 使用 OpenRC
        sudo rc-update add nginx default
        sudo rc-update add supervisor default
        sudo service nginx restart
        sudo service supervisor restart
    else
        log_warning "无法检测到服务管理器，请手动启动 nginx 和 supervisor 服务"
    fi

    # 验证服务状态
    log_info "验证服务状态..."

    # 检查 Nginx
    if pgrep nginx > /dev/null; then
        log_success "Nginx 服务运行正常"
    else
        log_warning "Nginx 服务可能未正常启动"
    fi

    # 检查应用
    if sudo supervisorctl status ems-pool-gamble | grep -q RUNNING; then
        log_success "应用服务运行正常"
    else
        log_warning "应用服务可能未正常启动"
    fi

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
