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
from .models import players, get_player_by_id
from .database import db
from .tournament import (
    create_tournament, list_tournaments, get_tournament,
    delete_tournament,
    add_participant, remove_participant, set_participant_seed,
    generate_bracket, get_bracket,
    RESOURCE_BYE, _next_power_of_2,
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
        bracket = get_bracket(tournament_id) if tournament['status'] in (STATUS_IN_PROGRESS, STATUS_COMPLETED) else []
        return render_template(
            'tournament_detail.html',
            tournament=tournament,
            bracket=bracket,
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

    # ---------- 报名管理（管理员） ----------
    @app.route('/tournament/<tournament_id>/registration', methods=['GET'])
    @require_admin_auth
    def tournament_registration(tournament_id):
        tournament = get_tournament(tournament_id)
        if not tournament:
            flash('赛事不存在', 'error')
            return redirect(url_for('tournament_index'))
        if tournament['status'] not in (STATUS_DRAFT, STATUS_REGISTRATION):
            flash('赛事已生成对阵，无法再修改报名', 'error')
            return redirect(url_for('tournament_detail', tournament_id=tournament_id))

        # 全部 player（按名字排）
        all_players = db.get_all_players()
        registered_ids = {p['player_id'] for p in tournament['participants']}
        available_players = [p for p in all_players if p['player_id'] not in registered_ids]
        available_players.sort(key=lambda p: p['name'])

        # 给"对阵编辑器"算 bracket_size（next pow2，最小 4）
        n = len(tournament['participants'])
        bracket_size = max(4, _next_power_of_2(n)) if n >= 2 else 0
        n_byes = bracket_size - n if bracket_size else 0

        return render_template(
            'tournament_registration.html',
            tournament=tournament,
            available_players=available_players,
            bracket_size=bracket_size,
            n_byes=n_byes,
            app_version=APP_VERSION,
        )

    @app.route('/tournament/<tournament_id>/registration/add', methods=['POST'])
    @require_admin_auth
    @require_csrf_protection
    def tournament_register_add(tournament_id):
        tournament = get_tournament(tournament_id)
        if not tournament:
            flash('赛事不存在', 'error')
            return redirect(url_for('tournament_index'))
        if tournament['status'] not in (STATUS_DRAFT, STATUS_REGISTRATION):
            flash('赛事已生成对阵，无法再修改报名', 'error')
            return redirect(url_for('tournament_detail', tournament_id=tournament_id))

        player_ids = request.form.getlist('player_ids')
        added = 0
        for pid in player_ids:
            if get_player_by_id(pid) and add_participant(tournament_id, pid, None):
                added += 1
        if added:
            flash(f'成功添加 {added} 名参赛者', 'success')
        else:
            flash('未添加任何参赛者', 'error')
        return redirect(url_for('tournament_registration', tournament_id=tournament_id))

    @app.route('/tournament/<tournament_id>/registration/remove', methods=['POST'])
    @require_admin_auth
    @require_csrf_protection
    def tournament_register_remove(tournament_id):
        tournament = get_tournament(tournament_id)
        if not tournament:
            flash('赛事不存在', 'error')
            return redirect(url_for('tournament_index'))
        if tournament['status'] not in (STATUS_DRAFT, STATUS_REGISTRATION):
            flash('赛事已生成对阵，无法再修改报名', 'error')
            return redirect(url_for('tournament_detail', tournament_id=tournament_id))

        player_id = request.form.get('player_id', '').strip()
        if not player_id:
            flash('参数错误', 'error')
            return redirect(url_for('tournament_registration', tournament_id=tournament_id))
        if remove_participant(tournament_id, player_id):
            flash('已移除参赛者', 'success')
        else:
            flash('移除失败', 'error')
        return redirect(url_for('tournament_registration', tournament_id=tournament_id))

    @app.route('/tournament/<tournament_id>/registration/set_seed', methods=['POST'])
    @require_admin_auth
    @require_csrf_protection
    def tournament_register_set_seed(tournament_id):
        tournament = get_tournament(tournament_id)
        if not tournament:
            flash('赛事不存在', 'error')
            return redirect(url_for('tournament_index'))
        if tournament['status'] not in (STATUS_DRAFT, STATUS_REGISTRATION):
            flash('赛事已生成对阵，无法再修改报名', 'error')
            return redirect(url_for('tournament_detail', tournament_id=tournament_id))

        # 表单里每个 participant 一个 seed_<player_id> 字段（空字符串 = 无种子）
        # 同时强制约束：1-4 号种子各最多 1 人
        new_seeds = {}
        seen_seeds = set()
        for p in tournament['participants']:
            pid = p['player_id']
            raw = request.form.get(f'seed_{pid}', '').strip()
            if raw == '':
                new_seeds[pid] = None
                continue
            try:
                seed = int(raw)
            except ValueError:
                flash(f'选手 "{p["player_name"]}" 的种子号无效', 'error')
                return redirect(url_for('tournament_registration', tournament_id=tournament_id))
            if seed < 1 or seed > 4:
                flash('种子号必须为 1-4 之间', 'error')
                return redirect(url_for('tournament_registration', tournament_id=tournament_id))
            if seed in seen_seeds:
                flash(f'种子号 {seed} 被指定给了多人', 'error')
                return redirect(url_for('tournament_registration', tournament_id=tournament_id))
            seen_seeds.add(seed)
            new_seeds[pid] = seed

        for pid, seed in new_seeds.items():
            set_participant_seed(tournament_id, pid, seed)
        flash('种子设置已保存', 'success')
        return redirect(url_for('tournament_registration', tournament_id=tournament_id))

    # ---------- 生成 bracket（管理员） ----------
    @app.route('/tournament/<tournament_id>/generate_bracket', methods=['POST'])
    @require_admin_auth
    @require_csrf_protection
    def tournament_generate_bracket(tournament_id):
        tournament = get_tournament(tournament_id)
        if not tournament:
            flash('赛事不存在', 'error')
            return redirect(url_for('tournament_index'))
        if tournament['status'] not in (STATUS_DRAFT, STATUS_REGISTRATION):
            flash('赛事已生成对阵', 'error')
            return redirect(url_for('tournament_detail', tournament_id=tournament_id))
        if len(tournament['participants']) < 2:
            flash('至少需要 2 名参赛者才能生成对阵', 'error')
            return redirect(url_for('tournament_registration', tournament_id=tournament_id))

        # 收集手动 slot 指定：每个 slot_<i> 字段值可以是
        #   '' / 'random'  → 留空（让算法随机抽）
        #   '__bye__'      → 该 slot 锁为 bye
        #   <player_id>    → 该 slot 锁为某参赛者
        bracket_size = max(4, _next_power_of_2(len(tournament['participants'])))
        manual_slots = {}
        for slot_1based in range(1, bracket_size + 1):
            raw = request.form.get(f'slot_{slot_1based}', '').strip()
            if raw == '' or raw == 'random':
                continue
            manual_slots[slot_1based] = raw  # 后端会校验是否合法

        ok = generate_bracket(tournament_id, manual_slots=manual_slots or None)
        if not ok:
            flash('生成对阵失败：参赛人数不足、轮数配置不够、或手动 slot 设置冲突', 'error')
            return redirect(url_for('tournament_registration', tournament_id=tournament_id))

        flash('对阵已生成', 'success')
        return redirect(url_for('tournament_detail', tournament_id=tournament_id))
