"""
游戏相关路由模块 - 游戏界面、计分、玩家管理等
"""
from flask import render_template, request, redirect, url_for, session, flash
from .models import (sessions, players, save_data, 
                     get_player_by_name, get_player_name, get_or_create_player, create_player,
                     get_available_players, get_session,
                     add_player_to_session, add_game_record, delete_game_record,
                     end_session, delete_session, add_multi_loser_record)
from .utils import get_utc_timestamp
from .security import require_admin_auth, require_csrf_protection
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

        game_session = get_session(session_id)
        if not game_session:
            flash('请先选择一个场次', 'error')
            return redirect(url_for('index'))

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束，跳转到详情页面查看结果', 'info')
            return redirect(url_for('session_detail', session_id=session_id))

        # 准备玩家列表，按分数排序，包含player_id
        # 构建包含player_id的玩家列表
        players_with_ids = []
        for player_name in game_session.get('players', set()):
            player_id = get_player_by_name(player_name)
            score = game_session.get('scores', {}).get(player_name, 0)
            players_with_ids.append({
                'name': player_name,
                'id': player_id,
                'score': score
            })

        # 按分数排序
        sorted_players = sorted(players_with_ids, key=lambda x: x['score'], reverse=True)

        # 准备可用玩家的信息（用于显示）
        available_player_data = get_available_players(exclude_session_id=session_id)

        return render_template(
            'game.html',
            session_id=session_id,
            session=game_session,
            score_options=DEFAULT_SCORE_OPTIONS,
            sorted_players=sorted_players,
            recent_players=available_player_data,  # 传递包含ID的可用玩家列表
            app_version=APP_VERSION
        )

    @app.route('/add_player/<session_id>', methods=['POST'])
    def add_player(session_id):
        # 在游戏中添加新玩家
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        game_session = get_session(session_id)
        if not game_session:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束', 'error')
            return redirect(url_for('index'))

        new_player_name = request.form['new_player_name'].strip()
        if not new_player_name:
            flash('玩家名称不能为空', 'error')
            return redirect(url_for('game', session_id=session_id))

        # 检查玩家是否已存在（按名字）
        if new_player_name in game_session.get('players', set()):
            flash('该用户名已存在', 'error')
            return redirect(url_for('game', session_id=session_id))

        # 获取或创建玩家
        player_id = get_or_create_player(new_player_name)

        # 添加玩家到场次
        success = add_player_to_session(session_id, player_id)
        if not success:
            flash('添加玩家失败，可能已存在', 'error')
            return redirect(url_for('game', session_id=session_id))

        # 保存数据（数据库自动保存）
        save_data()

        flash(f'玩家 "{new_player_name}" 添加成功', 'success')
        return redirect(url_for('game', session_id=session_id))

    @app.route('/batch_add_players/<session_id>', methods=['POST'])
    def batch_add_players(session_id):
        # 批量添加玩家功能
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        game_session = get_session(session_id)
        if not game_session:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束', 'error')
            return redirect(url_for('index'))

        # 获取要添加的玩家名字列表
        player_names = request.form.getlist('player_names')
        
        if not player_names:
            flash('请选择要添加的玩家', 'error')
            return redirect(url_for('game', session_id=session_id))

        added_players = []
        existing_players = []
        failed_players = []

        for player_name in player_names:
            if not player_name or not player_name.strip():
                continue
                
            player_name = player_name.strip()
            
            # 检查玩家是否已在场次中
            if player_name in game_session.get('players', set()):
                existing_players.append(player_name)
                continue

            try:
                # 获取或创建玩家
                player_id = get_or_create_player(player_name)

                # 添加玩家到场次
                success = add_player_to_session(session_id, player_id)
                if success:
                    added_players.append(player_name)
                else:
                    failed_players.append(player_name)
            except Exception as e:
                print(f"添加玩家 {player_name} 时出错: {e}")
                failed_players.append(player_name)

        # 保存数据（数据库自动保存）
        if added_players:
            save_data()

        # 生成反馈消息
        messages = []
        if added_players:
            if len(added_players) == 1:
                messages.append(f'成功添加玩家：{added_players[0]}')
            else:
                messages.append(f'成功添加 {len(added_players)} 个玩家：{", ".join(added_players)}')
            
        if existing_players:
            if len(existing_players) == 1:
                messages.append(f'玩家 {existing_players[0]} 已在场次中')
            else:
                messages.append(f'{len(existing_players)} 个玩家已在场次中：{", ".join(existing_players)}')
                
        if failed_players:
            if len(failed_players) == 1:
                messages.append(f'添加玩家 {failed_players[0]} 失败')
            else:
                messages.append(f'{len(failed_players)} 个玩家添加失败：{", ".join(failed_players)}')

        # 根据结果类型显示消息
        if added_players and not existing_players and not failed_players:
            # 全部成功
            flash(messages[0], 'success')
        elif added_players:
            # 部分成功
            flash('，'.join(messages), 'success')
        elif existing_players and not failed_players:
            # 全部已存在
            flash('，'.join(messages), 'error')
        else:
            # 有失败的情况
            flash('，'.join(messages), 'error')

        return redirect(url_for('game', session_id=session_id))

    @app.route('/add_score/<session_id>', methods=['POST'])
    def add_score(session_id):
        # 记分功能
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        game_session = get_session(session_id)
        if not game_session:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束', 'error')
            return redirect(url_for('index'))

        winner = request.form['winner']
        loser = request.form['loser']
        score = int(request.form['score'])

        # 验证
        if winner == loser:
            flash('胜者和败者不能是同一个玩家', 'error')
        elif winner not in game_session.get('players', set()) or loser not in game_session.get('players', set()):
            flash('选择的玩家不在当前场次中', 'error')
        else:
            # 获取玩家ID
            winner_id = get_player_by_name(winner)
            loser_id = get_player_by_name(loser)

            # 添加计分记录（数据库会自动更新分数）
            add_game_record(session_id, winner_id, loser_id, score)

            # 保存数据（数据库自动保存）
            save_data()
            flash('成功记录分数', 'success')

        return redirect(url_for('game', session_id=session_id))

    @app.route('/add_special_score/<session_id>', methods=['POST'])
    def add_special_score(session_id):
        # 处理特殊分数（14分和20分）的记分功能
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        game_session = get_session(session_id)
        if not game_session:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

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
        game_players = game_session.get('players', set())
        for player in all_players:
            if player not in game_players:
                flash(f'玩家 {player} 不在当前场次中', 'error')
                return redirect(url_for('game', session_id=session_id))

        # 获取玩家ID
        winner_id = get_player_by_name(winner)
        loser_ids = [get_player_by_name(loser) for loser in losers]

        # 使用统一的计分记录方法（支持多败者）
        add_game_record(session_id, winner_id, loser_ids[0], total_score, None, loser_ids[1])

        # 保存数据（数据库自动保存）
        save_data()
        flash(f'成功记录特殊分数：{winner} 胜 {losers[0]}+{losers[1]} ({total_score}分)', 'success')

        return redirect(url_for('game', session_id=session_id))

    @app.route('/delete_record/<session_id>/<int:record_index>', methods=['POST'])
    @require_admin_auth
    @require_csrf_protection
    def delete_record(session_id, record_index):
        # 删除计分记录
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        game_session = get_session(session_id)
        if not game_session:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束，无法删除记录', 'error')
            return redirect(url_for('index'))

        # 获取记录列表并验证索引
        records = game_session.get('records', [])
        if record_index < 0 or record_index >= len(records):
            flash('无效的记录索引', 'error')
            return redirect(url_for('game', session_id=session_id))

        # 删除记录（通过record_id而不是索引）
        record_to_delete = records[record_index]
        record_id = record_to_delete.get('record_id')
        
        if record_id:
            deleted_record = delete_game_record(record_id)
            if deleted_record:
                # 保存数据（数据库自动保存）
                save_data()
                
                winner_name = get_player_name(deleted_record['winner_id'])
                loser_name = get_player_name(deleted_record['loser_id'])
                flash(f'已删除记录：{winner_name} 胜 {loser_name} ({deleted_record["score"]}分)', 'success')
            else:
                flash('删除记录失败', 'error')
        else:
            flash('无法删除该记录', 'error')

        return redirect(url_for('game', session_id=session_id))

    @app.route('/end_session/<session_id>')
    def end_session_get(session_id):
        # 结束当前场次（GET方式，兼容性保留）
        return end_session_post(session_id)

    @app.route('/end_session/<session_id>', methods=['POST'])
    @require_admin_auth
    @require_csrf_protection
    def end_session_post(session_id):
        # 结束当前场次
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        # 结束场次
        success = end_session(session_id)
        
        if success:
            # 保存数据（数据库自动保存）
            save_data()
            flash('本场比赛已结束', 'success')
        else:
            flash('结束场次失败', 'error')

        return redirect(url_for('history'))

    @app.route('/create_and_select_player/<session_id>', methods=['POST'])
    def create_and_select_player(session_id):
        # 创建新玩家但不直接添加到场次，而是刷新页面让用户选择
        if session_id not in sessions:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        game_session = get_session(session_id)
        if not game_session:
            flash('场次不存在', 'error')
            return redirect(url_for('index'))

        # 检查场次是否已被结束
        if not game_session.get('active', True):
            flash('该场次已经结束', 'error')
            return redirect(url_for('index'))

        new_player_name = request.form['new_player_name'].strip()
        if not new_player_name:
            flash('玩家名称不能为空', 'error')
            return redirect(url_for('game', session_id=session_id))

        # 检查玩家是否已存在（按名字）
        existing_player_id = get_player_by_name(new_player_name)
        if existing_player_id:
            flash(f'玩家 "{new_player_name}" 已存在，请直接选择', 'success')
            return redirect(url_for('game', session_id=session_id))

        # 创建新玩家
        player_id = create_player(new_player_name)

        # 保存数据（数据库自动保存）
        save_data()

        flash(f'玩家 "{new_player_name}" 创建成功，请在快速添加区域选择', 'success')
        return redirect(url_for('game', session_id=session_id))
