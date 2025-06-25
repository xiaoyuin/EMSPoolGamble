#!/usr/bin/env python3
"""
应用启动脚本
自动处理依赖安装和数据库初始化
"""
import subprocess
import sys
import os

def install_requirements():
    """安装依赖包"""
    print("正在安装依赖包...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("依赖包安装完成！")
        return True
    except subprocess.CalledProcessError as e:
        print(f"依赖包安装失败: {e}")
        return False

def check_and_migrate_data():
    """检查并迁移数据"""
    if os.path.exists('data.json'):
        print("发现旧的 data.json 文件，正在迁移数据...")
        try:
            from migrate_data import migrate_data_from_json
            from app import app, db

            with app.app_context():
                db.create_all()
                migrate_data_from_json()

            print("数据迁移完成！")
        except Exception as e:
            print(f"数据迁移失败: {e}")
            print("您可以稍后手动运行 'python migrate_data.py' 来迁移数据")

def main():
    """主函数"""
    print("=== EMS Pool Gamble 启动脚本 ===")

    # 检查是否需要安装依赖
    try:
        import flask_sqlalchemy
        print("依赖检查：✓ 所有依赖已安装")
    except ImportError:
        print("依赖检查：✗ 缺少必要依赖")
        if not install_requirements():
            print("无法安装依赖，请手动运行: pip install -r requirements.txt")
            return False

    # 检查并迁移数据
    check_and_migrate_data()

    print("\n启动应用...")

    # 启动Flask应用
    try:
        from app import app
        port = int(os.environ.get('PORT', 5000))
        debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

        print(f"应用启动在 http://localhost:{port}")
        print("按 Ctrl+C 停止应用")

        app.run(host='0.0.0.0', port=port, debug=debug)
    except Exception as e:
        print(f"应用启动失败: {e}")
        return False

    return True

if __name__ == '__main__':
    success = main()
    if not success:
        sys.exit(1)
