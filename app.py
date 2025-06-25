from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from collections import defaultdict
import uuid
import datetime
import json
import os

# 应用版本信息
APP_VERSION = "v2.0.0"
APP_NAME = "EMS Pool Gamble"
VERSION_DATE = "2025-06-25"

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key_for_testing')  # 用于会话管理

# 数据库配置
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///ems_pool_gamble.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库
from models import db
db.init_app(app)

# 导入数据库服务
from database_service import DatabaseService

# 默认分数选项（只有正整数1-10）
DEFAULT_SCORE_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

# 应用启动时初始化数据库
with app.app_context():
    db.create_all()

    # 如果存在旧的 data.json 文件，自动迁移数据
    if os.path.exists('data.json'):
        try:
            from migrate_data import migrate_data_from_json
            migrate_data_from_json()
        except Exception as e:
            print(f"自动数据迁移失败: {e}")
            print("请手动运行 python migrate_data.py 进行数据迁移")

@app.route('/', methods=['GET', 'POST'])
def index():
    # 进入首页，显示当前进行中的场次列表
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create_session':
            # 创建新场次
            session_name = request.form['session_name'].strip()
            if not session_name:
                flash('场次名称不能为空', 'error')
                return redirect(url_for('index'))

            session_id = DatabaseService.create_session(session_name)
            flash(f'场次 "{session_name}" 创建成功', 'success')
            return redirect(url_for('index'))

        elif action == 'join_session':
            # 加入现有场次
            username = request.form['username'].strip()
            role = request.form['role']  # player/viewer
            session_id = request.form['session_id']

            # 验证用户名
            if not username:
                flash('用户名不能为空', 'error')
                return redirect(url_for('index'))

            if not DatabaseService.get_session(session_id):
                flash('场次不存在', 'error')
                return redirect(url_for('index'))

            # 注册用户
            if role == 'player':
                success, message = DatabaseService.add_player_to_session(session_id, username)
                if not success:
                    flash(message, 'error')
                    return redirect(url_for('index'))
            else:
                success, message = DatabaseService.add_viewer_to_session(session_id, username)
                if not success:
                    flash(message, 'error')
                    return redirect(url_for('index'))

            session['username'] = username
            session['role'] = role
            session['session_id'] = session_id

            # 记录用户名到浏览器缓存
            session['last_username'] = username

            return redirect(url_for('game'))

    # 获取所有场次
    all_sessions = DatabaseService.get_all_sessions()

    # 获取所有活跃的场次
    active_sessions = {k: v for k, v in all_sessions.items() if v.get('active', True)}
    sorted_active_sessions = sorted(
        active_sessions.items(),
        key=lambda x: x[1].get('timestamp', ''),
        reverse=True
    )

    # 获取最近结束的场次（最多3个）
    ended_sessions = {k: v for k, v in all_sessions.items() if not v.get('active', True)}
    sorted_ended_sessions = sorted(
        ended_sessions.items(),
        key=lambda x: x[1].get('end_time', x[1].get('timestamp', '')),
        reverse=True
    )[:3]

    # 获取上次登录的用户名
    last_username = session.get('last_username', '')

    # 检查用户当前的session_id是否仍然有效（场次是否还在进行中）
    current_session_id = session.get('session_id')
    if current_session_id:
        current_session_data = DatabaseService.get_session(current_session_id)
        if not current_session_data or not current_session_data.get('active', True):
            # 清除无效的session信息
            session.pop('session_id', None)
            if not current_session_data:
                flash('您所在的场次已被删除', 'error')
            else:
                flash('您所在的场次已结束', 'error')

    return render_template('index.html',
                         active_sessions=sorted_active_sessions,
                         ended_sessions=sorted_ended_sessions,
                         last_username=last_username,
                         sessions=all_sessions,
                         app_version=APP_VERSION,
                         app_name=APP_NAME,
                         version_date=VERSION_DATE)

@app.route('/game', methods=['GET', 'POST'])
def game():
    # 游戏主界面
    session_id = session.get('session_id')
    username = session.get('username')
    role = session.get('role')

    if not session_id:
        return redirect(url_for('index'))

    game_session_data = DatabaseService.get_session(session_id)
    if not game_session_data:
        return redirect(url_for('index'))

    # 检查场次是否已被结束
    if not game_session_data.get('active', True):
        # 清除用户的session信息
        session.pop('session_id', None)
        flash('该场次已经结束，您已被自动退出', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST' and role == 'player':
        winner = request.form['winner']
        loser = request.form['loser']
        score = int(request.form['score'])

        # 验证
        if winner == loser:
            flash('胜者和败者不能是同一个玩家', 'error')
        else:
            success, message = DatabaseService.add_game_record(session_id, winner, loser, score)
            if success:
                flash('成功记录分数', 'success')
            else:
                flash(message, 'error')

    # 重新获取最新的游戏数据
    game_session_data = DatabaseService.get_session(session_id)

    # 准备玩家列表，按分数排序
    sorted_players = sorted(
        [(p, game_session_data['scores'][p]) for p in game_session_data['players']],
        key=lambda x: x[1],
        reverse=True
    )

    # 获取最近玩家列表
    recent_players = DatabaseService.get_recent_players()

    return render_template(
        'game.html',
        session=game_session_data,
        username=username,
        role=role,
        score_options=DEFAULT_SCORE_OPTIONS,
        sorted_players=sorted_players,
        recent_players=recent_players,
        default_loser=next((p for p in game_session_data['players'] if p != username), ''),
        app_version=APP_VERSION
    )



@app.route('/history')
def history():
    # 展示所有场次和分数历史
    all_sessions = DatabaseService.get_all_sessions()

    sorted_sessions = sorted(
        all_sessions.items(),
        key=lambda x: x[1].get('timestamp', ''),
        reverse=True
    )

    # 计算全局玩家总分
    sorted_total_scores = DatabaseService.get_total_scores()

    return render_template('history.html',
                          sessions=dict(sorted_sessions),
                          total_scores=sorted_total_scores,
                          app_version=APP_VERSION)

@app.route('/logout')
def logout():
    session.clear()
    flash('您已成功退出', 'success')
    return redirect(url_for('index'))

@app.route('/end_session')
def end_session():
    # 结束当前场次
    session_id = session.get('session_id')
    username = session.get('username')
    role = session.get('role')

    if not session_id:
        return redirect(url_for('index'))

    game_session_data = DatabaseService.get_session(session_id)
    if not game_session_data:
        return redirect(url_for('index'))

    # 验证权限
    if role != 'player':
        flash('只有玩家可以结束场次', 'error')
        return redirect(url_for('game'))

    # 标记为非活跃
    DatabaseService.end_session(session_id)

    flash('本场比赛已结束', 'success')
    return redirect(url_for('history'))

@app.route('/api/scores')
def api_scores():
    """提供API接口获取分数数据，方便扩展"""
    session_id = request.args.get('session_id')
    if session_id:
        game_session_data = DatabaseService.get_session(session_id)
        if game_session_data:
            return jsonify({
                'players': list(game_session_data['players']),
                'scores': dict(game_session_data['scores']),
                'records': game_session_data['records']
            })

    return jsonify({'error': 'Invalid session ID'}), 400

@app.route('/add_player', methods=['POST'])
def add_player():
    # 在游戏中添加新玩家
    session_id = session.get('session_id')
    username = session.get('username')
    role = session.get('role')

    if not session_id:
        return redirect(url_for('index'))

    game_session_data = DatabaseService.get_session(session_id)
    if not game_session_data:
        return redirect(url_for('index'))

    # 检查场次是否已被结束
    if not game_session_data.get('active', True):
        session.pop('session_id', None)
        flash('该场次已经结束，您已被自动退出', 'error')
        return redirect(url_for('index'))

    # 验证权限
    if role != 'player':
        flash('只有玩家可以添加新玩家', 'error')
        return redirect(url_for('game'))

    new_player_name = request.form['new_player_name'].strip()
    if not new_player_name:
        flash('玩家名称不能为空', 'error')
        return redirect(url_for('game'))

    # 添加玩家
    success, message = DatabaseService.add_player_to_session(session_id, new_player_name)
    if success:
        flash(f'玩家 "{new_player_name}" 添加成功', 'success')
    else:
        flash(message, 'error')

    return redirect(url_for('game'))

@app.route('/delete_session/<session_id>')
def delete_session(session_id):
    # 删除场次
    username = session.get('username')
    role = session.get('role')

    game_session_data = DatabaseService.get_session(session_id)
    if not game_session_data:
        flash('场次不存在', 'error')
        return redirect(url_for('history'))

    # 验证权限：只有玩家才能删除场次
    if role != 'player' or username not in game_session_data['players']:
        flash('只有该场次的玩家才能删除场次', 'error')
        return redirect(url_for('session_detail', session_id=session_id))

    session_name = game_session_data['name']
    DatabaseService.delete_session(session_id)

    # 如果删除的是当前场次，清除session
    if session.get('session_id') == session_id:
        session.pop('session_id', None)

    flash(f'场次 "{session_name}" 已删除', 'success')
    return redirect(url_for('history'))

@app.route('/session_detail/<session_id>')
def session_detail(session_id):
    # 显示场次详情页
    game_session_data = DatabaseService.get_session(session_id)
    if not game_session_data:
        flash('场次不存在', 'error')
        return redirect(url_for('index'))

    # 按分数排序玩家
    sorted_players = sorted(
        [(p, game_session_data['scores'][p]) for p in game_session_data['players']],
        key=lambda x: x[1],
        reverse=True
    )

    return render_template('session_detail.html',
                         session_id=session_id,
                         session_data=game_session_data,
                         sorted_players=sorted_players,
                         app_version=APP_VERSION)

@app.route('/delete_record/<int:record_index>', methods=['POST'])
def delete_record(record_index):
    # 删除计分记录
    session_id = session.get('session_id')
    username = session.get('username')
    role = session.get('role')

    if not session_id:
        return redirect(url_for('index'))

    game_session_data = DatabaseService.get_session(session_id)
    if not game_session_data:
        return redirect(url_for('index'))

    # 检查场次是否已被结束
    if not game_session_data.get('active', True):
        session.pop('session_id', None)
        flash('该场次已经结束，无法删除记录', 'error')
        return redirect(url_for('index'))

    # 验证权限
    if role != 'player':
        flash('只有玩家可以删除计分记录', 'error')
        return redirect(url_for('game'))

    # 删除记录
    success, message = DatabaseService.delete_game_record(session_id, record_index)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')

    return redirect(url_for('game'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true')
