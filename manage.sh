#!/bin/bash
# EMS Pool Gamble 管理脚本 - 统一管理入口

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# 显示标题
show_title() {
    echo -e "${BLUE}"
    echo "========================================"
    echo "    EMS Pool Gamble 管理工具"
    echo "========================================"
    echo -e "${NC}"
}

# 显示菜单
show_menu() {
    echo "请选择操作："
    echo
    echo -e "${GREEN}部署相关:${NC}"
    echo "  1) 首次部署      - 在全新 Linux 环境中部署应用"
    echo "  2) 更新部署      - 更新代码（保留数据）"
    echo "  3) 环境检查      - 检查系统环境和服务状态"
    echo
    echo -e "${GREEN}数据管理:${NC}"
    echo "  4) 备份数据      - 创建数据库备份"
    echo "  5) 恢复数据      - 从备份恢复数据库"
    echo "  6) 列出备份      - 显示所有备份文件"
    echo
    echo -e "${GREEN}服务管理:${NC}"
    echo "  7) 启动服务      - 启动应用服务"
    echo "  8) 停止服务      - 停止应用服务"
    echo "  9) 重启服务      - 重启应用服务"
    echo " 10) 查看状态      - 查看服务运行状态"
    echo " 11) 查看日志      - 查看应用日志"
    echo
    echo -e "${GREEN}其他:${NC}"
    echo " 12) 生成诊断报告  - 生成详细的系统诊断报告"
    echo "  0) 退出"
    echo
}

# 确保脚本可执行
make_executable() {
    chmod +x deploy.sh backup.sh update.sh check.sh 2>/dev/null || true
}

# 部署应用
deploy_app() {
    echo -e "${BLUE}开始首次部署...${NC}"
    if [[ -f "deploy.sh" ]]; then
        ./deploy.sh
    else
        echo -e "${RED}错误: deploy.sh 文件不存在${NC}"
    fi
}

# 更新应用
update_app() {
    echo -e "${BLUE}开始更新部署...${NC}"
    if [[ -f "update.sh" ]]; then
        ./update.sh
    else
        echo -e "${RED}错误: update.sh 文件不存在${NC}"
    fi
}

# 检查环境
check_environment() {
    echo -e "${BLUE}开始环境检查...${NC}"
    if [[ -f "check.sh" ]]; then
        ./check.sh
    else
        echo -e "${RED}错误: check.sh 文件不存在${NC}"
    fi
}

# 备份数据
backup_data() {
    echo -e "${BLUE}开始数据备份...${NC}"
    if [[ -f "backup.sh" ]]; then
        ./backup.sh backup
    else
        echo -e "${RED}错误: backup.sh 文件不存在${NC}"
    fi
}

# 恢复数据
restore_data() {
    echo -e "${BLUE}数据恢复${NC}"
    if [[ -f "backup.sh" ]]; then
        echo "可用的备份文件："
        ./backup.sh list
        echo
        read -p "请输入要恢复的备份文件名: " backup_file
        if [[ -n "$backup_file" ]]; then
            ./backup.sh restore "$backup_file"
        else
            echo -e "${RED}未指定备份文件${NC}"
        fi
    else
        echo -e "${RED}错误: backup.sh 文件不存在${NC}"
    fi
}

# 列出备份
list_backups() {
    echo -e "${BLUE}备份文件列表${NC}"
    if [[ -f "backup.sh" ]]; then
        ./backup.sh list
    else
        echo -e "${RED}错误: backup.sh 文件不存在${NC}"
    fi
}

# 服务管理
manage_service() {
    local action=$1
    case $action in
        start)
            echo -e "${BLUE}启动服务...${NC}"
            sudo supervisorctl start ems-pool-gamble
            ;;
        stop)
            echo -e "${BLUE}停止服务...${NC}"
            sudo supervisorctl stop ems-pool-gamble
            ;;
        restart)
            echo -e "${BLUE}重启服务...${NC}"
            sudo supervisorctl restart ems-pool-gamble
            ;;
        status)
            echo -e "${BLUE}服务状态:${NC}"
            sudo supervisorctl status ems-pool-gamble
            echo
            echo -e "${BLUE}Nginx 状态:${NC}"
            sudo systemctl status nginx --no-pager -l
            ;;
        logs)
            echo -e "${BLUE}应用日志 (按 Ctrl+C 退出):${NC}"
            sudo tail -f /var/log/ems-pool-gamble.log
            ;;
    esac
}

# 生成诊断报告
generate_diagnostic() {
    echo -e "${BLUE}生成诊断报告...${NC}"
    if [[ -f "check.sh" ]]; then
        ./check.sh --report
    else
        echo -e "${RED}错误: check.sh 文件不存在${NC}"
    fi
}

# 主函数
main() {
    # 确保在正确的目录
    if [[ ! -f "app.py" ]]; then
        echo -e "${RED}错误: 请在 EMS Pool Gamble 项目根目录下运行此脚本${NC}"
        exit 1
    fi

    # 确保脚本可执行
    make_executable

    while true; do
        show_title
        show_menu

        read -p "请输入选项 (0-12): " choice
        echo

        case $choice in
            1)
                deploy_app
                ;;
            2)
                update_app
                ;;
            3)
                check_environment
                ;;
            4)
                backup_data
                ;;
            5)
                restore_data
                ;;
            6)
                list_backups
                ;;
            7)
                manage_service start
                ;;
            8)
                manage_service stop
                ;;
            9)
                manage_service restart
                ;;
            10)
                manage_service status
                ;;
            11)
                manage_service logs
                ;;
            12)
                generate_diagnostic
                ;;
            0)
                echo -e "${GREEN}退出管理工具${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}无效选项，请重新选择${NC}"
                ;;
        esac

        echo
        read -p "按任意键继续..." -n 1
        clear
    done
}

# 运行主函数
main "$@"
