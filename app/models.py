"""
数据模型和数据库操作模块 - 使用SQLite数据库
提供数据一致性保证和线程安全访问
"""
import os
import json
from typing import List, Dict, Optional

from .database import db
from .tenancy import EMS_ORG_ID


# ===== 兼容性接口 - 保持与原有代码的兼容性 =====

def init_data():
    """初始化 EMS 组织数据，并检查是否需要从旧 JSON 迁移。"""
    print("初始化数据库...")

    # 检查是否存在旧的JSON数据需要迁移
    json_file = get_data_file_path()
    if os.path.exists(json_file):
        print(f"发现JSON数据文件: {json_file}")

        # 检查数据库是否为空（首次迁移）
        players = db.get_all_players(EMS_ORG_ID)
        if not players:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                    db.migrate_from_json(json_data, EMS_ORG_ID)

                # 迁移完成后备份JSON文件
                backup_file = json_file + '.backup'
                os.rename(json_file, backup_file)
                print(f"JSON数据已迁移，原文件备份为: {backup_file}")
            except Exception as e:
                print(f"JSON数据迁移失败: {e}")

    # 统计数据
    players = db.get_all_players(EMS_ORG_ID)
    sessions = db.get_all_sessions(EMS_ORG_ID)
    print(f"数据库初始化完成: {len(sessions)} 个场次, {len(players)} 个玩家")


def get_data_file_path():
    """获取数据文件路径（兼容性保留）"""
    if os.environ.get('WEBSITE_SITE_NAME'):
        data_dir = '/home/data'
        try:
            os.makedirs(data_dir, exist_ok=True)
        except OSError:
            data_dir = '/home'
        return os.path.join(data_dir, 'data.json')
    return 'data.json'


def save_data():
    """保存数据（兼容性保留，数据库自动保存）"""
    # 数据库操作是实时的，无需手动保存
    pass


# ===== 玩家管理函数 =====

def create_player(org_id: str, name: str) -> str:
    """创建新玩家，返回player_id"""
    return db.create_player(org_id, name)


def get_player_by_name(org_id: str, name: str) -> Optional[str]:
    """根据名字查找玩家，返回player_id或None"""
    return db.get_player_by_name(org_id, name)


def get_or_create_player(org_id: str, name: str) -> str:
    """获取或创建玩家，返回player_id"""
    return db.get_or_create_player(org_id, name)


def get_player_name(org_id: str, player_id: str) -> str:
    """根据player_id获取玩家名字"""
    return db.get_player_name(org_id, player_id)


def update_player_name(org_id: str, player_id: str, new_name: str) -> bool:
    """更新玩家名字"""
    return db.update_player_name(org_id, player_id, new_name)


def get_all_players(org_id: str) -> List[Dict]:
    """获取所有玩家列表"""
    return db.get_all_players(org_id)


def get_available_players(org_id: str, exclude_session_id: str = None) -> List[Dict]:
    """获取所有可用玩家，可排除指定场次中的玩家"""
    return db.get_available_players(org_id, exclude_session_id)


# ===== 场次管理函数 =====

def create_session(org_id: str, name: str) -> str:
    """创建新场次，返回session_id"""
    return db.create_session(org_id, name)


def get_session(org_id: str, session_id: str) -> Optional[Dict]:
    """获取场次完整信息（兼容原有格式）"""
    return db.get_session_with_players(org_id, session_id)


def get_active_sessions(org_id: str) -> List[Dict]:
    """获取所有活跃场次"""
    return db.get_active_sessions(org_id)


def get_ended_sessions(org_id: str, limit: int = 3) -> List[Dict]:
    """获取最近结束的场次"""
    return db.get_ended_sessions(org_id, limit)


def get_all_sessions(org_id: str) -> List[Dict]:
    """获取所有场次"""
    return db.get_all_sessions(org_id)


def end_session(org_id: str, session_id: str) -> bool:
    """结束场次"""
    return db.end_session(org_id, session_id)


def delete_session(org_id: str, session_id: str) -> bool:
    """删除场次"""
    return db.delete_session(org_id, session_id)


def add_player_to_session(org_id: str, session_id: str, player_id: str) -> bool:
    """将玩家添加到场次"""
    return db.add_player_to_session(org_id, session_id, player_id)


def get_session_players(org_id: str, session_id: str) -> List[Dict]:
    """获取场次中的所有玩家"""
    return db.get_session_players(org_id, session_id)


# ===== 计分记录管理 =====

def add_game_record(org_id: str, session_id: str, winner_id: str, loser_id: str,
                    score: int, special_score: str = None,
                    loser_id2: str = None, winner_id2: str = None) -> int:
    """添加计分记录，支持单败者、多败者和多赢家"""
    return db.add_game_record(
        org_id, session_id, winner_id, loser_id, score, special_score,
        loser_id2, winner_id2,
    )


def add_multi_loser_record(org_id: str, session_id: str, winner_id: str,
                           loser_id1: str, loser_id2: str, total_score: int,
                           special_score: str = None) -> int:
    """添加一对二的计分记录（兼容性保留，实际调用add_game_record）"""
    return db.add_game_record(
        org_id, session_id, winner_id, loser_id1, total_score, special_score,
        loser_id2,
    )


def get_session_records(org_id: str, session_id: str) -> List[Dict]:
    """获取场次的计分记录"""
    return db.get_session_records(org_id, session_id)


def delete_game_record(org_id: str, record_id: int) -> Optional[Dict]:
    """删除计分记录"""
    return db.delete_game_record(org_id, record_id)


def get_player_records(org_id: str, player_id: str, start_date: str = None,
                       end_date: str = None) -> List[Dict]:
    """获取玩家的所有对战记录。可选按 created_at 范围过滤（闭区间）。"""
    return db.get_player_records(org_id, player_id, start_date, end_date)


# ===== 统计查询 =====

def get_player_stats(org_id: str, player_id: str) -> Dict:
    """获取玩家统计数据"""
    return db.get_player_stats(org_id, player_id)


def get_global_leaderboard(org_id: str, start_date: str = None,
                           end_date: str = None) -> List[Dict]:
    """获取全局排行榜"""
    return db.get_global_leaderboard(org_id, start_date, end_date)


def get_available_months(org_id: str) -> List[Dict]:
    """获取有数据的月份列表"""
    return db.get_available_months(org_id)


def get_available_months_for_player(org_id: str, player_id: str) -> List[Dict]:
    """获取该玩家有对局的月份列表"""
    return db.get_available_months_for_player(org_id, player_id)


def get_player_tournament_history(org_id: str, player_id: str) -> List[Dict]:
    """获取该玩家参与过的所有杯赛及最终成绩。"""
    from .tournament import get_player_tournament_history as _impl
    return _impl(org_id, player_id)


def get_earliest_session_date(org_id: str) -> Optional[str]:
    """获取最早的会话日期（用于默认日期范围）"""
    sessions = db.get_all_sessions(org_id)
    if not sessions:
        return None

    # 会话已按创建时间降序排列，取最后一个
    earliest_session = sessions[-1]
    created_at = earliest_session.get('created_at', '')

    if created_at:
        # 提取日期部分 (YYYY-MM-DD)
        return created_at[:10]

    return None


def get_player_by_id(org_id: str, player_id: str) -> Optional[Dict]:
    """根据player_id获取玩家完整信息"""
    return db.get_player_by_id(org_id, player_id)


# ===== 特殊胜利记录查询 =====

def get_player_special_wins(org_id: str, player_id: str) -> Dict:
    """获取玩家的特殊胜利记录（小金、大金）"""
    return db.get_player_special_wins(org_id, player_id)


def get_players_special_wins_batch(org_id: str, player_ids: List[str]) -> Dict:
    """批量获取多个玩家的特殊胜利记录"""
    return db.get_players_special_wins_batch(org_id, player_ids)


def get_achievement_players(org_id: str, achievement_type: str) -> List[Dict]:
    """获取达成指定成就的玩家列表"""
    return db.get_achievement_players(org_id, achievement_type)


def get_achievement_records(org_id: str, achievement_type: str,
                            player_id: str = None) -> List[Dict]:
    """获取成就达成记录详情"""
    return db.get_achievement_records(org_id, achievement_type, player_id)


def get_achievement_stats(org_id: str) -> Dict:
    """获取成就系统统计信息"""
    return db.get_achievement_stats(org_id)


def get_achievement_master_players(org_id: str,
                                    achievement_type: str) -> List[Dict]:
    """获取达人成就的玩家列表"""
    return db.get_achievement_master_players(org_id, achievement_type)


def get_negative_achievement_players(org_id: str,
                                     achievement_type: str) -> List[Dict]:
    """获取负面成就的玩家列表"""
    players = db.get_negative_achievement_players(org_id, achievement_type)

    if achievement_type == 'gold_loser':
        records = db.get_negative_achievement_records(org_id, achievement_type)
        # 为每个玩家计算被谁痛击最多
        for player in players:
            opponent_counts = {}
            for record in records:
                # 检查是否是这个玩家被痛击
                if (record.get('loser_name') == player['name'] or
                        record.get('loser2_name') == player['name']):
                    winner = record['winner_name']
                    opponent_counts[winner] = opponent_counts.get(winner, 0) + 1

            # 找出痛击次数最多的对手
            if opponent_counts:
                most_defeated_by = max(opponent_counts.items(), key=lambda x: x[1])
                player['most_defeated_by'] = most_defeated_by[0]
                player['most_defeated_count'] = most_defeated_by[1]
            else:
                player['most_defeated_by'] = None
                player['most_defeated_count'] = 0

    return players


def get_negative_achievement_records(org_id: str, achievement_type: str,
                                     player_id: str = None) -> List[Dict]:
    """获取负面成就记录详情"""
    return db.get_negative_achievement_records(org_id, achievement_type, player_id)


def get_best_buddy_stats(org_id: str) -> List[Dict]:
    """获取好兄弟统计"""
    return db.get_best_buddy_stats(org_id)


def get_duo_loser_stats(org_id: str) -> List[Dict]:
    """获取有难同当统计"""
    return db.get_duo_loser_stats(org_id)


def get_honor_roll_stats(org_id: str, top_n: int = 10) -> Dict:
    """获取榜上有名（冠军榜 + 必吃榜）统计"""
    return db.get_honor_roll_stats(org_id, top_n)


def retire_player(org_id: str, player_id: str):
    """退役玩家"""
    db.retire_player(org_id, player_id)


def comeback_player(org_id: str, player_id: str):
    """复出玩家"""
    db.comeback_player(org_id, player_id)


def is_player_retired(org_id: str, player_id: str) -> bool:
    """检查玩家是否退役"""
    return db.is_player_retired(org_id, player_id)


def get_retired_player_ids(org_id: str) -> set:
    """获取所有退役玩家ID"""
    return db.get_retired_player_ids(org_id)


# 兼容性列表
recent_player_ids = []  # 这个将通过get_recent_players()函数获取
