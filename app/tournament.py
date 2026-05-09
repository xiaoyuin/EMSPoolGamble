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
        [{'name': '16进8', 'best_of': 5},
         {'name': '8进4',  'best_of': 7},
         {'name': '半决赛', 'best_of': 7},
         {'name': '决赛',   'best_of': 9}]

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


# ===== Bracket 生成（#3） =====

# 标准 bracket 种子布置表（迭代生成，匹配 Wikipedia 标准）：
#   size=2:  [1, 2]
#   size=4:  [1, 4, 3, 2]    → R1: 1v4 + 3v2  → 决赛 (1or4) vs (3or2)
#   size=8:  [1, 8, 5, 4, 3, 6, 7, 2]
#                              R1: 1v8 5v4 3v6 7v2
#                              R2 半决赛: (1or8)v(5or4) + (3or6)v(7or2)
#                              决赛: 1的半区 vs 2的半区 ✓
#
# 算法：每次倍增时，把当前列表 prev 扩展为长度 2*size_prev：
#   对 prev 中每个位置 i 上的 seed s，新表中 [i*2] = s，
#   新表中 [i*2+1] = (2*size_prev + 1 - s)
# 但顺序上"内/外"要按 prev 中位置交替——所以更稳的写法是用反射：
#   new = []
#   for s in prev:
#       new.append(s)
#       new.append(new_size + 1 - s)
#   即与之前一样。但要让 size=4 得到 [1, 4, 3, 2] 而不是 [1, 4, 2, 3]，
#   prev = _seed_order(2) 必须是 [1, 2]，扩展时要让 seed 2 那位在外侧 → [3, 2]。
#   关键修正：扩展时根据 prev 中位置的"奇偶性"决定 (s, new+1-s) 还是 (new+1-s, s)。
#   位置 0 (偶) → (s, new+1-s)；位置 1 (奇) → (new+1-s, s)。
#   但更简单：总是 (s, new+1-s)，但让 prev 自己满足"每对内的小 seed 在前"。
#   _seed_order(2)=[1,2]：第二个元素是 2，需要变成 [3, 2]。
#   所以扩展规则改为：对 prev 中第 i 位的 s，
#     if i even: append s, append new+1-s
#     if i odd : append new+1-s, append s
def _seed_order(size: int) -> List[int]:
    """返回长度为 size 的列表 a，其中 a[i] 表示 slot (i+1) 应当装第几号种子（1-based）。"""
    if size == 1:
        return [1]
    prev = _seed_order(size // 2)
    out = []
    for i, s in enumerate(prev):
        a, b = s, size + 1 - s
        if i % 2 == 0:
            out.append(a)
            out.append(b)
        else:
            out.append(b)
            out.append(a)
    return out


def _next_power_of_2(n: int) -> int:
    if n <= 1:
        return 2
    return 1 << (n - 1).bit_length()


# slot 资源类型
RESOURCE_BYE = '__bye__'  # 表示该 slot 是 bye
# 其它情况下是 player_id 字符串


def _build_bracket_layout(participants: List[Dict],
                          bracket_size: int,
                          manual_slots: Optional[Dict[int, str]] = None
                          ) -> List[Optional[str]]:
    """
    根据参赛者、目标 bracket_size 和手动指定的 slot，生成首轮所有 slot 的布局。

    参数：
      participants: [{'player_id', 'seed': 1-4 或 None, 'player_name'}, ...]
      bracket_size: bracket 总 slot 数（2 的幂）
      manual_slots: dict[slot_index_1based] = player_id 或 RESOURCE_BYE
                    管理员手动指定的 slot 内容（最高优先级）。

    返回：
      slots: 长度 == bracket_size 的列表，每个元素是 player_id 或 None（None = bye 占位）

    算法（3 步）：
      Step 1: 应用 manual_slots —— 每个手动指定的 slot 直接锁定。验证：
              - 同一 player_id 不能出现在两个 slot
              - manual 的 player_id 必须是参赛者
      Step 2: 对剩下的种子玩家，按 _seed_order 找它们的标准 slot，
              如果该 slot 还没被手动占用，把种子放进去；
              否则该种子降级为"普通参赛者"（将随机分配）。
      Step 3: 剩下的 slot（未被任何人占用）由"剩余资源"随机填入：
              剩余资源 = 未被锁定的参赛者 + 还需要的 bye 数量
              其中 bye 数量 = (bracket_size - len(participants)) - manual 中 bye 的数量

    返回的 slots 列表里，None 表示 bye 占位（数据库写入时变成 player1=该 slot 玩家、
    player2=NULL、is_bye=1 的 match）。
    """
    n = len(participants)
    if n < 2:
        raise ValueError('至少需要 2 名参赛者')
    if bracket_size < n:
        raise ValueError('bracket_size 必须 >= 参赛人数')

    manual_slots = manual_slots or {}
    participant_ids = {p['player_id'] for p in participants}

    # ---- Step 1: 应用 manual_slots ----
    slots: List[Optional[str]] = [None] * bracket_size
    locked_player_ids = set()    # 已在某 slot 被锁定的 player_id
    locked_slot_indices = set()  # 已被手动占用的 slot 索引（0-based）
    manual_bye_count = 0

    for slot_1based, value in manual_slots.items():
        slot_idx = slot_1based - 1
        if slot_idx < 0 or slot_idx >= bracket_size:
            raise ValueError(f'slot 索引超出范围: {slot_1based}')
        if slot_idx in locked_slot_indices:
            raise ValueError(f'slot {slot_1based} 被指定了多次')

        if value == RESOURCE_BYE:
            slots[slot_idx] = None  # bye 占位
            manual_bye_count += 1
        else:
            # 必须是参赛者
            if value not in participant_ids:
                raise ValueError(f'slot {slot_1based} 指定的玩家不在参赛者中')
            if value in locked_player_ids:
                raise ValueError(f'玩家 {value} 被指定到了多个 slot')
            slots[slot_idx] = value
            locked_player_ids.add(value)

        locked_slot_indices.add(slot_idx)

    # ---- Step 2: 把声明的种子放进它们的标准 slot（如果该 slot 没被锁） ----
    seed_pos = _seed_order(bracket_size)  # seed_pos[i] = slot (i+1) 期望的种子号（1-based）

    seed_to_player = {}  # seed# → player_id（仅未被手动锁定的种子）
    for p in participants:
        s = p.get('seed')
        if s is not None and 1 <= s <= 4 and p['player_id'] not in locked_player_ids:
            seed_to_player[s] = p['player_id']

    for slot_idx, expected_seed in enumerate(seed_pos):
        if slot_idx in locked_slot_indices:
            continue  # 手动占用的不动
        if expected_seed > 4:
            continue  # 不是 1-4 号种子位
        if expected_seed in seed_to_player:
            slots[slot_idx] = seed_to_player[expected_seed]
            locked_player_ids.add(seed_to_player[expected_seed])
            locked_slot_indices.add(slot_idx)
            del seed_to_player[expected_seed]

    # ---- Step 3: 剩余资源分配（轮空尽量均分到上下半区） ----
    remaining_slots = [i for i in range(bracket_size) if i not in locked_slot_indices]
    remaining_players = [p['player_id'] for p in participants if p['player_id'] not in locked_player_ids]
    n_byes_needed = (bracket_size - n) - manual_bye_count
    if n_byes_needed < 0:
        raise ValueError('手动指定的 bye 数量超过 bracket 容量')

    # 构建待分配池：剩余玩家 + 需要的 bye
    pool = list(remaining_players) + [RESOURCE_BYE] * n_byes_needed
    if len(pool) != len(remaining_slots):
        raise ValueError(
            f'待分配资源({len(pool)})与剩余 slot 数({len(remaining_slots)})不一致')

    # 如果没有剩余 slot（全部手动指定了），直接返回
    if not remaining_slots:
        return slots

    # 尽量让 bye 在上下半区均匀分布：
    # 把剩余 slot 按半区分组，各组内随机填入玩家和 bye
    half_size = bracket_size // 2
    upper_slots = [i for i in remaining_slots if i < half_size]
    lower_slots = [i for i in remaining_slots if i >= half_size]

    # 已锁 bye 在两半区的分布
    upper_locked_byes = sum(1 for i in locked_slot_indices
                            if i < half_size and slots[i] is None)
    lower_locked_byes = manual_bye_count - upper_locked_byes

    # 各半区应分多少 bye（尽量均匀，受限于实际空位数）
    total_byes = bracket_size - n  # 含已锁和待分配
    target_upper = max(0, min((total_byes + 1) // 2 - upper_locked_byes, len(upper_slots)))
    target_lower = max(0, min(total_byes // 2 - lower_locked_byes, len(lower_slots)))
    # 剩余的 bye 给有空位的一边
    shortfall = n_byes_needed - target_upper - target_lower
    if shortfall > 0:
        if len(upper_slots) - target_upper >= shortfall:
            target_upper += shortfall
        else:
            target_lower += shortfall

    # 随机选哪些玩家去上半区
    random.shuffle(remaining_players)
    upper_player_count = len(upper_slots) - target_upper
    upper_pool = list(remaining_players[:upper_player_count]) + [RESOURCE_BYE] * target_upper
    lower_pool = list(remaining_players[upper_player_count:]) + [RESOURCE_BYE] * target_lower
    random.shuffle(upper_pool)
    random.shuffle(lower_pool)

    for slot_idx, item in zip(upper_slots, upper_pool):
        slots[slot_idx] = None if item == RESOURCE_BYE else item
    for slot_idx, item in zip(lower_slots, lower_pool):
        slots[slot_idx] = None if item == RESOURCE_BYE else item

    return slots


def preview_bracket_layout(tournament_id: str,
                           manual_slots: Optional[Dict[int, str]] = None
                           ) -> Tuple[Optional[Dict], str]:
    """Dry-run 计算首轮 slot 布局，不写库。返回
    (result_dict, '') 成功，或 (None, error_message) 失败。
    """
    tournament = get_tournament(tournament_id)
    if not tournament:
        return None, '赛事不存在'
    if tournament['status'] not in (STATUS_DRAFT, STATUS_REGISTRATION):
        return None, '赛事已生成对阵'
    participants = tournament['participants']
    if len(participants) < 2:
        return None, f'至少需要 2 名参赛者（当前 {len(participants)} 人）'

    bracket_size = max(4, _next_power_of_2(len(participants)))
    expected_rounds = int(math.log2(bracket_size))
    if len(tournament['rounds']) < expected_rounds:
        return None, (f'轮数配置不够：{len(participants)} 人需要 '
                      f'{expected_rounds} 轮，但只配了 {len(tournament["rounds"])} 轮')

    try:
        slots = _build_bracket_layout(participants, bracket_size, manual_slots=manual_slots)
    except ValueError as e:
        return None, f'手动 slot 设置冲突：{e}'

    # 把 None 映射回 '__bye__' 标记，方便前端识别
    payload_slots = {}
    for idx, val in enumerate(slots):
        slot_1based = str(idx + 1)
        payload_slots[slot_1based] = RESOURCE_BYE if val is None else val

    return {'bracket_size': bracket_size, 'slots': payload_slots}, ''


def generate_bracket(tournament_id: str,
                     manual_slots: Optional[Dict[int, str]] = None
                     ) -> Tuple[bool, str]:
    """
    根据当前报名 + 种子设置 + 手动 slot 指定，生成全部 rounds 的对阵记录。

    步骤：
      1) 验证当前状态为 draft/registration 且参赛人数 >= 2
      2) 计算 bracket_size = next_power_of_2(参赛人数)（最小 4）
      3) 调用 _build_bracket_layout 生成首轮 slot 布局
      4) 删除已有 matches（防御性）
      5) 创建所有轮的 matches；首轮按 slot 配对填 player1/player2
      6) bye 自动晋级（player1 → 下一轮）
      7) 状态切到 in_progress + 写 bracket_size

    参数：
      manual_slots: dict[slot_index_1based] = player_id 或 RESOURCE_BYE

    返回：
      (ok, message) — ok=False 时 message 包含具体失败原因
    """
    tournament = get_tournament(tournament_id)
    if not tournament:
        return False, '赛事不存在'
    if tournament['status'] not in (STATUS_DRAFT, STATUS_REGISTRATION):
        return False, '赛事已生成对阵，不能重复生成'

    participants = tournament['participants']
    if len(participants) < 2:
        return False, f'至少需要 2 名参赛者（当前 {len(participants)} 人）'

    bracket_size = max(4, _next_power_of_2(len(participants)))

    try:
        first_round_slots = _build_bracket_layout(
            participants, bracket_size, manual_slots=manual_slots)
    except ValueError as e:
        return False, f'手动 slot 设置冲突：{e}'

    expected_rounds = int(math.log2(bracket_size))
    if len(tournament['rounds']) < expected_rounds:
        return False, (f'轮数配置不够：{len(participants)} 人需要 {bracket_size} '
                       f'个位置的淘汰赛（{expected_rounds} 轮），'
                       f'但只配了 {len(tournament["rounds"])} 轮')

    now = get_utc_timestamp()
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 防御性清理
        cursor.execute(
            'DELETE FROM tournament_match_games WHERE match_id IN '
            '(SELECT match_id FROM tournament_matches WHERE tournament_id = ?)',
            (tournament_id,))
        cursor.execute('DELETE FROM tournament_matches WHERE tournament_id = ?', (tournament_id,))

        for round_index in range(1, expected_rounds + 1):
            matches_in_round = bracket_size // (2 ** round_index)
            for slot_index in range(1, matches_in_round + 1):
                match_id = str(uuid.uuid4())
                if round_index == 1:
                    p1_pos = (slot_index - 1) * 2
                    p2_pos = (slot_index - 1) * 2 + 1
                    p1 = first_round_slots[p1_pos]
                    p2 = first_round_slots[p2_pos]
                    is_bye = 1 if (p1 is None or p2 is None) else 0
                    if is_bye:
                        if p1 is None and p2 is not None:
                            p1, p2 = p2, None
                        winner_id = p1
                    else:
                        winner_id = None
                    cursor.execute('''
                        INSERT INTO tournament_matches
                        (match_id, tournament_id, round_index, slot_index,
                         player1_id, player2_id, is_bye, winner_id,
                         player1_games_won, player2_games_won,
                         started_at, finished_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
                    ''', (match_id, tournament_id, round_index, slot_index,
                          p1, p2, is_bye, winner_id,
                          now if winner_id else None,
                          now if winner_id else None))
                else:
                    cursor.execute('''
                        INSERT INTO tournament_matches
                        (match_id, tournament_id, round_index, slot_index,
                         player1_id, player2_id, is_bye, winner_id,
                         player1_games_won, player2_games_won)
                        VALUES (?, ?, ?, ?, NULL, NULL, 0, NULL, 0, 0)
                    ''', (match_id, tournament_id, round_index, slot_index))

        # bye 胜者向上晋级
        cursor.execute('''
            SELECT match_id, round_index, slot_index, winner_id
            FROM tournament_matches
            WHERE tournament_id = ? AND is_bye = 1 AND winner_id IS NOT NULL
            ORDER BY round_index, slot_index
        ''', (tournament_id,))
        for row in cursor.fetchall():
            _propagate_winner_to_next_round(
                cursor, tournament_id, row['round_index'], row['slot_index'], row['winner_id'])

        cursor.execute('''
            UPDATE tournaments SET bracket_size = ?, status = ?, updated_at = ?
            WHERE tournament_id = ?
        ''', (bracket_size, STATUS_IN_PROGRESS, now, tournament_id))

        conn.commit()
    return True, ''


def _propagate_winner_to_next_round(cursor, tournament_id: str,
                                    from_round: int, from_slot: int, winner_id: str) -> None:
    """把某场 match 的胜者填到下一轮对应 slot 的 player1 或 player2。

    映射规则：当前轮 slot=2k-1 → 下一轮 slot=k 的 player1
              当前轮 slot=2k   → 下一轮 slot=k 的 player2
    """
    next_round = from_round + 1
    next_slot = (from_slot + 1) // 2
    is_player1 = (from_slot % 2 == 1)

    cursor.execute('''
        SELECT match_id, player1_id, player2_id, is_bye
        FROM tournament_matches
        WHERE tournament_id = ? AND round_index = ? AND slot_index = ?
    ''', (tournament_id, next_round, next_slot))
    row = cursor.fetchone()
    if not row:
        return  # 已经是最后一轮

    if is_player1:
        cursor.execute('''
            UPDATE tournament_matches SET player1_id = ?
            WHERE match_id = ?
        ''', (winner_id, row['match_id']))
    else:
        cursor.execute('''
            UPDATE tournament_matches SET player2_id = ?
            WHERE match_id = ?
        ''', (winner_id, row['match_id']))


# ===== 查询 bracket（详情页用） =====

def get_bracket(tournament_id: str) -> List[List[Dict]]:
    """返回 [[round1_matches], [round2_matches], ...]，每场 match 含玩家名。

    在原始字段之外，额外注入：
      - match_number: 全局序号（按 round_index, slot_index 顺序累加）
      - prev_p1_number / prev_p2_number: 上一轮对应那场的 match_number，
        仅在玩家未确定时用于 UI 显示「对阵 N 胜者」占位。
      - player1_seed / player2_seed: 该玩家在本赛事的种子号（1-4 或 None）
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.*,
                   p1.name AS player1_name,
                   p2.name AS player2_name,
                   pw.name AS winner_name,
                   tp1.seed AS player1_seed,
                   tp2.seed AS player2_seed,
                   r.round_name, r.best_of
            FROM tournament_matches m
            LEFT JOIN players p1 ON p1.player_id = m.player1_id
            LEFT JOIN players p2 ON p2.player_id = m.player2_id
            LEFT JOIN players pw ON pw.player_id = m.winner_id
            LEFT JOIN tournament_participants tp1
                ON tp1.tournament_id = m.tournament_id AND tp1.player_id = m.player1_id
            LEFT JOIN tournament_participants tp2
                ON tp2.tournament_id = m.tournament_id AND tp2.player_id = m.player2_id
            JOIN tournament_rounds r ON r.tournament_id = m.tournament_id AND r.round_index = m.round_index
            WHERE m.tournament_id = ?
            ORDER BY m.round_index, m.slot_index
        ''', (tournament_id,))
        rows = [dict(r) for r in cursor.fetchall()]

    by_round: Dict[int, List[Dict]] = {}
    for r in rows:
        by_round.setdefault(r['round_index'], []).append(r)
    rounds = [by_round[i] for i in sorted(by_round.keys())]

    # 全局编号：按轮次顺序累加。首轮 1..N1，下一轮 N1+1..N1+N2，依此类推。
    counter = 0
    # number_lookup[(round_index, slot_index)] -> match_number
    number_lookup: Dict[Tuple[int, int], int] = {}
    for round_matches in rounds:
        for m in round_matches:
            counter += 1
            m['match_number'] = counter
            number_lookup[(m['round_index'], m['slot_index'])] = counter

    # 注入"上一轮对应场次"的编号，便于 UI 显示「对阵 N 胜者」占位
    for round_matches in rounds:
        for m in round_matches:
            if m['round_index'] == 1:
                m['prev_p1_number'] = None
                m['prev_p2_number'] = None
                continue
            prev_round = m['round_index'] - 1
            # 当前 slot S → 上一轮 slot 2S-1 (player1 来源) 和 2S (player2 来源)
            m['prev_p1_number'] = number_lookup.get((prev_round, m['slot_index'] * 2 - 1))
            m['prev_p2_number'] = number_lookup.get((prev_round, m['slot_index'] * 2))

    return rounds


def get_match(match_id: str) -> Optional[Dict]:
    """获取单场对阵的完整信息（含玩家名、轮信息、逐局历史、全局编号、上一轮对应场次编号）。"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.*,
                   p1.name AS player1_name,
                   p2.name AS player2_name,
                   pw.name AS winner_name,
                   tp1.seed AS player1_seed,
                   tp2.seed AS player2_seed,
                   r.round_name, r.best_of,
                   t.name AS tournament_name, t.status AS tournament_status
            FROM tournament_matches m
            LEFT JOIN players p1 ON p1.player_id = m.player1_id
            LEFT JOIN players p2 ON p2.player_id = m.player2_id
            LEFT JOIN players pw ON pw.player_id = m.winner_id
            LEFT JOIN tournament_participants tp1
                ON tp1.tournament_id = m.tournament_id AND tp1.player_id = m.player1_id
            LEFT JOIN tournament_participants tp2
                ON tp2.tournament_id = m.tournament_id AND tp2.player_id = m.player2_id
            JOIN tournament_rounds r ON r.tournament_id = m.tournament_id AND r.round_index = m.round_index
            JOIN tournaments t ON t.tournament_id = m.tournament_id
            WHERE m.match_id = ?
        ''', (match_id,))
        row = cursor.fetchone()
        if not row:
            return None
        match = dict(row)

        # 取逐局历史
        cursor.execute('''
            SELECT mg.game_index, mg.winner_id, p.name AS winner_name
            FROM tournament_match_games mg
            LEFT JOIN players p ON p.player_id = mg.winner_id
            WHERE mg.match_id = ?
            ORDER BY mg.game_index
        ''', (match_id,))
        match['games'] = [dict(g) for g in cursor.fetchall()]

        # 计算全局 match_number（按 round_index, slot_index 排序时的全局序号），
        # 以及上一轮对应位置的 match_number（用于"对阵 N 胜者"占位）。
        # 用 ROW_NUMBER 一次性算出整赛事的编号映射。
        cursor.execute('''
            SELECT match_id, round_index, slot_index,
                   ROW_NUMBER() OVER (ORDER BY round_index, slot_index) AS num
            FROM tournament_matches
            WHERE tournament_id = ?
        ''', (match['tournament_id'],))
        all_rows = cursor.fetchall()
        number_lookup = {(r['round_index'], r['slot_index']): r['num'] for r in all_rows}
        by_id = {r['match_id']: r['num'] for r in all_rows}

        match['match_number'] = by_id.get(match_id)
        if match['round_index'] == 1:
            match['prev_p1_number'] = None
            match['prev_p2_number'] = None
        else:
            prev_round = match['round_index'] - 1
            match['prev_p1_number'] = number_lookup.get((prev_round, match['slot_index'] * 2 - 1))
            match['prev_p2_number'] = number_lookup.get((prev_round, match['slot_index'] * 2))

        return match


# ===== 录入比分 / 撤销（#4） =====

def record_match_game(match_id: str, winner_side: int) -> Tuple[bool, str]:
    """记录某场对阵的下一局结果。

    winner_side: 1 表示 player1 赢这一局，2 表示 player2 赢。
    返回 (success, message)。
    自动判定整场胜负：任一方 games_won 达到 best_of 半数+1 时
    设置 winner_id + 晋级到下一轮。
    """
    if winner_side not in (1, 2):
        return False, '非法的 winner_side'

    match = get_match(match_id)
    if not match:
        return False, 'match 不存在'
    if match['is_bye']:
        return False, 'bye 比赛无需录入'
    if not match['player1_id'] or not match['player2_id']:
        return False, '该 match 玩家未确定，无法录入'
    if match['winner_id']:
        return False, '该 match 已结束'

    target = games_needed_to_win(match['best_of'])
    new_p1 = match['player1_games_won'] + (1 if winner_side == 1 else 0)
    new_p2 = match['player2_games_won'] + (1 if winner_side == 2 else 0)

    if new_p1 > target or new_p2 > target:
        return False, '比分超出 best-of 上限'

    now = get_utc_timestamp()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        # 计算新一局序号
        next_game_idx = len(match['games']) + 1
        winner_id = match['player1_id'] if winner_side == 1 else match['player2_id']
        cursor.execute('''
            INSERT INTO tournament_match_games (match_id, game_index, winner_id)
            VALUES (?, ?, ?)
        ''', (match_id, next_game_idx, winner_id))

        # 更新 match 总比分
        match_winner_id = None
        if new_p1 >= target:
            match_winner_id = match['player1_id']
        elif new_p2 >= target:
            match_winner_id = match['player2_id']

        if match_winner_id:
            cursor.execute('''
                UPDATE tournament_matches
                SET player1_games_won = ?, player2_games_won = ?,
                    winner_id = ?, finished_at = ?,
                    started_at = COALESCE(started_at, ?)
                WHERE match_id = ?
            ''', (new_p1, new_p2, match_winner_id, now, now, match_id))
            # 晋级
            _propagate_winner_to_next_round(
                cursor, match['tournament_id'],
                match['round_index'], match['slot_index'], match_winner_id)
            # 检查是否决赛胜出 → 完成赛事
            cursor.execute('''
                SELECT MAX(round_index) AS final_round
                FROM tournament_matches WHERE tournament_id = ?
            ''', (match['tournament_id'],))
            final_round = cursor.fetchone()['final_round']
            if match['round_index'] == final_round:
                cursor.execute('''
                    UPDATE tournaments SET status = ?, completed_at = ?, updated_at = ?
                    WHERE tournament_id = ?
                ''', (STATUS_COMPLETED, now, now, match['tournament_id']))
        else:
            cursor.execute('''
                UPDATE tournament_matches
                SET player1_games_won = ?, player2_games_won = ?,
                    started_at = COALESCE(started_at, ?)
                WHERE match_id = ?
            ''', (new_p1, new_p2, now, match_id))

        conn.commit()
    return True, '已记录'


def record_match_result(match_id: str, p1_games: int, p2_games: int) -> Tuple[bool, str]:
    """直接录入整场比赛的总比分（覆盖式，用于一次性输入最终结果）。

    要求其中一方达到 best-of 胜局数，另一方少于胜局数。
    覆盖时会清掉之前的逐局记录。
    """
    match = get_match(match_id)
    if not match:
        return False, 'match 不存在'
    if match['is_bye']:
        return False, 'bye 比赛无需录入'
    if not match['player1_id'] or not match['player2_id']:
        return False, '该 match 玩家未确定，无法录入'
    if match['winner_id']:
        return False, '该 match 已结束（如要修改请先撤销）'

    if p1_games < 0 or p2_games < 0:
        return False, '比分不能为负'
    target = games_needed_to_win(match['best_of'])
    if max(p1_games, p2_games) != target:
        return False, f'胜方必须刚好达到 {target} 胜（best-of {match["best_of"]}）'
    if min(p1_games, p2_games) >= target:
        return False, '不能两方都达到胜局数'

    winner_id = match['player1_id'] if p1_games > p2_games else match['player2_id']
    now = get_utc_timestamp()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        # 清掉之前的逐局记录（如果有）
        cursor.execute('DELETE FROM tournament_match_games WHERE match_id = ?', (match_id,))

        cursor.execute('''
            UPDATE tournament_matches
            SET player1_games_won = ?, player2_games_won = ?,
                winner_id = ?, finished_at = ?,
                started_at = COALESCE(started_at, ?)
            WHERE match_id = ?
        ''', (p1_games, p2_games, winner_id, now, now, match_id))

        _propagate_winner_to_next_round(
            cursor, match['tournament_id'],
            match['round_index'], match['slot_index'], winner_id)

        # 决赛 → 完成赛事
        cursor.execute('''
            SELECT MAX(round_index) AS final_round
            FROM tournament_matches WHERE tournament_id = ?
        ''', (match['tournament_id'],))
        final_round = cursor.fetchone()['final_round']
        if match['round_index'] == final_round:
            cursor.execute('''
                UPDATE tournaments SET status = ?, completed_at = ?, updated_at = ?
                WHERE tournament_id = ?
            ''', (STATUS_COMPLETED, now, now, match['tournament_id']))

        conn.commit()
    return True, '已记录'


def reset_match(match_id: str) -> Tuple[bool, str]:
    """撤销一场 match 的录入：清空 winner_id / 比分 / 逐局记录，
    并把下一轮对应 slot 的 player1/player2 字段清掉（否则会显示错误的对手）。

    拒绝条件：下一轮对应 match 已有 winner_id（已开打），不能撤销，
    需要先撤销下一轮再回来撤这场。
    """
    match = get_match(match_id)
    if not match:
        return False, 'match 不存在'
    if match['is_bye']:
        return False, 'bye 不能撤销（请重新生成 bracket）'
    if not match['winner_id']:
        return False, '该 match 尚未结束'

    with db.get_connection() as conn:
        cursor = conn.cursor()
        # 检查下一轮是否已有结果
        next_round = match['round_index'] + 1
        next_slot = (match['slot_index'] + 1) // 2
        cursor.execute('''
            SELECT match_id, winner_id FROM tournament_matches
            WHERE tournament_id = ? AND round_index = ? AND slot_index = ?
        ''', (match['tournament_id'], next_round, next_slot))
        next_match = cursor.fetchone()
        if next_match and next_match['winner_id']:
            return False, '下一轮对应 match 已有结果，请先撤销下一轮'

        # 清掉下一轮的 player1 或 player2 字段
        if next_match:
            is_player1 = (match['slot_index'] % 2 == 1)
            field = 'player1_id' if is_player1 else 'player2_id'
            cursor.execute(f'''
                UPDATE tournament_matches SET {field} = NULL
                WHERE match_id = ?
            ''', (next_match['match_id'],))

        # 清掉本场的结果
        cursor.execute('DELETE FROM tournament_match_games WHERE match_id = ?', (match_id,))
        cursor.execute('''
            UPDATE tournament_matches
            SET winner_id = NULL, player1_games_won = 0, player2_games_won = 0,
                finished_at = NULL
            WHERE match_id = ?
        ''', (match_id,))

        # 如果该赛事此前是 completed（决赛被撤销），切回 in_progress
        cursor.execute('''
            UPDATE tournaments SET status = ?, completed_at = NULL, updated_at = ?
            WHERE tournament_id = ? AND status = ?
        ''', (STATUS_IN_PROGRESS, get_utc_timestamp(),
              match['tournament_id'], STATUS_COMPLETED))

        conn.commit()
    return True, '已撤销'


def undo_last_game(match_id: str) -> Tuple[bool, str]:
    """撤回某场对阵的最后一局。

    如果整场比赛已结束（有 winner_id），也一并撤回胜负判定和晋级。
    """
    match = get_match(match_id)
    if not match:
        return False, 'match 不存在'
    if match['is_bye']:
        return False, 'bye 比赛无需操作'
    if not match['games']:
        return False, '没有可撤回的局'

    # 如果比赛已结束，需要先检查下一轮是否已开打
    if match['winner_id']:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            next_round = match['round_index'] + 1
            next_slot = (match['slot_index'] + 1) // 2
            cursor.execute('''
                SELECT match_id, winner_id, started_at FROM tournament_matches
                WHERE tournament_id = ? AND round_index = ? AND slot_index = ?
            ''', (match['tournament_id'], next_round, next_slot))
            next_match = cursor.fetchone()
            if next_match and next_match['winner_id']:
                return False, '下一轮对应 match 已有结果，请先撤销下一轮'

    last_game = match['games'][-1]
    last_winner = last_game['winner_id']
    new_p1 = match['player1_games_won'] - (1 if last_winner == match['player1_id'] else 0)
    new_p2 = match['player2_games_won'] - (1 if last_winner == match['player2_id'] else 0)

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 删除最后一局
        cursor.execute('''
            DELETE FROM tournament_match_games
            WHERE match_id = ? AND game_index = ?
        ''', (match_id, last_game['game_index']))

        if match['winner_id']:
            # 撤回整场胜负：清 winner、晋级 slot、可能的赛事完成状态
            next_round = match['round_index'] + 1
            next_slot = (match['slot_index'] + 1) // 2
            cursor.execute('''
                SELECT match_id FROM tournament_matches
                WHERE tournament_id = ? AND round_index = ? AND slot_index = ?
            ''', (match['tournament_id'], next_round, next_slot))
            next_match = cursor.fetchone()
            if next_match:
                is_player1 = (match['slot_index'] % 2 == 1)
                field = 'player1_id' if is_player1 else 'player2_id'
                cursor.execute(f'''
                    UPDATE tournament_matches SET {field} = NULL
                    WHERE match_id = ?
                ''', (next_match['match_id'],))

            cursor.execute('''
                UPDATE tournament_matches
                SET player1_games_won = ?, player2_games_won = ?,
                    winner_id = NULL, finished_at = NULL
                WHERE match_id = ?
            ''', (new_p1, new_p2, match_id))

            # 如果赛事已完成（决赛被撤），切回 in_progress
            cursor.execute('''
                UPDATE tournaments SET status = ?, completed_at = NULL, updated_at = ?
                WHERE tournament_id = ? AND status = ?
            ''', (STATUS_IN_PROGRESS, get_utc_timestamp(),
                  match['tournament_id'], STATUS_COMPLETED))
        else:
            cursor.execute('''
                UPDATE tournament_matches
                SET player1_games_won = ?, player2_games_won = ?
                WHERE match_id = ?
            ''', (new_p1, new_p2, match_id))

        conn.commit()

    p_name = match['player1_name'] if last_winner == match['player1_id'] else match['player2_name']
    return True, f'已撤回第 {last_game["game_index"]} 局（{p_name} 赢）'
    """返回 [[round1_matches], [round2_matches], ...]，每场 match 含玩家名。"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.*,
                   p1.name AS player1_name,
                   p2.name AS player2_name,
                   pw.name AS winner_name,
                   r.round_name, r.best_of
            FROM tournament_matches m
            LEFT JOIN players p1 ON p1.player_id = m.player1_id
            LEFT JOIN players p2 ON p2.player_id = m.player2_id
            LEFT JOIN players pw ON pw.player_id = m.winner_id
            JOIN tournament_rounds r ON r.tournament_id = m.tournament_id AND r.round_index = m.round_index
            WHERE m.tournament_id = ?
            ORDER BY m.round_index, m.slot_index
        ''', (tournament_id,))
        rows = [dict(r) for r in cursor.fetchall()]

    # 按 round_index 分组
    by_round: Dict[int, List[Dict]] = {}
    for r in rows:
        by_round.setdefault(r['round_index'], []).append(r)
    return [by_round[i] for i in sorted(by_round.keys())]


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
    """根据 matches 表推算选手在该赛事的当前名次描述。

    定义"最深一轮" = 选手作为 player1 或 player2 出现的最大 round_index 的那场 match
    （包括尚未结束的）。
    - 该 match 没结束：选手还在打这一轮 → "X 强 (进行中)"，X = 该轮还存活的人数
    - 该 match 已结束且 winner == player：
        - 是决赛 → 冠军
        - 不是决赛：选手晋级了，但还没到下一轮 match (理论上 propagate 时会把他放进下一轮)
          这种情况多半是数据中下一轮 match 已存在但还没显示在他的 match 列表里 ——
          为安全起见仍按"还存活"显示
    - 该 match 已结束且 winner != player → 在这一轮被淘汰
        - 是决赛 → 亚军
        - 否则 → "X 强"，X = 该轮还存活的人数
    """
    if status == STATUS_DRAFT or status == STATUS_REGISTRATION or not bracket_size:
        return '已报名'

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT round_index, winner_id, player1_id, player2_id, is_bye
            FROM tournament_matches
            WHERE tournament_id = ?
              AND (player1_id = ? OR player2_id = ?)
            ORDER BY round_index DESC
        ''', (tournament_id, player_id, player_id))
        matches = cursor.fetchall()

        if not matches:
            return '未出场'

        total_rounds = int(math.log2(bracket_size))
        deepest = matches[0]
        deepest_round = deepest['round_index']
        # 该轮"还存活"的人数 = 2^(total_rounds - deepest_round + 1)
        # 例：8 人 bracket (3 轮)，R1=8 强，R2=4 强，R3=决赛(2 强 = 决赛)
        survivors_in_round = 2 ** (total_rounds - deepest_round + 1)

        if deepest['winner_id'] is None:
            # 这一轮还没结束：选手还在打
            if deepest_round == total_rounds:
                return '决赛中'
            return f'{survivors_in_round} 强 (进行中)'

        # 这一轮已结束
        if deepest['winner_id'] == player_id:
            # 选手赢了，应该已被 propagate 到下一轮 match —— 如果没出现在更深一轮，
            # 通常意味着下一轮 match 还没建好（极少数情况）。按"已晋级到 N/2 强"显示。
            if deepest_round == total_rounds:
                return '冠军'
            next_survivors = 2 ** (total_rounds - deepest_round)
            return f'晋级 {next_survivors} 强'

        # 选手在这一轮被淘汰
        if deepest_round == total_rounds:
            return '亚军'
        return f'{survivors_in_round} 强'
