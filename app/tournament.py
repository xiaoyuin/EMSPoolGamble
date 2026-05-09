"""
Tournament 模块 - 杯赛系统（v1.10）

与现有计分系统隔离的 best-of-N 单淘汰赛容器：
- DAO 层：tournament / round / participant / match / match_game 五张表
- 业务逻辑：种子布置、bye 对称分布、bracket 生成、晋级、撤销

设计原则：
- player_id 是跨系统主键，杯赛通过 participants 引用 players 表
- 数据上完全独立，与 sessions / game_records 不共享
- 玩家详情页可拉取该 player 的所有 tournament 记录展示战绩

公开函数（供 routes 调用）通过 models.py 风格的薄 wrapper 暴露。
"""

import uuid
import math
import random
from typing import List, Dict, Optional, Tuple

from .database import db
from .utils import get_utc_timestamp


# ===== 状态枚举 =====
STATUS_DRAFT = 'draft'                 # 刚创建，未开放报名
STATUS_REGISTRATION = 'registration'   # 报名中（未生成 bracket）
STATUS_IN_PROGRESS = 'in_progress'     # 已生成 bracket，比赛进行中
STATUS_COMPLETED = 'completed'         # 完成

VALID_STATUSES = {STATUS_DRAFT, STATUS_REGISTRATION, STATUS_IN_PROGRESS, STATUS_COMPLETED}

# 一个 best-of-N 的赢者需要先达到的局数
def games_needed_to_win(best_of: int) -> int:
    return (best_of // 2) + 1


# ===== 创建 / 查询 tournaments =====

def create_tournament(name: str, rounds_config: List[Dict]) -> str:
    """
    创建一个新赛事。
    rounds_config: 每轮的配置，按从早到晚顺序排列，例如
        [{'name': '1/8 决赛', 'best_of': 5},
         {'name': '1/4 决赛', 'best_of': 7},
         {'name': '半决赛',   'best_of': 7},
         {'name': '决赛',     'best_of': 9}]

    返回新建的 tournament_id。bracket_size 此时为 NULL，等到生成 bracket 时由
    报名人数决定（next power of 2，最小 4）。
    """
    tournament_id = str(uuid.uuid4())
    now = get_utc_timestamp()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tournaments (tournament_id, name, bracket_size, status, created_at, updated_at)
            VALUES (?, ?, NULL, ?, ?, ?)
        ''', (tournament_id, name, STATUS_REGISTRATION, now, now))

        for idx, r in enumerate(rounds_config, start=1):
            cursor.execute('''
                INSERT INTO tournament_rounds (tournament_id, round_index, round_name, best_of)
                VALUES (?, ?, ?, ?)
            ''', (tournament_id, idx, r['name'], r['best_of']))

        conn.commit()
    return tournament_id


def list_tournaments() -> List[Dict]:
    """按创建时间倒序列出所有赛事，附带参赛人数。"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.*, (
                SELECT COUNT(*) FROM tournament_participants tp WHERE tp.tournament_id = t.tournament_id
            ) AS participant_count
            FROM tournaments t
            ORDER BY t.created_at DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]


def get_tournament(tournament_id: str) -> Optional[Dict]:
    """获取赛事完整信息：基础字段 + 各轮配置 + 参赛者列表。"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tournaments WHERE tournament_id = ?', (tournament_id,))
        row = cursor.fetchone()
        if not row:
            return None
        tournament = dict(row)

        cursor.execute('''
            SELECT round_index, round_name, best_of
            FROM tournament_rounds
            WHERE tournament_id = ?
            ORDER BY round_index
        ''', (tournament_id,))
        tournament['rounds'] = [dict(r) for r in cursor.fetchall()]

        cursor.execute('''
            SELECT tp.player_id, tp.seed, p.name AS player_name
            FROM tournament_participants tp
            JOIN players p ON p.player_id = tp.player_id
            WHERE tp.tournament_id = ?
            ORDER BY
                CASE WHEN tp.seed IS NULL THEN 1 ELSE 0 END,
                tp.seed,
                p.name
        ''', (tournament_id,))
        tournament['participants'] = [dict(r) for r in cursor.fetchall()]

        return tournament


def update_tournament_status(tournament_id: str, status: str) -> bool:
    if status not in VALID_STATUSES:
        return False
    now = get_utc_timestamp()
    completed_at = now if status == STATUS_COMPLETED else None
    with db.get_connection() as conn:
        cursor = conn.cursor()
        if completed_at:
            cursor.execute('''
                UPDATE tournaments SET status = ?, updated_at = ?, completed_at = ?
                WHERE tournament_id = ?
            ''', (status, now, completed_at, tournament_id))
        else:
            cursor.execute('''
                UPDATE tournaments SET status = ?, updated_at = ?
                WHERE tournament_id = ?
            ''', (status, now, tournament_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_tournament(tournament_id: str) -> bool:
    """硬删除整个赛事（含所有 rounds / participants / matches / match_games）。"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        # SQLite 默认不开 ON DELETE CASCADE，手动级联删除
        cursor.execute('DELETE FROM tournament_match_games WHERE match_id IN '
                       '(SELECT match_id FROM tournament_matches WHERE tournament_id = ?)',
                       (tournament_id,))
        cursor.execute('DELETE FROM tournament_matches WHERE tournament_id = ?', (tournament_id,))
        cursor.execute('DELETE FROM tournament_participants WHERE tournament_id = ?', (tournament_id,))
        cursor.execute('DELETE FROM tournament_rounds WHERE tournament_id = ?', (tournament_id,))
        cursor.execute('DELETE FROM tournaments WHERE tournament_id = ?', (tournament_id,))
        conn.commit()
        return cursor.rowcount > 0


# ===== 参赛者管理（#3 用） =====

def add_participant(tournament_id: str, player_id: str, seed: Optional[int] = None) -> bool:
    """添加参赛者；如果已存在则返回 False。"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO tournament_participants (tournament_id, player_id, seed)
            VALUES (?, ?, ?)
        ''', (tournament_id, player_id, seed))
        conn.commit()
        return cursor.rowcount > 0


def remove_participant(tournament_id: str, player_id: str) -> bool:
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM tournament_participants
            WHERE tournament_id = ? AND player_id = ?
        ''', (tournament_id, player_id))
        conn.commit()
        return cursor.rowcount > 0


def set_participant_seed(tournament_id: str, player_id: str, seed: Optional[int]) -> bool:
    """设置或清除参赛者的种子号；seed 应为 1-4 或 None。"""
    if seed is not None and (not isinstance(seed, int) or seed < 1 or seed > 4):
        return False
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE tournament_participants SET seed = ?
            WHERE tournament_id = ? AND player_id = ?
        ''', (seed, tournament_id, player_id))
        conn.commit()
        return cursor.rowcount > 0


# ===== 玩家联动（#5 用） =====

def get_player_tournament_history(player_id: str) -> List[Dict]:
    """
    返回该玩家参加过的所有赛事 + 在每个赛事中的最终成绩。
    成绩定义：
    - winner_id == player_id 的最深一轮 → "X 强出局"
    - 一直晋级到决赛胜利 → "冠军"
    - 决赛输 → "亚军"
    - 报名了但还没生成 bracket → "已报名"
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.tournament_id, t.name, t.status, t.bracket_size,
                   t.created_at, t.completed_at, tp.seed
            FROM tournament_participants tp
            JOIN tournaments t ON t.tournament_id = tp.tournament_id
            WHERE tp.player_id = ?
            ORDER BY t.created_at DESC
        ''', (player_id,))
        results = []
        for row in cursor.fetchall():
            t = dict(row)
            placement = _compute_placement(t['tournament_id'], player_id, t['bracket_size'], t['status'])
            t['placement'] = placement
            results.append(t)
        return results


def _compute_placement(tournament_id: str, player_id: str,
                       bracket_size: Optional[int], status: str) -> str:
    """根据 matches 表推算选手在该赛事的最终名次描述。"""
    if status == STATUS_DRAFT or status == STATUS_REGISTRATION or not bracket_size:
        return '已报名'

    with db.get_connection() as conn:
        cursor = conn.cursor()
        # 拿到该选手所有有结果的 match
        cursor.execute('''
            SELECT round_index, winner_id, player1_id, player2_id
            FROM tournament_matches
            WHERE tournament_id = ?
              AND (player1_id = ? OR player2_id = ?)
              AND winner_id IS NOT NULL
            ORDER BY round_index DESC
        ''', (tournament_id, player_id, player_id))
        matches = cursor.fetchall()

        if not matches:
            return '未出场'

        # 总轮数
        total_rounds = int(math.log2(bracket_size))

        # 找最后一场（最深的一轮）
        last_match = matches[0]
        last_round = last_match['round_index']

        if last_match['winner_id'] == player_id and last_round == total_rounds:
            return '冠军'
        if last_match['winner_id'] != player_id and last_round == total_rounds:
            return '亚军'
        # 在第 last_round 轮被淘汰：剩下的对手数 = 2^(total_rounds - last_round + 1) → 多少强
        # 例如 8 人 bracket（3 轮），第 1 轮被淘汰 → 8 强；第 2 轮 → 4 强
        survived_to = 2 ** (total_rounds - last_round + 1)
        return f'{survived_to} 强'
