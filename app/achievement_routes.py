"""
成就系统路由模块 - 处理所有成就相关的路由
"""
from flask import render_template, request, redirect, url_for, flash
from .models import (get_achievement_players, get_achievement_records,
                     get_achievement_stats, get_achievement_master_players,
                     get_negative_achievement_players, get_negative_achievement_records,
                     get_best_buddy_stats, get_duo_loser_stats)
from . import APP_VERSION


def register_achievement_routes(app):
    """注册成就系统路由"""

    @app.route('/achievements')
    def achievements():
        """成就系统主页"""
        # 获取成就统计信息
        stats = get_achievement_stats()

        # 获取好兄弟数据（用于计数）
        buddy_stats = get_best_buddy_stats()

        # 准备成就列表数据
        achievements_data = [
            {
                'id': 'small_gold',
                'name': '小金玩家',
                'description': '获得过至少一次小金胜利的玩家',
                'icon': '🥉',
                'count': stats['small_gold_players'],
                'category': 'basic'
            },
            {
                'id': 'big_gold',
                'name': '大金玩家',
                'description': '获得过至少一次大金胜利的玩家',
                'icon': '🥇',
                'count': stats['big_gold_players'],
                'category': 'basic'
            },
            {
                'id': 'small_gold_master',
                'name': '小金达人',
                'description': '获得10次或以上小金胜利的玩家',
                'icon': '🏆',
                'count': stats['small_gold_masters'],
                'category': 'master'
            },
            {
                'id': 'big_gold_master',
                'name': '大金达人',
                'description': '获得5次或以上大金胜利的玩家',
                'icon': '👑',
                'count': stats['big_gold_masters'],
                'category': 'master'
            },
            {
                'id': 'big_gold_legend',
                'name': '大金传奇',
                'description': '获得10次或以上大金胜利的玩家',
                'icon': '🏛️',
                'count': stats['big_gold_legends'],
                'category': 'legend'
            },
            {
                'id': 'gold_loser',
                'name': '大吃一金',
                'description': '被大小金痛击过的玩家',
                'icon': '🙈',
                'count': stats['gold_loser_players'],
                'category': 'negative'
            },
            {
                'id': 'best_buddy',
                'name': '好兄弟',
                'description': '给谁送了最多1分？',
                'icon': '🤝',
                'count': None,
                'category': 'fun'
            },
            {
                'id': 'duo_loser',
                'name': '有难同当',
                'description': '一起被大金/双吃的组合',
                'icon': '🫂',
                'count': None,
                'category': 'fun'
            }
        ]

        return render_template('achievements/index.html',
                             achievements=achievements_data,
                             app_version=APP_VERSION)

    @app.route('/achievement/small_gold')
    def achievement_small_gold():
        """小金玩家成就详情"""
        # 获取小金玩家
        achievement_players = get_achievement_players('small_gold')

        # 获取小金记录（最近50条）
        achievement_records = get_achievement_records('small_gold')[:50]

        # 成就配置
        achievement_config = {
            'id': 'small_gold',
            'name': '小金玩家',
            'description': '获得过至少一次小金胜利的玩家。小金是台球游戏中的特殊得分方式，代表着精准的技术和运气的结合。',
            'icon': '🥉',
            'rule': '在任意场次中获得一次小金胜利',
            'difficulty': '入门',
            'color_theme': 'bronze'
        }

        return render_template('achievements/small_gold.html',
                             achievement=achievement_config,
                             achievement_players=achievement_players,
                             achievement_records=achievement_records,
                             app_version=APP_VERSION)

    @app.route('/achievement/big_gold')
    def achievement_big_gold():
        """大金玩家成就详情"""
        # 获取大金玩家
        achievement_players = get_achievement_players('big_gold')

        # 获取大金记录（最近50条）
        achievement_records = get_achievement_records('big_gold')[:50]

        # 成就配置
        achievement_config = {
            'id': 'big_gold',
            'name': '大金玩家',
            'description': '获得过至少一次大金胜利的玩家。大金是台球游戏中最高级别的得分方式，需要极高的技术水平和完美的时机把握。',
            'icon': '🥇',
            'rule': '在任意场次中获得一次大金胜利',
            'difficulty': '困难',
            'color_theme': 'gold'
        }

        return render_template('achievements/big_gold.html',
                             achievement=achievement_config,
                             achievement_players=achievement_players,
                             achievement_records=achievement_records,
                             app_version=APP_VERSION)

    @app.route('/achievement/small_gold_master')
    def achievement_small_gold_master():
        """小金达人成就详情"""
        # 获取小金达人玩家
        achievement_players = get_achievement_master_players('small_gold_master')

        # 获取小金记录（用于展示总记录）
        all_small_gold_records = get_achievement_records('small_gold')

        # 成就配置
        achievement_config = {
            'id': 'small_gold_master',
            'name': '小金达人',
            'description': '获得10次或以上小金胜利的玩家。这代表着对小金技巧的深度掌握和持续的优秀表现。',
            'icon': '🏆',
            'rule': '累计获得10次或以上小金胜利',
            'difficulty': '专家',
            'color_theme': 'trophy',
            'requirement_count': 10
        }

        return render_template('achievements/small_gold_master.html',
                             achievement=achievement_config,
                             achievement_players=achievement_players,
                             all_records=all_small_gold_records,
                             app_version=APP_VERSION)

    @app.route('/achievement/big_gold_master')
    def achievement_big_gold_master():
        """大金达人成就详情"""
        # 获取大金达人玩家
        achievement_players = get_achievement_master_players('big_gold_master')

        # 获取大金记录（用于展示总记录）
        all_big_gold_records = get_achievement_records('big_gold')

        # 成就配置
        achievement_config = {
            'id': 'big_gold_master',
            'name': '大金达人',
            'description': '获得5次或以上大金胜利的玩家。这是台球游戏中的最高荣誉，代表着绝对的技术统治力。',
            'icon': '👑',
            'rule': '累计获得5次或以上大金胜利',
            'difficulty': '传奇',
            'color_theme': 'crown',
            'requirement_count': 5
        }

        return render_template('achievements/big_gold_master.html',
                             achievement=achievement_config,
                             achievement_players=achievement_players,
                             all_records=all_big_gold_records,
                             app_version=APP_VERSION)

    @app.route('/achievement/big_gold_legend')
    def achievement_big_gold_legend():
        """大金传奇成就详情"""
        # 获取大金传奇玩家
        achievement_players = get_achievement_master_players('big_gold_legend')

        # 获取大金记录（用于展示总记录）
        all_big_gold_records = get_achievement_records('big_gold')

        # 成就配置
        achievement_config = {
            'id': 'big_gold_legend',
            'name': '大金传奇',
            'description': '获得10次或以上大金胜利的玩家。真正的台球传奇，技术和经验的完美结合。',
            'icon': '🏛️',
            'rule': '累计获得10次或以上大金胜利',
            'color_theme': 'legend',
            'requirement_count': 10
        }

        return render_template('achievements/big_gold_legend.html',
                             achievement=achievement_config,
                             achievement_players=achievement_players,
                             all_records=all_big_gold_records,
                             app_version=APP_VERSION)

    @app.route('/achievement/gold_loser')
    def achievement_gold_loser():
        """大吃一金负面成就详情"""
        # 获取大吃一金玩家
        achievement_players = get_negative_achievement_players('gold_loser')

        # 获取被大小金痛击的记录（最近50条）
        achievement_records = get_negative_achievement_records('gold_loser')[:50]

        # 成就配置
        achievement_config = {
            'id': 'gold_loser',
            'name': '大吃一金',
            'description': '被大小金痛击过的玩家。虽然失败，但这也是成长的一部分。',
            'icon': '🙈',
            'rule': '在任意场次中被大金或小金击败',
            'difficulty': '经历',
            'color_theme': 'negative'
        }

        return render_template('achievements/gold_loser.html',
                             achievement=achievement_config,
                             achievement_players=achievement_players,
                             achievement_records=achievement_records,
                             app_version=APP_VERSION)

    @app.route('/achievement/best_buddy')
    def achievement_best_buddy():
        """好兄弟详情页"""
        buddy_stats = get_best_buddy_stats()

        achievement_config = {
            'id': 'best_buddy',
            'name': '好兄弟',
            'description': '每个玩家给谁送了最多的1分？1分虽小，但日积月累，你的好兄弟是谁一目了然。',
            'icon': '🤝',
            'rule': '统计每位玩家赢得1分时，对手出现最多的人',
            'difficulty': '趣味统计',
            'color_theme': 'buddy'
        }

        return render_template('achievements/best_buddy.html',
                             achievement=achievement_config,
                             buddy_stats=buddy_stats,
                             app_version=APP_VERSION)

    @app.route('/achievement/duo_loser')
    def achievement_duo_loser():
        """有难同当详情页"""
        duo_stats = get_duo_loser_stats()

        achievement_config = {
            'id': 'duo_loser',
            'name': '有难同当',
            'description': '哪些组合最常一起被大金或双吃？同甘共苦的兄弟情。',
            'icon': '🫂',
            'rule': '统计在大金（20分）和双吃中，一起作为败者的玩家组合出现次数',
            'difficulty': '趣味统计',
            'color_theme': 'duo'
        }

        return render_template('achievements/duo_loser.html',
                             achievement=achievement_config,
                             duo_stats=duo_stats,
                             app_version=APP_VERSION)

    @app.route('/achievement/<achievement_id>')
    def achievement_fallback(achievement_id):
        """未定义成就的后备路由"""
        flash(f'成就 "{achievement_id}" 不存在或尚未实现', 'error')
        return redirect(url_for('achievements'))
