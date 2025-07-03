"""
玩家相关路由模块 - 玩家详情、重命名等
"""
from collections import defaultdict
from flask import render_template, request, redirect, url_for, flash
from .models import (sessions, players, save_data, 
                     get_player_by_name, get_player_name, get_or_create_player, 
                     update_player_name, get_player_by_id, get_player_records,
                     get_player_stats)
from .security import require_admin_auth, require_csrf_protection
from . import APP_VERSION


def register_player_routes(app):
    """注册玩家相关路由"""
    
    @app.route('/player/<player_id>')
    def player_detail(player_id):
        """玩家详情页面"""
        if player_id not in players:
            flash('玩家不存在', 'error')
            return redirect(url_for('index'))

        player = get_player_by_id(player_id)
        if not player:
            flash('玩家不存在', 'error')
            return redirect(url_for('index'))

        # 获取玩家的所有对战记录
        player_records = get_player_records(player_id)

        # 将记录分为1分记录和非1分记录
        one_point_records = [r for r in player_records if r['score'] == 1]
        non_one_point_records = [r for r in player_records if r['score'] != 1]
        
        # 获取统计数据（包含所有记录）
        stats = get_player_stats(player_id)
        
        # 计算不包含1分记录的胜负统计
        competitive_wins = len([r for r in non_one_point_records if r['is_winner']])
        competitive_losses = len([r for r in non_one_point_records if not r['is_winner']])
        competitive_games = len(non_one_point_records)
        
        # 更新统计数据
        stats['competitive_wins'] = competitive_wins
        stats['competitive_losses'] = competitive_losses  
        stats['competitive_games'] = competitive_games
        stats['one_point_given'] = len([r for r in one_point_records if not r['is_winner']])  # 送出1分次数
        stats['one_point_received'] = len([r for r in one_point_records if r['is_winner']])    # 收到1分次数
        stats['one_point_profit'] = stats['one_point_received'] - stats['one_point_given']  # 1分收益（收到-送出）
        stats['competitive_win_rate'] = (competitive_wins / competitive_games * 100) if competitive_games > 0 else 0

        # 对手统计（胜负统计排除1分记录，但总分差包含所有记录）
        opponent_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total_score': 0})
        
        # 计算胜负统计（排除1分记录）
        for record in non_one_point_records:
            opponent_id = record['opponent_id']
            # 处理多个对手的情况
            if isinstance(opponent_id, list):
                # 如果是多个对手，为每个对手单独统计（但分数要分摊）
                for single_opponent_id in opponent_id:
                    if single_opponent_id:
                        if record['is_winner']:
                            opponent_stats[single_opponent_id]['wins'] += 1
                        else:
                            opponent_stats[single_opponent_id]['losses'] += 1
            else:
                # 单个对手的情况
                if opponent_id:
                    if record['is_winner']:
                        opponent_stats[opponent_id]['wins'] += 1
                    else:
                        opponent_stats[opponent_id]['losses'] += 1
        
        # 计算总分差（包含所有记录，包括1分记录）
        for record in player_records:
            opponent_id = record['opponent_id']
            # 处理多个对手的情况
            if isinstance(opponent_id, list):
                # 如果是多个对手，分数要分摊（使用整数除法）
                score_per_opponent = record['score'] // len(opponent_id)
                for single_opponent_id in opponent_id:
                    if single_opponent_id:
                        if record['is_winner']:
                            opponent_stats[single_opponent_id]['total_score'] += score_per_opponent
                        else:
                            opponent_stats[single_opponent_id]['total_score'] -= score_per_opponent
            else:
                # 单个对手的情况
                if opponent_id:
                    if record['is_winner']:
                        opponent_stats[opponent_id]['total_score'] += record['score']
                    else:
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

        # 准备分数趋势图表数据
        score_trend_data = []
        cumulative_score = 0
        
        # 按时间排序所有记录（最早的在前）
        sorted_records = sorted(player_records, key=lambda x: x['timestamp'])
        
        for i, record in enumerate(sorted_records):
            if record['is_winner']:
                cumulative_score += record['score']
            else:
                cumulative_score -= record['score']
            
            score_trend_data.append({
                'game_index': i + 1,  # 第几场比赛
                'score': cumulative_score,
                'timestamp': record['timestamp'],
                'opponent_name': record['opponent_name'],
                'session_name': record['session_name'],
                'record_score': record['score'],
                'is_winner': record['is_winner']
            })

        return render_template(
            'player_detail.html',
            player=player,
            player_id=player_id,
            stats=stats,
            records=player_records[:50],  # 只显示最近50场
            opponents=opponent_list,
            score_trend_data=score_trend_data,
            app_version=APP_VERSION
        )

    @app.route('/player/<player_id>/rename', methods=['POST'])
    @require_admin_auth
    @require_csrf_protection
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

        old_name = get_player_name(player_id)

        # 更新玩家名字
        success = update_player_name(player_id, new_name)
        
        if success:
            # 保存数据（数据库自动保存）
            save_data()
            flash(f'玩家名字已从 "{old_name}" 更改为 "{new_name}"', 'success')
        else:
            flash('更新玩家名字失败', 'error')

        return redirect(url_for('player_detail', player_id=player_id))
