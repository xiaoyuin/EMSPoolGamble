"""
玩家相关路由模块 - 玩家详情、重命名等
"""
import datetime
import calendar
from collections import defaultdict
from flask import render_template, request, redirect, url_for, flash
from .models import (sessions, players, save_data,
                     get_player_by_name, get_player_name, get_or_create_player,
                     update_player_name, get_player_by_id, get_player_records,
                     get_player_stats, get_player_special_wins, get_players_special_wins_batch,
                     get_available_months_for_player)
from .security import require_admin_auth, require_csrf_protection
from . import APP_VERSION


def _resolve_player_date_range(selected_month, custom_start_date, custom_end_date):
    """根据筛选参数返回 (start_date, end_date) 字符串元组，用于 DB 查询。
    返回 (None, None) 表示不限时段。"""
    if not selected_month or selected_month == 'all':
        return None, None

    if selected_month == 'custom':
        if not (custom_start_date and custom_end_date):
            return None, None
        try:
            start_dt = datetime.datetime.fromisoformat(custom_start_date.replace('T', ' '))
            end_dt = datetime.datetime.fromisoformat(custom_end_date.replace('T', ' '))
            return (start_dt.strftime('%Y-%m-%d %H:%M:%S'),
                    end_dt.strftime('%Y-%m-%d %H:%M:%S'))
        except ValueError:
            return None, None

    # 月份格式 YYYY-MM
    try:
        year, month = map(int, selected_month.split('-'))
    except ValueError:
        return None, None
    last_day = calendar.monthrange(year, month)[1]
    return (f"{selected_month}-01 00:00:00",
            f"{selected_month}-{last_day:02d} 23:59:59")


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

        # 时间范围筛选参数（与 /history 协议一致）
        # 默认全时段（month=all），用户可切月份/自定义
        selected_month = request.args.get('month', '').strip() or 'all'
        custom_start_date = request.args.get('start_date', '').strip()
        custom_end_date = request.args.get('end_date', '').strip()

        # 该玩家有对战的月份列表（用于下拉选项）
        available_months = get_available_months_for_player(player_id)

        # 全时段该玩家参与的不同场次数
        # available_months 已按月聚合 distinct session_id，每个 session 只属于一个月，
        # 求和即为全时段不重复场次数。
        all_sessions_total = sum(m['count'] for m in available_months)

        # 用于自定义日期选择器的默认值
        default_start_date = ''
        default_end_date = datetime.date.today().strftime('%Y-%m-%d')
        if available_months:
            # 最早一个月份的第一天作为默认起点
            earliest_month = available_months[-1]['key']
            default_start_date = f"{earliest_month}-01"

        # 自定义日期选择器回填（input type="date" 只要 YYYY-MM-DD）
        display_start_date = ''
        display_end_date = ''
        if custom_start_date:
            display_start_date = custom_start_date.split('T')[0] if 'T' in custom_start_date else custom_start_date[:10]
        if custom_end_date:
            display_end_date = custom_end_date.split('T')[0] if 'T' in custom_end_date else custom_end_date[:10]

        # 解析时间范围
        start_date, end_date = _resolve_player_date_range(
            selected_month, custom_start_date, custom_end_date)

        # 获取（已按时间筛选的）玩家所有对战记录
        player_records = get_player_records(player_id, start_date, end_date)

        # 顶部姓名高亮使用全时段身份徽章（小金/大金光环）
        special_wins = get_player_special_wins(player_id)

        # 在筛选区间内统计特殊胜利次数
        special_wins_counts = {
            'small_gold_count': 0,
            'big_gold_count': 0
        }
        for record in player_records:
            if record['is_winner'] and record.get('special_score'):
                if record['special_score'] == '小金':
                    special_wins_counts['small_gold_count'] += 1
                elif record['special_score'] == '大金':
                    special_wins_counts['big_gold_count'] += 1

        # 将记录分为1分记录和非1分记录
        one_point_records = [r for r in player_records if r['score'] == 1]
        non_one_point_records = [r for r in player_records if r['score'] != 1]

        # 在筛选区间内重新计算 stats（不再调用 get_player_stats，确保时间范围生效）
        wins = sum(1 for r in player_records if r['is_winner'])
        losses = sum(1 for r in player_records if not r['is_winner'])
        total_score = 0
        for r in player_records:
            if r['is_winner']:
                total_score += r['score']
            else:
                total_score -= r['score']
        stats = {
            'total_games': len(player_records),
            'wins': wins,
            'losses': losses,
            'total_score': total_score,
        }

        # 计算不包含1分记录的胜负统计
        competitive_wins = len([r for r in non_one_point_records if r['is_winner']])
        competitive_losses = len([r for r in non_one_point_records if not r['is_winner']])
        competitive_games = len(non_one_point_records)

        stats['competitive_wins'] = competitive_wins
        stats['competitive_losses'] = competitive_losses
        stats['competitive_games'] = competitive_games
        stats['one_point_given'] = len([r for r in one_point_records if not r['is_winner']])
        stats['one_point_received'] = len([r for r in one_point_records if r['is_winner']])
        stats['one_point_profit'] = stats['one_point_received'] - stats['one_point_given']
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
        opponent_ids = []  # 收集所有对手ID
        for opponent_id, stat in opponent_stats.items():
            opponent_ids.append(opponent_id)
            opponent_list.append({
                'id': opponent_id,
                'name': get_player_name(opponent_id),
                'wins': stat['wins'],
                'losses': stat['losses'],
                'total_games': stat['wins'] + stat['losses'],
                'win_rate': (stat['wins'] / (stat['wins'] + stat['losses']) * 100) if (stat['wins'] + stat['losses']) > 0 else 0,
                'total_score': stat['total_score']
            })

        # 获取所有对手的特殊胜利记录
        if opponent_ids:
            opponents_special_wins = get_players_special_wins_batch(opponent_ids)
            # 将特殊胜利记录添加到对手信息中
            for opponent in opponent_list:
                if opponent['id'] in opponents_special_wins:
                    opponent.update(opponents_special_wins[opponent['id']])
                else:
                    opponent.update({'has_small_gold': False, 'has_big_gold': False})

        # 按总对局数排序
        opponent_list.sort(key=lambda x: x['total_games'], reverse=True)

        # 准备分数趋势图表数据（基于筛选后的记录，从筛选区间内的 0 开始累计）
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
            special_wins=special_wins,  # 传递特殊胜利记录（全时段身份徽章）
            special_wins_counts=special_wins_counts,  # 筛选区间内的特殊胜利次数
            available_months=available_months,
            selected_month=selected_month,
            custom_start_date=custom_start_date,
            custom_end_date=custom_end_date,
            display_start_date=display_start_date,
            display_end_date=display_end_date,
            default_start_date=default_start_date,
            default_end_date=default_end_date,
            all_sessions_total=all_sessions_total,
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
