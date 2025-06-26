"""
EMS Pool Gamble - 多人台球计分 Web 应用
主应用入口文件
"""
import os
from flask import Flask
from app import APP_VERSION, APP_NAME, VERSION_DATE
from app.models import init_data, get_data_file_path, sessions, players
from app.main_routes import register_main_routes
from app.game_routes import register_game_routes
from app.player_routes import register_player_routes


def create_app():
    """创建Flask应用实例"""
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key_for_testing')
    
    # 初始化数据
    init_data()
    
    # 注册路由
    register_main_routes(app)
    register_game_routes(app)
    register_player_routes(app)
    
    return app


if __name__ == '__main__':
    # 创建应用
    app = create_app()
    
    # 输出数据存储位置信息
    data_file = get_data_file_path()
    is_azure = os.environ.get('WEBSITE_SITE_NAME') is not None
    print(f"")
    print(f"🎱 {APP_NAME} {APP_VERSION}")
    print(f"📊 数据存储位置: {data_file}")
    print(f"☁️  Azure环境: {'是' if is_azure else '否'}")
    print(f"📝 已加载 {len(sessions)} 个场次, {len(players)} 个玩家")
    print(f"")

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true')
