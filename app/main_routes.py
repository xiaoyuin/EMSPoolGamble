"""
主要路由模块 - 首页、历史、场次详情等
"""
import uuid
from collections import defaultdict
from flask import render_template, request, redirect, url_for, flash, jsonify
from .models import (sessions, players, save_data, get_player_by_name, get_player_name,
                     create_session, get_active_sessions, get_ended_sessions, 
                     get_all_sessions, delete_session, get_session,
                     get_players_special_wins_batch)
from .utils import get_utc_timestamp, generate_session_name
from .security import require_admin_auth, require_csrf_protection
from . import APP_VERSION, APP_NAME, VERSION_DATE


def register_main_routes(app):
    """注册主要路由"""
    
    @app.route('/', methods=['GET', 'POST'])
    def index():
        # 进入首页，显示当前进行中的场次列表
        if request.method == 'POST':
            action = request.form.get('action')

            if action == 'create_session':
                # 从前端接收房间名称
                session_name = request.form.get('session_name', '').strip()
                
                # 如果前端没有提供房间名称，使用服务器时间生成（降级处理）
                if not session_name:
                    session_name = generate_session_name()

                # 如果已经存在相同名称的活跃场次，添加序号
                active_sessions_list = get_active_sessions()
                existing_names = [s['name'] for s in active_sessions_list]
                counter = 1
                original_name = session_name
                while session_name in existing_names:
                    counter += 1
                    session_name = f"{original_name} ({counter})"

                session_id = create_session(session_name)

                # 保存数据（数据库自动保存）
                save_data()
                flash(f'场次 "{session_name}" 创建成功', 'success')
                # 直接进入新创建的房间
                return redirect(url_for('game', session_id=session_id))

            elif action == 'join_session':
                # 直接加入现有场次，所有人都是玩家
                session_id = request.form['session_id']

                if session_id not in sessions:
                    flash('场次不存在', 'error')
                    return redirect(url_for('index'))

                # 直接跳转到游戏页面，无需登录
                return redirect(url_for('game', session_id=session_id))

        # 获取所有活跃的场次（包含完整信息）
        active_sessions_list = get_active_sessions()
        sorted_active_sessions = []
        for session in active_sessions_list:
            session_id = session['session_id']
            full_session = get_session(session_id)  # 获取包含玩家信息的完整数据
            if full_session:
                sorted_active_sessions.append((session_id, full_session))

        # 获取最近结束的场次（最多3个，包含完整信息）
        ended_sessions_list = get_ended_sessions(3)
        sorted_ended_sessions = []
        for session in ended_sessions_list:
            session_id = session['session_id']
            full_session = get_session(session_id)  # 获取包含玩家信息的完整数据
            if full_session:
                sorted_ended_sessions.append((session_id, full_session))

        return render_template('index.html',
                             active_sessions=sorted_active_sessions,
                             ended_sessions=sorted_ended_sessions,
                             sessions=sessions,
                             suggested_session_name=generate_session_name(),  # 默认用服务器时间，前端会替换
                             app_version=APP_VERSION,
                             app_name=APP_NAME,
                             version_date=VERSION_DATE)

    @app.route('/history')
    def history():
        # 展示所有场次和分数历史
        all_sessions_list = get_all_sessions()
        
        # 计算全局玩家总分，包含player_id
        from .models import get_global_leaderboard
        sorted_total_scores = get_global_leaderboard()

        # 收集所有玩家ID用于批量查询特殊胜利记录
        all_player_ids = set()
        for player in sorted_total_scores:
            if player.get('player_id'):
                all_player_ids.add(player['player_id'])

        # 获取每个场次的完整信息（包含players_with_ids）
        sessions_with_player_ids = {}
        for session_data in all_sessions_list:
            sid = session_data['session_id']
            # 获取完整场次信息包含玩家数据
            full_session = get_session(sid)
            if full_session:
                sessions_with_player_ids[sid] = full_session
                # 收集场次中的玩家ID
                for player in full_session.get('players_with_ids', []):
                    if player.get('id'):
                        all_player_ids.add(player['id'])

        # 批量获取所有玩家的特殊胜利记录
        players_special_wins = get_players_special_wins_batch(list(all_player_ids)) if all_player_ids else {}

        # 将特殊胜利记录添加到全局排行榜数据中
        for player in sorted_total_scores:
            player_id = player.get('player_id')
            if player_id and player_id in players_special_wins:
                player.update(players_special_wins[player_id])
            else:
                player.update({'has_small_gold': False, 'has_big_gold': False})

        # 将特殊胜利记录添加到场次玩家数据中
        for session in sessions_with_player_ids.values():
            for player in session.get('players_with_ids', []):
                player_id = player.get('id')
                if player_id and player_id in players_special_wins:
                    player.update(players_special_wins[player_id])
                else:
                    player.update({'has_small_gold': False, 'has_big_gold': False})

        return render_template('history.html',
                              sessions=sessions_with_player_ids,
                              total_scores=sorted_total_scores,
                              app_version=APP_VERSION)

    @app.route('/session_detail/<session_id>')
    def session_detail(session_id):
        # 显示场次详情页
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        session_data = get_session(session_id)
        if not session_data:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        # 构建包含player_id的玩家列表并按分数排序
        players_with_ids = []
        player_ids = []
        for player_name in session_data.get('players', set()):
            player_id = get_player_by_name(player_name)
            score = session_data.get('scores', {}).get(player_name, 0)
            players_with_ids.append({
                'name': player_name,
                'id': player_id,
                'score': score
            })
            if player_id:
                player_ids.append(player_id)

        # 获取玩家的特殊胜利记录
        players_special_wins = get_players_special_wins_batch(player_ids) if player_ids else {}

        # 将特殊胜利记录添加到玩家信息中
        for player in players_with_ids:
            player_id = player.get('id')
            if player_id and player_id in players_special_wins:
                player.update(players_special_wins[player_id])
            else:
                player.update({'has_small_gold': False, 'has_big_gold': False})

        # 按分数排序
        sorted_players = sorted(players_with_ids, key=lambda x: x['score'], reverse=True)

        # 获取计分记录
        records_with_ids = session_data.get('records', [])

        return render_template('session_detail.html',
                             session_id=session_id,
                             session_data=session_data,
                             sorted_players=sorted_players,
                             records=records_with_ids,
                             app_version=APP_VERSION)

    @app.route('/delete_session/<session_id>', methods=['POST'])
    @require_admin_auth
    @require_csrf_protection
    def delete_session_route(session_id):
        # 删除场次
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('history'))

        # 获取场次名称用于提示
        session_data = get_session(session_id)
        session_name = session_data['name'] if session_data else '未知场次'
        
        # 删除场次
        success = delete_session(session_id)
        
        if success:
            # 保存数据（数据库自动保存）
            save_data()
            flash(f'场次 "{session_name}" 已删除', 'success')
        else:
            flash('删除场次失败', 'error')
            
        return redirect(url_for('history'))

    @app.route('/api/scores')
    def api_scores():
        """提供API接口获取分数数据，方便扩展"""
        session_id = request.args.get('session_id')
        if session_id and session_id in sessions:
            return jsonify({
                'players': list(sessions[session_id]['players']),
                'scores': dict(sessions[session_id]['scores']),
                'records': sessions[session_id]['records']
            })
        else:
            return jsonify({'error': 'Invalid session ID'}), 400
