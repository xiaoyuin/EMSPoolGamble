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
from app.achievement_routes import register_achievement_routes
from app.tournament_routes import register_tournament_routes
from app.security import register_security_routes


def create_app():
    """创建Flask应用实例"""
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key_for_testing')

    # 设置session持久化时间（7天）
    app.permanent_session_lifetime = 604800

    # 初始化数据
    init_data()

    # 注册路由
    register_main_routes(app)
    register_game_routes(app)
    register_player_routes(app)
    register_achievement_routes(app)
    register_tournament_routes(app)
    register_security_routes(app)

    return app


# 创建应用实例供uWSGI使用
application = create_app()

# 为了兼容性，也创建app变量
app = application


if __name__ == '__main__':
    # 输出数据存储位置信息
    data_file = get_data_file_path()
    is_azure = os.environ.get('WEBSITE_SITE_NAME') is not None

    # 获取统计信息
    from app.models import get_all_sessions, get_player_by_id
    from app.database import db
    all_sessions = get_all_sessions()
    all_players = db.get_all_players()

    print(f"")
    print(f"🎱 {APP_NAME} {APP_VERSION}")
    print(f"📊 数据存储位置: SQLite数据库 ({db.db_path})")
    print(f"☁️  Azure环境: {'是' if is_azure else '否'}")
    print(f"📝 已加载 {len(all_sessions)} 个场次, {len(all_players)} 个玩家")
    print(f"")

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true')
