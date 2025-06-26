"""
主要路由模块 - 首页、历史、场次详情等
"""
import uuid
from collections import defaultdict
from flask import render_template, request, redirect, url_for, flash, jsonify
from .models import sessions, players, save_data, get_player_by_name, get_player_name
from .utils import get_utc_timestamp, generate_session_name
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
                existing_names = [s['name'] for s in sessions.values() if s.get('active', True)]
                counter = 1
                original_name = session_name
                while session_name in existing_names:
                    counter += 1
                    session_name = f"{original_name} ({counter})"

                session_id = str(uuid.uuid4())
                sessions[session_id] = {
                    'name': session_name,
                    'players': set(),          # 暂时保留用于显示
                    'player_ids': set(),       # 新增：存储玩家ID
                    'viewers': set(),
                    'records': [],             # 改为records存储计分记录
                    'scores': defaultdict(int),
                    'active': True,
                    'timestamp': get_utc_timestamp()  # 统一使用UTC时间存储
                }

                # 保存数据
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

        # 获取所有活跃的场次
        active_sessions = {k: v for k, v in sessions.items() if v.get('active', True)}
        sorted_active_sessions = sorted(
            active_sessions.items(),
            key=lambda x: x[1].get('timestamp', ''),
            reverse=True
        )

        # 获取最近结束的场次（最多3个）
        ended_sessions = {k: v for k, v in sessions.items() if not v.get('active', True)}
        sorted_ended_sessions = sorted(
            ended_sessions.items(),
            key=lambda x: x[1].get('end_time', x[1].get('timestamp', '')),
            reverse=True
        )[:3]

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
        sorted_sessions = sorted(
            sessions.items(),
            key=lambda x: x[1].get('timestamp', ''),
            reverse=True
        )

        # 计算全局玩家总分，包含player_id
        total_scores = defaultdict(int)
        for _, s in sessions.items():
            for p in s['players']:
                total_scores[p] += s['scores'][p]

        # 构建包含player_id的排行榜数据
        sorted_total_scores = []
        for player_name, score in total_scores.items():
            player_id = get_player_by_name(player_name)
            sorted_total_scores.append({
                'name': player_name,
                'id': player_id,
                'score': score
            })

        # 按分数排序
        sorted_total_scores.sort(key=lambda x: x['score'], reverse=True)

        # 为每个场次构建包含player_id的玩家数据
        sessions_with_player_ids = {}
        for sid, session_data in sorted_sessions:
            session_copy = session_data.copy()
            # 构建包含ID的玩家列表
            players_with_ids = []
            for player_name in session_data['players']:
                player_id = get_player_by_name(player_name)
                score = session_data['scores'].get(player_name, 0)
                players_with_ids.append({
                    'name': player_name,
                    'id': player_id,
                    'score': score
                })

            # 按分数排序
            players_with_ids.sort(key=lambda x: x['score'], reverse=True)
            session_copy['players_with_ids'] = players_with_ids
            sessions_with_player_ids[sid] = session_copy

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

        session_data = sessions[session_id]

        # 构建包含player_id的玩家列表并按分数排序
        players_with_ids = []
        for player_name in session_data['players']:
            player_id = get_player_by_name(player_name)
            score = session_data['scores'].get(player_name, 0)
            players_with_ids.append({
                'name': player_name,
                'id': player_id,
                'score': score
            })

        # 按分数排序
        sorted_players = sorted(players_with_ids, key=lambda x: x['score'], reverse=True)

        # 为记录添加玩家ID（如果需要）
        records_with_ids = []
        for record in session_data.get('records', []):
            record_copy = record.copy()
            if 'winner_id' not in record_copy and 'winner' in record_copy:
                record_copy['winner_id'] = get_player_by_name(record_copy['winner'])
            if 'loser_id' not in record_copy and 'loser' in record_copy:
                record_copy['loser_id'] = get_player_by_name(record_copy['loser'])
            records_with_ids.append(record_copy)

        return render_template('session_detail.html',
                             session_id=session_id,
                             session_data=session_data,
                             sorted_players=sorted_players,
                             records=records_with_ids,
                             app_version=APP_VERSION)

    @app.route('/delete_session/<session_id>')
    def delete_session(session_id):
        # 删除场次
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('history'))

        session_name = sessions[session_id]['name']
        del sessions[session_id]

        # 保存数据
        save_data()

        flash(f'场次 "{session_name}" 已删除', 'success')
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
