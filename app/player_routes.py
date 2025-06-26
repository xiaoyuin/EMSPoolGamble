"""
玩家相关路由模块 - 玩家详情、重命名等
"""
from collections import defaultdict
from flask import render_template, request, redirect, url_for, flash
from .models import (sessions, players, save_data, 
                     get_player_by_name, get_player_name, get_or_create_player, update_player_name)
from . import APP_VERSION


def register_player_routes(app):
    """注册玩家相关路由"""
    
    @app.route('/player/<player_id>')
    def player_detail(player_id):
        """玩家详情页面"""
        if player_id not in players:
            flash('玩家不存在', 'error')
            return redirect(url_for('index'))

        player = players[player_id]

        # 收集这个玩家的所有对战记录
        player_records = []
        for session_id, session_data in sessions.items():
            for record in session_data.get('records', []):
                if (record.get('winner_id') == player_id or record.get('loser_id') == player_id or
                    record.get('winner') == player['name'] or record.get('loser') == player['name']):

                    # 确保记录有player_id信息
                    if 'winner_id' not in record and 'winner' in record:
                        record['winner_id'] = get_or_create_player(record['winner'])
                    if 'loser_id' not in record and 'loser' in record:
                        record['loser_id'] = get_or_create_player(record['loser'])

                    player_records.append({
                        'session_name': session_data.get('name', '未命名场次'),
                        'session_id': session_id,
                        'record': record,
                        'is_winner': (record.get('winner_id') == player_id or record.get('winner') == player['name']),
                        'opponent_id': record.get('loser_id') if (record.get('winner_id') == player_id or record.get('winner') == player['name']) else record.get('winner_id'),
                        'opponent_name': get_player_name(record.get('loser_id')) if (record.get('winner_id') == player_id or record.get('winner') == player['name']) else get_player_name(record.get('winner_id')),
                        'score': record.get('score', 0)
                    })

        # 按时间排序（最新的在前面）
        player_records.sort(key=lambda x: x['record'].get('timestamp', ''), reverse=True)

        # 计算统计数据（排除1分记录）
        # 将记录分为1分记录和非1分记录
        one_point_records = [r for r in player_records if r['score'] == 1]
        non_one_point_records = [r for r in player_records if r['score'] != 1]
        
        stats = {
            'total_games': len(player_records),
            'competitive_games': len(non_one_point_records),  # 不包含1分的对局数
            'wins': len([r for r in non_one_point_records if r['is_winner']]),
            'losses': len([r for r in non_one_point_records if not r['is_winner']]),
            'total_score': sum(r['score'] if r['is_winner'] else -r['score'] for r in player_records),
            'one_point_given': len([r for r in one_point_records if not r['is_winner']]),  # 送出1分次数
            'one_point_received': len([r for r in one_point_records if r['is_winner']])    # 收到1分次数
        }
        stats['win_rate'] = (stats['wins'] / stats['competitive_games'] * 100) if stats['competitive_games'] > 0 else 0

        # 对手统计（排除1分记录）
        opponent_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total_score': 0})
        for record in non_one_point_records:
            opponent_id = record['opponent_id']
            if opponent_id:
                if record['is_winner']:
                    opponent_stats[opponent_id]['wins'] += 1
                    opponent_stats[opponent_id]['total_score'] += record['score']
                else:
                    opponent_stats[opponent_id]['losses'] += 1
                    opponent_stats[opponent_id]['total_score'] -= record['score']

        # 转换对手统计为列表，包含名字
        opponent_list = []
        for opponent_id, stat in opponent_stats.items():
            opponent_list.append({
                'id': opponent_id,
                'name': get_player_name(opponent_id),
                'wins': stat['wins'],
                'losses': stat['losses'],
                'total_games': stat['wins'] + stat['losses'],
                'win_rate': (stat['wins'] / (stat['wins'] + stat['losses']) * 100) if (stat['wins'] + stat['losses']) > 0 else 0,
                'total_score': stat['total_score']
            })

        # 按总对局数排序
        opponent_list.sort(key=lambda x: x['total_games'], reverse=True)

        return render_template(
            'player_detail.html',
            player=player,
            player_id=player_id,
            stats=stats,
            records=player_records[:50],  # 只显示最近50场
            opponents=opponent_list,
            app_version=APP_VERSION
        )

    @app.route('/player/<player_id>/rename', methods=['POST'])
    def rename_player(player_id):
        """重命名玩家"""
        if player_id not in players:
            flash('玩家不存在', 'error')
            return redirect(url_for('index'))

        new_name = request.form.get('new_name', '').strip()
        if not new_name:
            flash('新名字不能为空', 'error')
            return redirect(url_for('player_detail', player_id=player_id))

        # 检查新名字是否已被其他玩家使用
        existing_player_id = get_player_by_name(new_name)
        if existing_player_id and existing_player_id != player_id:
            flash('该名字已被其他玩家使用', 'error')
            return redirect(url_for('player_detail', player_id=player_id))

        old_name = players[player_id]['name']

        # 更新玩家名字
        update_player_name(player_id, new_name)

        # 更新所有场次中的玩家名字（为了兼容性）
        for session_data in sessions.values():
            if old_name in session_data.get('players', set()):
                session_data['players'].remove(old_name)
                session_data['players'].add(new_name)
                # 更新分数记录
                if old_name in session_data.get('scores', {}):
                    session_data['scores'][new_name] = session_data['scores'][old_name]
                    del session_data['scores'][old_name]

            # 更新记录中的名字（为了显示）
            for record in session_data.get('records', []):
                if record.get('winner') == old_name:
                    record['winner'] = new_name
                if record.get('loser') == old_name:
                    record['loser'] = new_name

        # 保存数据
        save_data()

        flash(f'玩家名字已从 "{old_name}" 更改为 "{new_name}"', 'success')
        return redirect(url_for('player_detail', player_id=player_id))
