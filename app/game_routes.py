"""
游戏相关路由模块 - 游戏界面、计分、玩家管理等
"""
from flask import render_template, request, redirect, url_for, session, flash
from .models import (sessions, players, recent_player_ids, save_data, 
                     get_player_by_name, get_player_name, get_or_create_player)
from .utils import get_utc_timestamp
from . import DEFAULT_SCORE_OPTIONS, APP_VERSION


def register_game_routes(app):
    """注册游戏相关路由"""
    
    @app.route('/game')
    @app.route('/game/<session_id>')
    def game(session_id=None):
        # 游戏主界面 - 通过URL参数或session获取session_id
        if session_id is None:
            session_id = session.get('session_id')

        if not session_id or session_id not in sessions:
            flash('请先选择一个场次', 'error')
            return redirect(url_for('index'))

        game_session = sessions[session_id]

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束', 'error')
            return redirect(url_for('index'))

        # 准备玩家列表，按分数排序，包含player_id
        # 确保所有玩家都在scores字典中有条目
        for player in game_session['players']:
            if player not in game_session['scores']:
                game_session['scores'][player] = 0

        # 构建包含player_id的玩家列表
        players_with_ids = []
        for player_name in game_session['players']:
            player_id = get_player_by_name(player_name)
            score = game_session['scores'][player_name]
            players_with_ids.append({
                'name': player_name,
                'id': player_id,
                'score': score
            })

        # 按分数排序
        sorted_players = sorted(players_with_ids, key=lambda x: x['score'], reverse=True)

        # 准备最近玩家的信息（用于显示）
        recent_player_data = []
        for pid in recent_player_ids:
            player_name = get_player_name(pid)
            if player_name not in game_session['players']:  # 只显示不在当前场次的玩家
                recent_player_data.append({
                    'id': pid,
                    'name': player_name
                })

        return render_template(
            'game.html',
            session_id=session_id,
            session=game_session,
            score_options=DEFAULT_SCORE_OPTIONS,
            sorted_players=sorted_players,
            recent_players=recent_player_data,  # 传递包含ID的最近玩家列表
            app_version=APP_VERSION
        )

    @app.route('/add_player/<session_id>', methods=['POST'])
    def add_player(session_id):
        global recent_player_ids
        # 在游戏中添加新玩家
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        game_session = sessions[session_id]

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束', 'error')
            return redirect(url_for('index'))

        new_player_name = request.form['new_player_name'].strip()
        if not new_player_name:
            flash('玩家名称不能为空', 'error')
            return redirect(url_for('game', session_id=session_id))

        # 检查玩家是否已存在（按名字）
        if new_player_name in game_session['players'] or new_player_name in game_session['viewers']:
            flash('该用户名已存在', 'error')
            return redirect(url_for('game', session_id=session_id))

        # 获取或创建玩家
        player_id = get_or_create_player(new_player_name)

        # 添加玩家到场次
        game_session['player_ids'].add(player_id)
        game_session['players'].add(new_player_name)  # 为了兼容性保留
        game_session['scores'][new_player_name] = 0

        # 更新最近玩家列表
        if player_id not in recent_player_ids:
            recent_player_ids.append(player_id)
            # 只保留最近10个玩家
            if len(recent_player_ids) > 10:
                recent_player_ids = recent_player_ids[-10:]

        # 保存数据
        save_data()

        flash(f'玩家 "{new_player_name}" 添加成功', 'success')
        return redirect(url_for('game', session_id=session_id))

    @app.route('/add_score/<session_id>', methods=['POST'])
    def add_score(session_id):
        # 记分功能
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        game_session = sessions[session_id]

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束', 'error')
            return redirect(url_for('index'))

        winner = request.form['winner']
        loser = request.form['loser']
        score = int(request.form['score'])

        # 获取用户时区偏移量
        timezone_offset = request.form.get('timezone_offset')
        try:
            timezone_offset_minutes = int(timezone_offset) if timezone_offset else None
        except (ValueError, TypeError):
            timezone_offset_minutes = None

        # 验证
        if winner == loser:
            flash('胜者和败者不能是同一个玩家', 'error')
        elif winner not in game_session['players'] or loser not in game_session['players']:
            flash('选择的玩家不在当前场次中', 'error')
        else:
            # 获取玩家ID
            winner_id = get_player_by_name(winner)
            loser_id = get_player_by_name(loser)

            # 记录本次计分
            record_data = {
                'winner': winner,
                'loser': loser,
                'winner_id': winner_id,
                'loser_id': loser_id,
                'score': score,
                'timestamp': get_utc_timestamp()
            }
            game_session['records'].append(record_data)

            # 更新分数
            game_session['scores'][winner] += score
            game_session['scores'][loser] -= score

            # 保存数据
            save_data()
            flash('成功记录分数', 'success')

        return redirect(url_for('game', session_id=session_id))

    @app.route('/add_special_score/<session_id>', methods=['POST'])
    def add_special_score(session_id):
        # 处理特殊分数（14分和20分）的记分功能
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        game_session = sessions[session_id]

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束', 'error')
            return redirect(url_for('index'))

        winner = request.form.get('winner')
        losers = request.form.getlist('losers')  # 获取多个败者
        total_score = int(request.form.get('score', 0))

        # 验证输入
        if not winner or not losers or total_score not in [14, 20]:
            flash('请选择胜者、败者和正确的分数', 'error')
            return redirect(url_for('game', session_id=session_id))

        if winner in losers:
            flash('胜者不能同时是败者', 'error')
            return redirect(url_for('game', session_id=session_id))

        if len(losers) != 2:
            flash('特殊分数需要选择两个败者', 'error')
            return redirect(url_for('game', session_id=session_id))

        # 检查所有玩家是否存在
        all_players = [winner] + losers
        for player in all_players:
            if player not in game_session['players']:
                flash(f'玩家 {player} 不在当前场次中', 'error')
                return redirect(url_for('game', session_id=session_id))

        # 计算分数
        half_score = total_score // 2

        # 获取用户时区偏移量
        timezone_offset = request.form.get('timezone_offset')
        try:
            timezone_offset_minutes = int(timezone_offset) if timezone_offset else None
        except (ValueError, TypeError):
            timezone_offset_minutes = None

        # 获取玩家ID
        winner_id = get_player_by_name(winner)
        loser_ids = [get_player_by_name(loser) for loser in losers]

        # 记录第一笔：胜者得分，第一个败者失分
        record_data_1 = {
            'winner': winner,
            'loser': losers[0],
            'winner_id': winner_id,
            'loser_id': loser_ids[0],
            'score': half_score,
            'timestamp': get_utc_timestamp()
        }
        game_session['records'].append(record_data_1)

        # 记录第二笔：胜者得分，第二个败者失分
        record_data_2 = {
            'winner': winner,
            'loser': losers[1],
            'winner_id': winner_id,
            'loser_id': loser_ids[1],
            'score': half_score,
            'timestamp': get_utc_timestamp()
        }
        game_session['records'].append(record_data_2)

        # 更新分数
        game_session['scores'][winner] += total_score
        game_session['scores'][losers[0]] -= half_score
        game_session['scores'][losers[1]] -= half_score

        # 保存数据
        save_data()
        flash(f'成功记录特殊分数：{winner} 胜 {losers[0]}+{losers[1]} ({total_score}分)', 'success')

        return redirect(url_for('game', session_id=session_id))

    @app.route('/delete_record/<session_id>/<int:record_index>', methods=['POST'])
    def delete_record(session_id, record_index):
        # 删除计分记录
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        game_session = sessions[session_id]

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束，无法删除记录', 'error')
            return redirect(url_for('index'))

        # 验证记录索引
        if record_index < 0 or record_index >= len(game_session['records']):
            flash('无效的记录索引', 'error')
            return redirect(url_for('game', session_id=session_id))

        # 获取要删除的记录
        record_to_delete = game_session['records'][record_index]

        # 恢复分数（撤销这条记录的分数变化）
        winner = record_to_delete['winner']
        loser = record_to_delete['loser']
        score = record_to_delete['score']

        # 撤销分数变化
        game_session['scores'][winner] -= score
        game_session['scores'][loser] += score

        # 删除记录
        del game_session['records'][record_index]

        # 保存数据
        save_data()

        flash(f'已删除记录：{winner} 胜 {loser} ({score}分)', 'success')
        return redirect(url_for('game', session_id=session_id))

    @app.route('/end_session/<session_id>')
    def end_session(session_id):
        # 结束当前场次（GET方式，兼容性保留）
        return end_session_post(session_id)

    @app.route('/end_session/<session_id>', methods=['POST'])
    def end_session_post(session_id):
        # 结束当前场次
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        # 获取用户时区偏移量（POST请求才有）
        timezone_offset = request.form.get('timezone_offset') if request.method == 'POST' else None
        try:
            timezone_offset_minutes = int(timezone_offset) if timezone_offset else None
        except (ValueError, TypeError):
            timezone_offset_minutes = None

        # 标记为非活跃
        sessions[session_id]['active'] = False
        sessions[session_id]['end_time'] = get_utc_timestamp()  # 统一使用UTC时间存储

        # 保存数据
        save_data()

        flash('本场比赛已结束', 'success')
        return redirect(url_for('history'))
