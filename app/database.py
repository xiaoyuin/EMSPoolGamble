"""
数据库操作模块 - 使用SQLite替换JSON存储
提供数据一致性保证和并发安全访问
"""
import sqlite3
import uuid
import os
import json
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager
from .utils import get_utc_timestamp


class DatabaseManager:
    """数据库管理类，提供所有数据操作接口"""
    
    def __init__(self, db_path: str = None):
        """初始化数据库连接"""
        if db_path is None:
            # 检测是否在Azure环境
            if os.environ.get('WEBSITE_SITE_NAME'):
                # Azure环境使用持久化目录
                data_dir = '/home/data'
                try:
                    os.makedirs(data_dir, exist_ok=True)
                    db_path = os.path.join(data_dir, 'ems_pool_gamble.db')
                except OSError:
                    # 降级到/home目录
                    db_path = '/home/ems_pool_gamble.db'
            else:
                # 本地开发环境
                db_path = 'ems_pool_gamble.db'
        
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 使结果可以像字典一样访问
        try:
            yield conn
        finally:
            conn.close()
    
    def init_database(self):
        """初始化数据库表结构"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 创建玩家表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    player_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            # 创建场次表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    end_time TEXT
                )
            ''')
            
            # 创建场次玩家关联表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id),
                    FOREIGN KEY (player_id) REFERENCES players (player_id),
                    UNIQUE(session_id, player_id)
                )
            ''')
            
            # 创建计分记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_records (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    winner_id TEXT NOT NULL,
                    loser_id TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    special_score_part TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id),
                    FOREIGN KEY (winner_id) REFERENCES players (player_id),
                    FOREIGN KEY (loser_id) REFERENCES players (player_id)
                )
            ''')
            
            # 创建索引优化查询性能
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_name ON players (name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions (active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_session_players_session ON session_players (session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_game_records_session ON game_records (session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_game_records_players ON game_records (winner_id, loser_id)')
            
            conn.commit()
            print(f"数据库初始化完成: {self.db_path}")
    
    # ===== 玩家相关操作 =====
    
    def create_player(self, name: str) -> str:
        """创建新玩家，返回player_id"""
        player_id = str(uuid.uuid4())
        current_time = get_utc_timestamp()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO players (player_id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (player_id, name, current_time, current_time))
            conn.commit()
        
        return player_id
    
    def get_player_by_name(self, name: str) -> Optional[str]:
        """根据名字查找玩家，返回player_id或None"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT player_id FROM players WHERE name = ?', (name,))
            result = cursor.fetchone()
            return result['player_id'] if result else None
    
    def get_or_create_player(self, name: str) -> str:
        """获取或创建玩家，返回player_id"""
        player_id = self.get_player_by_name(name)
        if player_id is None:
            player_id = self.create_player(name)
        return player_id
    
    def get_player_by_id(self, player_id: str) -> Optional[Dict]:
        """根据player_id获取玩家信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM players WHERE player_id = ?', (player_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def get_player_name(self, player_id: str) -> str:
        """根据player_id获取玩家名字"""
        player = self.get_player_by_id(player_id)
        return player['name'] if player else 'Unknown Player'
    
    def update_player_name(self, player_id: str, new_name: str) -> bool:
        """更新玩家名字"""
        current_time = get_utc_timestamp()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE players SET name = ?, updated_at = ? WHERE player_id = ?
            ''', (new_name, current_time, player_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_all_players(self) -> List[Dict]:
        """获取所有玩家列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM players ORDER BY name')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_available_players(self, exclude_session_id: str = None) -> List[Dict]:
        """获取所有可用玩家，可排除指定场次中的玩家，包含有效胜率信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if exclude_session_id:
                cursor.execute('''
                    SELECT p.player_id, p.name
                    FROM players p
                    WHERE p.player_id NOT IN (
                        SELECT player_id FROM session_players WHERE session_id = ?
                    )
                    ORDER BY p.name
                ''', (exclude_session_id,))
            else:
                cursor.execute('''
                    SELECT p.player_id, p.name
                    FROM players p
                    ORDER BY p.name
                ''')
            
            players = []
            for row in cursor.fetchall():
                player_data = {
                    'id': row['player_id'], 
                    'name': row['name']
                }
                # 计算有效胜率（排除1分对局）
                player_data['effective_win_rate'] = self.get_player_effective_win_rate(row['player_id'])
                
                players.append(player_data)
            
            return players
    
    # ===== 场次相关操作 =====
    
    def create_session(self, name: str) -> str:
        """创建新场次，返回session_id"""
        session_id = str(uuid.uuid4())
        current_time = get_utc_timestamp()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sessions (session_id, name, active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
            ''', (session_id, name, current_time, current_time))
            conn.commit()
        
        return session_id
    
    def get_session_by_id(self, session_id: str) -> Optional[Dict]:
        """获取场次基本信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def get_session_with_players(self, session_id: str) -> Optional[Dict]:
        """获取场次完整信息（包含玩家和分数）"""
        session = self.get_session_by_id(session_id)
        if not session:
            return None
        
        # 获取场次玩家和分数
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT sp.player_id, sp.score, p.name
                FROM session_players sp
                JOIN players p ON sp.player_id = p.player_id
                WHERE sp.session_id = ?
                ORDER BY sp.score DESC
            ''', (session_id,))
            players_data = cursor.fetchall()
        
        # 构建返回数据结构（兼容原有格式）
        session['players'] = []
        session['player_ids'] = []
        session['scores'] = {}
        session['players_with_ids'] = []
        # 添加兼容性时间字段
        session['timestamp'] = session.get('created_at')
        
        for player_data in players_data:
            session['players'].append(player_data['name'])
            session['player_ids'].append(player_data['player_id'])
            session['scores'][player_data['name']] = player_data['score']
            # 添加 players_with_ids 用于历史页面
            session['players_with_ids'].append({
                'name': player_data['name'],
                'id': player_data['player_id'],
                'score': player_data['score']
            })
        
        # 获取计分记录
        session['records'] = self.get_session_records(session_id)
        
        return session
    
    def get_active_sessions(self) -> List[Dict]:
        """获取所有活跃场次"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM sessions WHERE active = 1 
                ORDER BY created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_ended_sessions(self, limit: int = 3) -> List[Dict]:
        """获取最近结束的场次"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM sessions WHERE active = 0 
                ORDER BY end_time DESC, updated_at DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_sessions(self) -> List[Dict]:
        """获取所有场次"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions ORDER BY created_at DESC')
            return [dict(row) for row in cursor.fetchall()]
    
    def end_session(self, session_id: str) -> bool:
        """结束场次"""
        current_time = get_utc_timestamp()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE sessions SET active = 0, end_time = ?, updated_at = ?
                WHERE session_id = ?
            ''', (current_time, current_time, session_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_session(self, session_id: str) -> bool:
        """删除场次及相关数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 删除相关记录（外键约束会自动处理）
            cursor.execute('DELETE FROM game_records WHERE session_id = ?', (session_id,))
            cursor.execute('DELETE FROM session_players WHERE session_id = ?', (session_id,))
            cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    # ===== 玩家-场次关联操作 =====
    
    def add_player_to_session(self, session_id: str, player_id: str, initial_score: int = 0) -> bool:
        """将玩家添加到场次"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO session_players (session_id, player_id, score)
                    VALUES (?, ?, ?)
                ''', (session_id, player_id, initial_score))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # 玩家已在场次中
                return False
    
    def update_player_score(self, session_id: str, player_id: str, score_change: int) -> bool:
        """更新玩家分数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE session_players 
                SET score = score + ?
                WHERE session_id = ? AND player_id = ?
            ''', (score_change, session_id, player_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_session_players(self, session_id: str) -> List[Dict]:
        """获取场次中的所有玩家及分数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT sp.player_id, sp.score, p.name
                FROM session_players sp
                JOIN players p ON sp.player_id = p.player_id
                WHERE sp.session_id = ?
                ORDER BY sp.score DESC
            ''', (session_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ===== 计分记录操作 =====
    
    def add_game_record(self, session_id: str, winner_id: str, loser_id: str, 
                       score: int, special_score_part: str = None) -> int:
        """添加计分记录，返回record_id"""
        current_time = get_utc_timestamp()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO game_records 
                (session_id, winner_id, loser_id, score, created_at, special_score_part)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, winner_id, loser_id, score, current_time, special_score_part))
            
            record_id = cursor.lastrowid
            
            # 同时更新玩家分数
            cursor.execute('''
                UPDATE session_players SET score = score + ? 
                WHERE session_id = ? AND player_id = ?
            ''', (score, session_id, winner_id))
            
            cursor.execute('''
                UPDATE session_players SET score = score - ? 
                WHERE session_id = ? AND player_id = ?
            ''', (score, session_id, loser_id))
            
            conn.commit()
            return record_id
    
    def get_session_records(self, session_id: str) -> List[Dict]:
        """获取场次的所有计分记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT gr.*, 
                       pw.name as winner_name, 
                       pl.name as loser_name
                FROM game_records gr
                JOIN players pw ON gr.winner_id = pw.player_id
                JOIN players pl ON gr.loser_id = pl.player_id
                WHERE gr.session_id = ?
                ORDER BY gr.record_id
            ''', (session_id,))
            
            records = []
            for row in cursor.fetchall():
                record = dict(row)
                # 保持兼容性，添加原有字段名
                record['winner'] = record['winner_name']
                record['loser'] = record['loser_name']
                record['timestamp'] = record['created_at']
                records.append(record)
            
            return records
    
    def delete_game_record(self, record_id: int) -> Optional[Dict]:
        """删除计分记录，返回被删除的记录信息用于恢复分数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 先获取记录信息
            cursor.execute('SELECT * FROM game_records WHERE record_id = ?', (record_id,))
            record = cursor.fetchone()
            if not record:
                return None
            
            record_dict = dict(record)
            
            # 恢复分数
            cursor.execute('''
                UPDATE session_players SET score = score - ? 
                WHERE session_id = ? AND player_id = ?
            ''', (record_dict['score'], record_dict['session_id'], record_dict['winner_id']))
            
            cursor.execute('''
                UPDATE session_players SET score = score + ? 
                WHERE session_id = ? AND player_id = ?
            ''', (record_dict['score'], record_dict['session_id'], record_dict['loser_id']))
            
            # 删除记录
            cursor.execute('DELETE FROM game_records WHERE record_id = ?', (record_id,))
            
            conn.commit()
            return record_dict
    
    def get_player_records(self, player_id: str) -> List[Dict]:
        """获取玩家的所有对战记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT gr.*, s.name as session_name,
                       pw.name as winner_name, 
                       pl.name as loser_name
                FROM game_records gr
                JOIN sessions s ON gr.session_id = s.session_id
                JOIN players pw ON gr.winner_id = pw.player_id
                JOIN players pl ON gr.loser_id = pl.player_id
                WHERE gr.winner_id = ? OR gr.loser_id = ?
                ORDER BY gr.created_at DESC
            ''', (player_id, player_id))
            
            records = []
            for row in cursor.fetchall():
                record = dict(row)
                # 添加额外信息便于统计
                record['is_winner'] = (record['winner_id'] == player_id)
                record['opponent_id'] = record['loser_id'] if record['is_winner'] else record['winner_id']
                record['opponent_name'] = record['loser_name'] if record['is_winner'] else record['winner_name']
                record['timestamp'] = record['created_at']
                records.append(record)
            
            return records
    
    # ===== 统计查询 =====
    
    def get_player_stats(self, player_id: str) -> Dict:
        """获取玩家统计数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取基本统计
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_games,
                    SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN loser_id = ? THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN winner_id = ? THEN score ELSE -score END) as total_score
                FROM game_records
                WHERE winner_id = ? OR loser_id = ?
            ''', (player_id, player_id, player_id, player_id, player_id))
            
            result = cursor.fetchone()
            
            return {
                'total_games': result['total_games'] or 0,
                'wins': result['wins'] or 0,
                'losses': result['losses'] or 0,
                'total_score': result['total_score'] or 0
            }
    
    def get_global_leaderboard(self) -> List[Dict]:
        """获取全局排行榜"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    p.player_id, p.name,
                    COUNT(*) as total_games,
                    SUM(CASE WHEN gr.winner_id = p.player_id THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN gr.loser_id = p.player_id THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN gr.winner_id = p.player_id THEN gr.score ELSE -gr.score END) as total_score
                FROM players p
                JOIN game_records gr ON (gr.winner_id = p.player_id OR gr.loser_id = p.player_id)
                GROUP BY p.player_id, p.name
                ORDER BY total_score DESC
            ''')
            
            leaderboard = []
            for row in cursor.fetchall():
                stats = dict(row)
                stats['win_rate'] = (stats['wins'] / stats['total_games'] * 100) if stats['total_games'] > 0 else 0
                # 为兼容性添加 score 字段（与 total_score 相同）
                stats['score'] = stats['total_score']
                # 为兼容性添加 id 字段（与 player_id 相同）
                stats['id'] = stats['player_id']
                leaderboard.append(stats)
            
            return leaderboard
    
    def get_player_effective_win_rate(self, player_id: str) -> Optional[float]:
        """计算玩家的有效胜率（排除1分的对局）"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_effective_games,
                    SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) as effective_wins
                FROM game_records
                WHERE (winner_id = ? OR loser_id = ?) AND score > 1
            ''', (player_id, player_id, player_id))
            
            result = cursor.fetchone()
            total_games = result['total_effective_games'] or 0
            wins = result['effective_wins'] or 0
            
            if total_games > 0:
                return round((wins / total_games) * 100, 1)
            else:
                return None  # 没有有效对局
    
    # ===== 数据迁移工具 =====
    
    def migrate_from_json(self, json_data: Dict):
        """从JSON数据迁移到数据库"""
        print("开始从JSON数据迁移到数据库...")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 迁移玩家数据
            if 'players' in json_data:
                for player_id, player_data in json_data['players'].items():
                    cursor.execute('''
                        INSERT OR REPLACE INTO players (player_id, name, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                    ''', (player_id, player_data['name'], 
                          player_data['created_at'], player_data['updated_at']))
                
                print(f"迁移了 {len(json_data['players'])} 个玩家")
            
            # 迁移场次数据
            if 'sessions' in json_data:
                for session_id, session_data in json_data['sessions'].items():
                    # 插入场次基本信息
                    cursor.execute('''
                        INSERT OR REPLACE INTO sessions 
                        (session_id, name, active, created_at, updated_at, end_time)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (session_id, session_data['name'], 
                          1 if session_data.get('active', True) else 0,
                          session_data['timestamp'], session_data['timestamp'],
                          session_data.get('end_time')))
                    
                    # 先创建所有参与玩家的记录（初始分数为0）
                    if 'player_ids' in session_data:
                        for player_id in session_data['player_ids']:
                            cursor.execute('''
                                INSERT OR REPLACE INTO session_players 
                                (session_id, player_id, score)
                                VALUES (?, ?, 0)
                            ''', (session_id, player_id))
                    
                    # 如果没有 player_ids 但有 players，则通过名字查找并创建记录
                    elif 'players' in session_data:
                        for player_name in session_data['players']:
                            player_id = self.get_player_by_name(player_name)
                            if player_id:
                                cursor.execute('''
                                    INSERT OR REPLACE INTO session_players 
                                    (session_id, player_id, score)
                                    VALUES (?, ?, 0)
                                ''', (session_id, player_id))
                    
                    # 迁移计分记录并同时更新分数
                    if 'records' in session_data:
                        for record in session_data['records']:
                            # 插入记录
                            cursor.execute('''
                                INSERT INTO game_records 
                                (session_id, winner_id, loser_id, score, created_at, special_score_part)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (session_id, record.get('winner_id'), record.get('loser_id'),
                                  record['score'], record['timestamp'], 
                                  record.get('special_score_part')))
                            
                            # 更新胜者分数 (+score)
                            cursor.execute('''
                                UPDATE session_players 
                                SET score = score + ? 
                                WHERE session_id = ? AND player_id = ?
                            ''', (record['score'], session_id, record.get('winner_id')))
                            
                            # 更新败者分数 (-score)
                            cursor.execute('''
                                UPDATE session_players 
                                SET score = score - ? 
                                WHERE session_id = ? AND player_id = ?
                            ''', (record['score'], session_id, record.get('loser_id')))
                
                print(f"迁移了 {len(json_data['sessions'])} 个场次")
            
            conn.commit()
            print("JSON数据迁移完成！")


# 全局数据库实例
db = DatabaseManager()
