"""
数据模型和数据库操作模块 - 使用SQLite数据库
提供数据一致性保证和线程安全访问
"""
import os
import json
from typing import List, Dict, Optional
from .database import db
from .utils import get_utc_timestamp


# ===== 兼容性接口 - 保持与原有代码的兼容性 =====

def init_data():
    """初始化数据，检查是否需要从JSON迁移"""
    print("初始化数据库...")
    
    # 检查是否存在旧的JSON数据需要迁移
    json_file = get_data_file_path()
    if os.path.exists(json_file):
        print(f"发现JSON数据文件: {json_file}")
        
        # 检查数据库是否为空（首次迁移）
        players = db.get_all_players()
        if not players:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                    db.migrate_from_json(json_data)
                    
                # 迁移完成后备份JSON文件
                backup_file = json_file + '.backup'
                os.rename(json_file, backup_file)
                print(f"JSON数据已迁移，原文件备份为: {backup_file}")
            except Exception as e:
                print(f"JSON数据迁移失败: {e}")
    
    # 统计数据
    players = db.get_all_players()
    sessions = db.get_all_sessions()
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
    else:
        return 'data.json'


def save_data():
    """保存数据（兼容性保留，数据库自动保存）"""
    # 数据库操作是实时的，无需手动保存
    pass


# ===== 玩家管理函数 =====

def create_player(name: str) -> str:
    """创建新玩家，返回player_id"""
    return db.create_player(name)


def get_player_by_name(name: str) -> Optional[str]:
    """根据名字查找玩家，返回player_id或None"""
    return db.get_player_by_name(name)


def get_or_create_player(name: str) -> str:
    """获取或创建玩家，返回player_id"""
    return db.get_or_create_player(name)


def get_player_name(player_id: str) -> str:
    """根据player_id获取玩家名字"""
    return db.get_player_name(player_id)


def update_player_name(player_id: str, new_name: str) -> bool:
    """更新玩家名字"""
    return db.update_player_name(player_id, new_name)


def get_all_players() -> List[Dict]:
    """获取所有玩家列表"""
    return db.get_all_players()


def get_available_players(exclude_session_id: str = None) -> List[Dict]:
    """获取所有可用玩家，可排除指定场次中的玩家"""
    return db.get_available_players(exclude_session_id)


# ===== 场次管理函数 =====

def create_session(name: str) -> str:
    """创建新场次，返回session_id"""
    return db.create_session(name)


def get_session(session_id: str) -> Optional[Dict]:
    """获取场次完整信息（兼容原有格式）"""
    return db.get_session_with_players(session_id)


def get_active_sessions() -> List[Dict]:
    """获取所有活跃场次"""
    return db.get_active_sessions()


def get_ended_sessions(limit: int = 3) -> List[Dict]:
    """获取最近结束的场次"""
    return db.get_ended_sessions(limit)


def get_all_sessions() -> List[Dict]:
    """获取所有场次"""
    return db.get_all_sessions()


def end_session(session_id: str) -> bool:
    """结束场次"""
    return db.end_session(session_id)


def delete_session(session_id: str) -> bool:
    """删除场次"""
    return db.delete_session(session_id)


def add_player_to_session(session_id: str, player_id: str) -> bool:
    """将玩家添加到场次"""
    return db.add_player_to_session(session_id, player_id)


def get_session_players(session_id: str) -> List[Dict]:
    """获取场次中的所有玩家"""
    return db.get_session_players(session_id)


# ===== 计分记录管理 =====

def add_game_record(session_id: str, winner_id: str, loser_id: str, 
                   score: int, special_score: str = None, loser_id2: str = None) -> int:
    """添加计分记录，支持单败者和多败者"""
    return db.add_game_record(session_id, winner_id, loser_id, score, special_score, loser_id2)


def add_multi_loser_record(session_id: str, winner_id: str, loser_id1: str, 
                          loser_id2: str, total_score: int, special_score: str = None) -> int:
    """添加一对二的计分记录（兼容性保留，实际调用add_game_record）"""
    return db.add_game_record(session_id, winner_id, loser_id1, total_score, special_score, loser_id2)


def get_session_records(session_id: str) -> List[Dict]:
    """获取场次的计分记录"""
    return db.get_session_records(session_id)


def delete_game_record(record_id: int) -> Optional[Dict]:
    """删除计分记录"""
    return db.delete_game_record(record_id)


def get_player_records(player_id: str) -> List[Dict]:
    """获取玩家的所有对战记录"""
    return db.get_player_records(player_id)


# ===== 统计查询 =====

def get_player_stats(player_id: str) -> Dict:
    """获取玩家统计数据"""
    return db.get_player_stats(player_id)


def get_global_leaderboard(start_date: str = None, end_date: str = None) -> List[Dict]:
    """获取全局排行榜"""
    return db.get_global_leaderboard(start_date, end_date)


def get_available_months() -> List[Dict]:
    """获取有游戏记录的月份列表"""
    return db.get_available_months()


def get_player_by_id(player_id: str) -> Optional[Dict]:
    """根据player_id获取玩家完整信息"""
    return db.get_player_by_id(player_id)


# ===== 特殊胜利记录查询 =====

def get_player_special_wins(player_id: str) -> Dict:
    """获取玩家的特殊胜利记录（小金、大金）"""
    return db.get_player_special_wins(player_id)


def get_players_special_wins_batch(player_ids: List[str]) -> Dict:
    """批量获取多个玩家的特殊胜利记录"""
    return db.get_players_special_wins_batch(player_ids)


# ===== 兼容性变量 - 用于保持与原有代码的兼容性 =====

class SessionsProxy:
    """场次代理类，提供类似字典的接口"""
    
    def __contains__(self, session_id: str) -> bool:
        """检查场次是否存在"""
        return db.get_session_by_id(session_id) is not None
    
    def __getitem__(self, session_id: str) -> Dict:
        """获取场次信息"""
        session = db.get_session_with_players(session_id)
        if session is None:
            raise KeyError(f"Session {session_id} not found")
        return session
    
    def __setitem__(self, session_id: str, session_data: Dict):
        """设置场次信息（用于兼容性，不建议使用）"""
        # 这个方法主要用于兼容性，实际应该使用数据库接口
        pass
    
    def __delitem__(self, session_id: str):
        """删除场次"""
        db.delete_session(session_id)
    
    def get(self, session_id: str, default=None):
        """获取场次信息，不存在时返回默认值"""
        session = db.get_session_with_players(session_id)
        return session if session is not None else default
    
    def items(self):
        """获取所有场次的迭代器"""
        sessions = db.get_all_sessions()
        for session in sessions:
            full_session = db.get_session_with_players(session['session_id'])
            yield session['session_id'], full_session
    
    def values(self):
        """获取所有场次的值"""
        sessions = db.get_all_sessions()
        for session in sessions:
            full_session = db.get_session_with_players(session['session_id'])
            yield full_session
    
    def keys(self):
        """获取所有场次的键"""
        sessions = db.get_all_sessions()
        for session in sessions:
            yield session['session_id']


class PlayersProxy:
    """玩家代理类，提供类似字典的接口"""
    
    def __contains__(self, player_id: str) -> bool:
        """检查玩家是否存在"""
        return db.get_player_by_id(player_id) is not None
    
    def __getitem__(self, player_id: str) -> Dict:
        """获取玩家信息"""
        player = db.get_player_by_id(player_id)
        if player is None:
            raise KeyError(f"Player {player_id} not found")
        return player
    
    def get(self, player_id: str, default=None):
        """获取玩家信息，不存在时返回默认值"""
        player = db.get_player_by_id(player_id)
        return player if player is not None else default
    
    def items(self):
        """获取所有玩家的迭代器"""
        players = db.get_all_players()
        for player in players:
            yield player['player_id'], player
    
    def values(self):
        """获取所有玩家的值"""
        players = db.get_all_players()
        for player in players:
            yield player
    
    def keys(self):
        """获取所有玩家的键"""
        players = db.get_all_players()
        for player in players:
            yield player['player_id']


# 创建兼容性代理对象
sessions = SessionsProxy()
players = PlayersProxy()

# 兼容性列表
recent_player_ids = []  # 这个将通过get_recent_players()函数获取
