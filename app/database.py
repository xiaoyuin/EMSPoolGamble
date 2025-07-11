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

        # 检查并执行数据库升级
        self.upgrade_to_multi_loser_support()

    def upgrade_to_multi_loser_support(self):
        """升级数据库以支持多败者记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 检查是否已经有 loser_id2 列
            cursor.execute("PRAGMA table_info(game_records)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'loser_id2' in columns and 'special_score' in columns:
                print("数据库已支持多败者记录")
                return

            print("开始升级数据库以支持多败者记录...")

            # 添加新列
            if 'loser_id2' not in columns:
                cursor.execute('ALTER TABLE game_records ADD COLUMN loser_id2 TEXT')
                print("添加了 loser_id2 列")

            if 'special_score' not in columns:
                cursor.execute('ALTER TABLE game_records ADD COLUMN special_score TEXT')
                print("添加了 special_score 列")

            # 如果有 special_score_part 列，进行数据迁移
            if 'special_score_part' in columns:
                print("开始迁移数据...")

                # 获取所有记录
                cursor.execute('''
                    SELECT record_id, session_id, winner_id, loser_id, score,
                           created_at, special_score_part
                    FROM game_records
                    ORDER BY session_id, created_at
                ''')
                all_records = cursor.fetchall()

                # 分析并合并记录
                records_to_delete = []
                records_to_update = []

                i = 0
                while i < len(all_records):
                    record = all_records[i]
                    special_part = record[6]  # special_score_part

                    # 检查是否是特殊分数的第一条记录
                    if special_part and '1/2 (总分' in special_part:
                        # 提取总分数
                        total_score = int(special_part.split('总分')[1].split(')')[0])

                        # 寻找对应的第二条记录
                        if i + 1 < len(all_records):
                            next_record = all_records[i + 1]
                            next_special_part = next_record[6]

                            if (next_special_part and
                                f'2/2 (总分{total_score})' in next_special_part and
                                next_record[1] == record[1] and  # 同一场次
                                next_record[2] == record[2]):    # 同一胜者

                                # 合并两条记录为一条
                                special_score = "大金" if total_score == 20 else "双吃"

                                records_to_update.append({
                                    'record_id': record[0],
                                    'loser_id2': next_record[3],  # 第二个败者
                                    'total_score': total_score,
                                    'special_score': special_score
                                })

                                # 标记第二条记录待删除
                                records_to_delete.append(next_record[0])

                                i += 2  # 跳过下一条记录
                                continue

                    # 处理普通记录
                    special_score = None
                    if record[4] >= 7:  # score >= 7
                        special_score = "小金"

                    records_to_update.append({
                        'record_id': record[0],
                        'loser_id2': None,
                        'total_score': record[4],
                        'special_score': special_score
                    })

                    i += 1

                # 执行更新
                for update in records_to_update:
                    cursor.execute('''
                        UPDATE game_records
                        SET loser_id2 = ?, score = ?, special_score = ?
                        WHERE record_id = ?
                    ''', (update['loser_id2'], update['total_score'],
                          update['special_score'], update['record_id']))

                # 删除重复记录
                for record_id in records_to_delete:
                    cursor.execute('DELETE FROM game_records WHERE record_id = ?', (record_id,))

                print(f"更新了 {len(records_to_update)} 条记录")
                print(f"删除了 {len(records_to_delete)} 条重复记录")

                # 删除旧列
                cursor.execute('''
                    CREATE TABLE game_records_new (
                        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        winner_id TEXT NOT NULL,
                        loser_id TEXT NOT NULL,
                        loser_id2 TEXT,
                        score INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        special_score TEXT,
                        FOREIGN KEY (session_id) REFERENCES sessions (session_id),
                        FOREIGN KEY (winner_id) REFERENCES players (player_id),
                        FOREIGN KEY (loser_id) REFERENCES players (player_id),
                        FOREIGN KEY (loser_id2) REFERENCES players (player_id)
                    )
                ''')

                cursor.execute('''
                    INSERT INTO game_records_new
                    (record_id, session_id, winner_id, loser_id, loser_id2, score, created_at, special_score)
                    SELECT record_id, session_id, winner_id, loser_id, loser_id2, score, created_at, special_score
                    FROM game_records
                ''')

                cursor.execute('DROP TABLE game_records')
                cursor.execute('ALTER TABLE game_records_new RENAME TO game_records')

                # 重建索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_game_records_session ON game_records (session_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_game_records_players ON game_records (winner_id, loser_id)')

            conn.commit()
            print("数据库升级完成！")

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
                       score: int, special_score: str = None, loser_id2: str = None) -> int:
        """添加计分记录，返回record_id

        Args:
            session_id: 场次ID
            winner_id: 赢家ID
            loser_id: 第一个败者ID
            score: 分数
            special_score: 特殊分数标签（由UI层传入，如"大金"、"小金"等）
            loser_id2: 第二个败者ID（可选）
        """
        current_time = get_utc_timestamp()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 检查表结构是否支持新字段
            cursor.execute("PRAGMA table_info(game_records)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'loser_id2' in columns and 'special_score' in columns:
                # 使用新表结构
                cursor.execute('''
                    INSERT INTO game_records
                    (session_id, winner_id, loser_id, loser_id2, score, created_at, special_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (session_id, winner_id, loser_id, loser_id2, score, current_time, special_score))
            else:
                # 使用旧表结构（兼容性），将special_score存入special_score_part字段
                cursor.execute('''
                    INSERT INTO game_records
                    (session_id, winner_id, loser_id, score, created_at, special_score_part)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (session_id, winner_id, loser_id, score, current_time, special_score))

            record_id = cursor.lastrowid

            # 更新玩家分数
            cursor.execute('''
                UPDATE session_players SET score = score + ?
                WHERE session_id = ? AND player_id = ?
            ''', (score, session_id, winner_id))

            # 如果有第二个败者，每个败者承担一半分数
            if loser_id2:
                score_per_loser = score // 2
                cursor.execute('''
                    UPDATE session_players SET score = score - ?
                    WHERE session_id = ? AND player_id = ?
                ''', (score_per_loser, session_id, loser_id))

                cursor.execute('''
                    UPDATE session_players SET score = score - ?
                    WHERE session_id = ? AND player_id = ?
                ''', (score_per_loser, session_id, loser_id2))
            else:
                # 单个败者承担全部分数
                cursor.execute('''
                    UPDATE session_players SET score = score - ?
                    WHERE session_id = ? AND player_id = ?
                ''', (score, session_id, loser_id))

            conn.commit()
            return record_id

    def get_session_records(self, session_id: str) -> List[Dict]:
        """获取场次的所有计分记录（按时间降序，最新记录在前）"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT gr.*,
                       pw.name as winner_name,
                       pl1.name as loser_name,
                       pl2.name as loser2_name
                FROM game_records gr
                JOIN players pw ON gr.winner_id = pw.player_id
                JOIN players pl1 ON gr.loser_id = pl1.player_id
                LEFT JOIN players pl2 ON gr.loser_id2 = pl2.player_id
                WHERE gr.session_id = ?
                ORDER BY gr.record_id DESC
            ''', (session_id,))

            records = []
            for row in cursor.fetchall():
                record = dict(row)
                # 保持兼容性，添加原有字段名
                record['winner'] = record['winner_name']
                record['loser'] = record['loser_name']
                record['timestamp'] = record['created_at']

                # 构建败者显示文本和ID信息
                if record['loser2_name']:
                    # 有两个败者的情况
                    record['loser_display'] = f"{record['loser_name']} + {record['loser2_name']}"
                    record['is_multi_loser'] = True
                    # 为模板提供败者信息列表
                    record['losers'] = [
                        {'id': record['loser_id'], 'name': record['loser_name']},
                        {'id': record['loser_id2'], 'name': record['loser2_name']}
                    ]
                else:
                    # 单个败者的情况
                    record['loser_display'] = record['loser_name']
                    record['is_multi_loser'] = False
                    record['losers'] = [
                        {'id': record['loser_id'], 'name': record['loser_name']}
                    ]

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

            # 如果有第二个败者，需要正确恢复每个败者的分数
            if record_dict.get('loser_id2'):
                score_per_loser = record_dict['score'] // 2
                cursor.execute('''
                    UPDATE session_players SET score = score + ?
                    WHERE session_id = ? AND player_id = ?
                ''', (score_per_loser, record_dict['session_id'], record_dict['loser_id']))

                cursor.execute('''
                    UPDATE session_players SET score = score + ?
                    WHERE session_id = ? AND player_id = ?
                ''', (score_per_loser, record_dict['session_id'], record_dict['loser_id2']))
            else:
                # 单个败者恢复全部分数
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
                       pl1.name as loser1_name,
                       pl2.name as loser2_name
                FROM game_records gr
                JOIN sessions s ON gr.session_id = s.session_id
                JOIN players pw ON gr.winner_id = pw.player_id
                JOIN players pl1 ON gr.loser_id = pl1.player_id
                LEFT JOIN players pl2 ON gr.loser_id2 = pl2.player_id
                WHERE gr.winner_id = ? OR gr.loser_id = ? OR gr.loser_id2 = ?
                ORDER BY gr.created_at DESC
            ''', (player_id, player_id, player_id))

            records = []
            for row in cursor.fetchall():
                record = dict(row)

                # 判断当前玩家在这场比赛中的角色
                if record['winner_id'] == player_id:
                    # 当前玩家是赢家
                    record['is_winner'] = True
                    record['score'] = record['score']  # 赢家得全部分数

                    # 构建对手信息
                    opponents = [record['loser1_name']]
                    opponent_ids = [record['loser_id']]
                    if record['loser2_name']:
                        opponents.append(record['loser2_name'])
                        opponent_ids.append(record['loser_id2'])

                    record['opponent_name'] = ' + '.join(opponents)
                    record['opponent_id'] = opponent_ids[0] if len(opponent_ids) == 1 else opponent_ids

                    # 为模板添加结构化的对手信息
                    if len(opponent_ids) > 1:
                        record['opponent_names'] = [
                            {'id': opponent_ids[0], 'name': opponents[0]},
                            {'id': opponent_ids[1], 'name': opponents[1]}
                        ]
                    else:
                        record['opponent_names'] = None

                else:
                    # 当前玩家是败者
                    record['is_winner'] = False

                    # 如果有两个败者，当前玩家只承担一半分数
                    if record['loser_id2']:
                        record['score'] = record['score'] // 2
                    else:
                        record['score'] = record['score']

                    record['opponent_name'] = record['winner_name']
                    record['opponent_id'] = record['winner_id']
                    record['opponent_names'] = None  # 败者通常只有一个对手

                # 添加兼容性字段
                record['timestamp'] = record['created_at']
                records.append(record)

            return records

    # ===== 统计查询 =====

    def get_player_stats(self, player_id: str) -> Dict:
        """获取玩家统计数据（正确处理多败者记录）"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 获取所有相关记录
            cursor.execute('''
                SELECT winner_id, loser_id, loser_id2, score
                FROM game_records
                WHERE winner_id = ? OR loser_id = ? OR loser_id2 = ?
            ''', (player_id, player_id, player_id))

            total_games = 0
            wins = 0
            losses = 0
            total_score = 0

            for record in cursor.fetchall():
                if record['winner_id'] == player_id:
                    # 玩家是赢家
                    wins += 1
                    total_games += 1
                    total_score += record['score']
                elif record['loser_id'] == player_id or record['loser_id2'] == player_id:
                    # 玩家是败者
                    losses += 1
                    total_games += 1

                    # 如果有两个败者，只承担一半分数
                    if record['loser_id2']:
                        total_score -= record['score'] // 2
                    else:
                        total_score -= record['score']

            return {
                'total_games': total_games,
                'wins': wins,
                'losses': losses,
                'total_score': total_score
            }

    def get_global_leaderboard(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """获取全局排行榜（正确处理多败者记录，使用有效胜率）

        Args:
            start_date: 开始日期 (YYYY-MM-DD)，None表示不限制
            end_date: 结束日期 (YYYY-MM-DD)，None表示不限制
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 获取所有玩家
            cursor.execute('SELECT player_id, name FROM players')
            players = cursor.fetchall()

            leaderboard = []
            for player in players:
                player_id = player['player_id']
                player_name = player['name']

                # 构建查询条件
                date_filter = ""
                params = [player_id, player_id, player_id]

                if start_date and end_date:
                    date_filter = "AND DATE(gr.created_at) >= ? AND DATE(gr.created_at) <= ?"
                    params.extend([start_date, end_date])
                elif start_date:
                    date_filter = "AND DATE(gr.created_at) >= ?"
                    params.append(start_date)
                elif end_date:
                    date_filter = "AND DATE(gr.created_at) <= ?"
                    params.append(end_date)

                # 获取玩家的相关记录（支持日期过滤）
                cursor.execute(f'''
                    SELECT winner_id, loser_id, loser_id2, score
                    FROM game_records gr
                    WHERE (winner_id = ? OR loser_id = ? OR loser_id2 = ?) {date_filter}
                ''', params)

                total_games = 0
                wins = 0
                losses = 0
                total_score = 0
                effective_games = 0
                effective_wins = 0

                for record in cursor.fetchall():
                    if record['winner_id'] == player_id:
                        # 玩家是赢家
                        wins += 1
                        total_games += 1
                        total_score += record['score']

                        # 有效对局（分数 > 1）
                        if record['score'] > 1:
                            effective_games += 1
                            effective_wins += 1

                    elif record['loser_id'] == player_id or record['loser_id2'] == player_id:
                        # 玩家是败者
                        losses += 1
                        total_games += 1

                        # 如果有两个败者，只承担一半分数
                        if record['loser_id2']:
                            total_score -= record['score'] // 2
                        else:
                            total_score -= record['score']

                        # 有效对局（分数 > 1）
                        if record['score'] > 1:
                            effective_games += 1

                # 只包含有游戏记录的玩家
                if total_games > 0:
                    # 计算有效胜率（排除1分局）
                    effective_win_rate = (effective_wins / effective_games * 100) if effective_games > 0 else 0

                    stats = {
                        'player_id': player_id,
                        'name': player_name,
                        'total_games': total_games,
                        'wins': wins,
                        'losses': losses,
                        'total_score': total_score,
                        'win_rate': effective_win_rate,  # 使用有效胜率
                        'effective_games': effective_games,
                        'effective_wins': effective_wins,
                        # 为兼容性添加字段
                        'score': total_score,
                        'id': player_id
                    }
                    leaderboard.append(stats)

            # 按总分排序
            leaderboard.sort(key=lambda x: x['total_score'], reverse=True)
            return leaderboard

    def get_available_months(self) -> List[Dict]:
        """获取有场次记录的月份列表，统计每月的场次数量"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    strftime('%Y-%m', created_at) as month_key,
                    CAST(strftime('%Y', created_at) AS INTEGER) as year,
                    CAST(strftime('%m', created_at) AS INTEGER) as month,
                    COUNT(DISTINCT session_id) as session_count
                FROM sessions
                GROUP BY strftime('%Y-%m', created_at)
                ORDER BY month_key DESC
            ''')

            months = []
            for row in cursor.fetchall():
                # 格式化月份名称为 "XXXX年X月"（去掉前导零）
                month_name = f"{row['year']}年{row['month']}月"
                months.append({
                    'key': row['month_key'],
                    'name': month_name,
                    'count': row['session_count']
                })

            return months

    def get_player_effective_win_rate(self, player_id: str) -> Optional[float]:
        """计算玩家的有效胜率（排除1分的对局，正确处理多败者）"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    COUNT(*) as total_effective_games,
                    SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) as effective_wins
                FROM game_records
                WHERE (winner_id = ? OR loser_id = ? OR loser_id2 = ?) AND score > 1
            ''', (player_id, player_id, player_id, player_id))

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

    def get_player_special_wins(self, player_id: str) -> Dict[str, bool]:
        """获取玩家的特殊胜利记录（小金、大金）"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 查询玩家赢过的特殊分数记录
            cursor.execute('''
                SELECT DISTINCT special_score
                FROM game_records
                WHERE winner_id = ? AND special_score IS NOT NULL
            ''', (player_id,))

            special_wins = cursor.fetchall()

            # 构建结果字典
            result = {
                'has_small_gold': False,
                'has_big_gold': False
            }

            for win in special_wins:
                special_score = win['special_score']
                if special_score == '小金':
                    result['has_small_gold'] = True
                elif special_score == '大金':
                    result['has_big_gold'] = True

            return result

    def get_players_special_wins_batch(self, player_ids: List[str]) -> Dict[str, Dict[str, bool]]:
        """批量获取多个玩家的特殊胜利记录"""
        if not player_ids:
            return {}

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 构建IN查询的占位符
            placeholders = ','.join(['?'] * len(player_ids))

            # 查询所有玩家的特殊胜利记录
            cursor.execute(f'''
                SELECT winner_id, special_score
                FROM game_records
                WHERE winner_id IN ({placeholders}) AND special_score IS NOT NULL
            ''', player_ids)

            special_wins = cursor.fetchall()

            # 初始化所有玩家的结果
            result = {}
            for player_id in player_ids:
                result[player_id] = {
                    'has_small_gold': False,
                    'has_big_gold': False
                }

            # 填充特殊胜利记录
            for win in special_wins:
                player_id = win['winner_id']
                special_score = win['special_score']

                if special_score == '小金':
                    result[player_id]['has_small_gold'] = True
                elif special_score == '大金':
                    result[player_id]['has_big_gold'] = True

            return result

    def get_achievement_players(self, achievement_type: str) -> List[Dict]:
        """获取达成指定成就的玩家列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 根据成就类型确定查询条件
            if achievement_type == 'small_gold':
                special_score = '小金'
            elif achievement_type == 'big_gold':
                special_score = '大金'
            else:
                return []

            # 查询达成该成就的玩家及其首次和总次数
            cursor.execute('''
                SELECT
                    p.player_id,
                    p.name,
                    COUNT(gr.record_id) as achievement_count,
                    MIN(gr.created_at) as first_achievement_date,
                    MAX(gr.created_at) as latest_achievement_date
                FROM players p
                INNER JOIN game_records gr ON p.player_id = gr.winner_id
                WHERE gr.special_score = ?
                GROUP BY p.player_id, p.name
                ORDER BY achievement_count DESC, first_achievement_date ASC
            ''', (special_score,))

            players = cursor.fetchall()

            return [dict(player) for player in players]

    def get_achievement_records(self, achievement_type: str, player_id: str = None) -> List[Dict]:
        """获取成就达成记录详情"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 根据成就类型确定查询条件
            if achievement_type == 'small_gold':
                special_score = '小金'
            elif achievement_type == 'big_gold':
                special_score = '大金'
            else:
                return []

            # 构建查询
            base_query = '''
                SELECT
                    gr.record_id,
                    gr.session_id,
                    gr.created_at,
                    gr.score,
                    winner.name as winner_name,
                    loser.name as loser_name,
                    s.name as session_name
                FROM game_records gr
                INNER JOIN players winner ON gr.winner_id = winner.player_id
                INNER JOIN players loser ON gr.loser_id = loser.player_id
                INNER JOIN sessions s ON gr.session_id = s.session_id
                WHERE gr.special_score = ?
            '''

            params = [special_score]

            if player_id:
                base_query += ' AND gr.winner_id = ?'
                params.append(player_id)

            base_query += ' ORDER BY gr.created_at DESC'

            cursor.execute(base_query, params)
            records = cursor.fetchall()

            return [dict(record) for record in records]

    def get_achievement_stats(self) -> Dict:
        """获取成就系统统计信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            # 小金玩家统计
            cursor.execute('''
                SELECT COUNT(DISTINCT winner_id) as player_count
                FROM game_records
                WHERE special_score = '小金'
            ''')
            stats['small_gold_players'] = cursor.fetchone()['player_count']

            # 大金玩家统计
            cursor.execute('''
                SELECT COUNT(DISTINCT winner_id) as player_count
                FROM game_records
                WHERE special_score = '大金'
            ''')
            stats['big_gold_players'] = cursor.fetchone()['player_count']

            # 小金达人统计（小金次数 >= 10）
            cursor.execute('''
                SELECT COUNT(*) as player_count
                FROM (
                    SELECT winner_id, COUNT(*) as achievement_count
                    FROM game_records
                    WHERE special_score = '小金'
                    GROUP BY winner_id
                    HAVING COUNT(*) >= 10
                ) as small_gold_masters
            ''')
            stats['small_gold_masters'] = cursor.fetchone()['player_count']

            # 大金达人统计（大金次数 >= 5）
            cursor.execute('''
                SELECT COUNT(*) as player_count
                FROM (
                    SELECT winner_id, COUNT(*) as achievement_count
                    FROM game_records
                    WHERE special_score = '大金'
                    GROUP BY winner_id
                    HAVING COUNT(*) >= 5
                ) as big_gold_masters
            ''')
            stats['big_gold_masters'] = cursor.fetchone()['player_count']

            return stats

    def get_achievement_master_players(self, achievement_type: str) -> List[Dict]:
        """获取达人成就的玩家列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if achievement_type == 'small_gold_master':
                special_score = '小金'
                min_count = 10
            elif achievement_type == 'big_gold_master':
                special_score = '大金'
                min_count = 5
            else:
                return []

            # 查询达成达人成就的玩家
            cursor.execute('''
                SELECT
                    p.player_id,
                    p.name,
                    COUNT(gr.record_id) as achievement_count,
                    MIN(gr.created_at) as first_achievement_date,
                    MAX(gr.created_at) as latest_achievement_date
                FROM players p
                INNER JOIN game_records gr ON p.player_id = gr.winner_id
                WHERE gr.special_score = ?
                GROUP BY p.player_id, p.name
                HAVING COUNT(gr.record_id) >= ?
                ORDER BY achievement_count DESC, first_achievement_date ASC
            ''', (special_score, min_count))

            players = cursor.fetchall()

            return [dict(player) for player in players]

# 全局数据库实例
db = DatabaseManager()
