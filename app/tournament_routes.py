"""
Tournament 路由模块（v1.10）

公开页面（任何人）：
  GET  /tournament                       — 赛事列表 + 当前进行中的赛事入口
  GET  /tournament/<tid>                 — 赛事详情（参赛者、bracket、对阵）

管理员页面/动作（@require_admin_auth）：
  GET  /tournament/new                   — 创建赛事表单
  POST /tournament/new                   — 提交创建
  POST /tournament/<tid>/delete          — 删除赛事

#3 / #4 将在此基础上追加：
  GET/POST /tournament/<tid>/registration
  POST     /tournament/<tid>/generate_bracket
  POST     /tournament/<tid>/match/<mid>/record
  POST     /tournament/<tid>/match/<mid>/reset
"""

from flask import render_template, request, redirect, url_for, flash
from .security import require_admin_auth, require_csrf_protection
from . import APP_VERSION
from .tournament import (
    create_tournament, list_tournaments, get_tournament,
    delete_tournament,
    STATUS_DRAFT, STATUS_REGISTRATION, STATUS_IN_PROGRESS, STATUS_COMPLETED,
)


def register_tournament_routes(app):
    """注册赛事相关路由。"""

    # ---------- 列表（公开） ----------
    @app.route('/tournament')
    def tournament_index():
        tournaments = list_tournaments()
        return render_template(
            'tournament_index.html',
            tournaments=tournaments,
            app_version=APP_VERSION,
        )

    # ---------- 详情（公开） ----------
    @app.route('/tournament/<tournament_id>')
    def tournament_detail(tournament_id):
        tournament = get_tournament(tournament_id)
        if not tournament:
            flash('赛事不存在', 'error')
            return redirect(url_for('tournament_index'))
        return render_template(
            'tournament_detail.html',
            tournament=tournament,
            app_version=APP_VERSION,
        )

    # ---------- 创建赛事（管理员） ----------
    @app.route('/tournament/new', methods=['GET'])
    @require_admin_auth
    def tournament_new():
        # 默认提一个常见赛制建议（4 轮：1/8 → 1/4 → 半决赛 → 决赛）
        default_rounds = [
            {'name': '1/8 决赛', 'best_of': 5},
            {'name': '1/4 决赛', 'best_of': 7},
            {'name': '半决赛',   'best_of': 7},
            {'name': '决赛',     'best_of': 9},
        ]
        return render_template(
            'tournament_new.html',
            default_rounds=default_rounds,
            app_version=APP_VERSION,
        )

    @app.route('/tournament/new', methods=['POST'])
    @require_admin_auth
    @require_csrf_protection
    def tournament_create():
        name = request.form.get('name', '').strip()
        if not name:
            flash('赛事名称不能为空', 'error')
            return redirect(url_for('tournament_new'))

        # 表单形式：round_name_1, best_of_1, round_name_2, best_of_2 ...
        rounds = []
        for idx in range(1, 11):  # 最多支持 10 轮（10 轮 = 1024 人，远超实际需求）
            round_name = request.form.get(f'round_name_{idx}', '').strip()
            best_of_raw = request.form.get(f'best_of_{idx}', '').strip()
            if not round_name and not best_of_raw:
                continue
            if not round_name:
                flash(f'第 {idx} 轮名称不能为空', 'error')
                return redirect(url_for('tournament_new'))
            try:
                best_of = int(best_of_raw)
            except ValueError:
                flash(f'第 {idx} 轮 best-of 必须是整数', 'error')
                return redirect(url_for('tournament_new'))
            if best_of % 2 == 0 or best_of < 1:
                flash(f'第 {idx} 轮 best-of 必须是 ≥1 的奇数（如 5/7/9）', 'error')
                return redirect(url_for('tournament_new'))
            rounds.append({'name': round_name, 'best_of': best_of})

        if len(rounds) < 1:
            flash('至少需要 1 轮配置', 'error')
            return redirect(url_for('tournament_new'))

        tournament_id = create_tournament(name, rounds)
        flash(f'赛事 "{name}" 已创建，可以开始报名', 'success')
        return redirect(url_for('tournament_detail', tournament_id=tournament_id))

    # ---------- 删除赛事（管理员） ----------
    @app.route('/tournament/<tournament_id>/delete', methods=['POST'])
    @require_admin_auth
    @require_csrf_protection
    def tournament_delete(tournament_id):
        tournament = get_tournament(tournament_id)
        if not tournament:
            flash('赛事不存在', 'error')
            return redirect(url_for('tournament_index'))
        delete_tournament(tournament_id)
        flash(f'赛事 "{tournament["name"]}" 已删除', 'success')
        return redirect(url_for('tournament_index'))
