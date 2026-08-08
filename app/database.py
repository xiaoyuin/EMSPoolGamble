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
from flask import current_app, has_app_context
from .utils import get_utc_timestamp
from .tenancy import (
    EMS_ORG_ID,
    generate_organization_slug,
    initialize_database,
    normalize_name,
    validate_organization_name,
)


class DatabaseManager:
    """数据库管理类，提供所有数据操作接口"""

    def __init__(self, db_path: str = None):
        """初始化数据库连接"""
        if db_path is None:
            db_path = os.environ.get('DATABASE_PATH')
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
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA busy_timeout = 5000')
        conn.row_factory = sqlite3.Row  # 使结果可以像字典一样访问
        try:
            yield conn
        finally:
            conn.close()

    def init_database(self):
        """初始化目标租户结构，或原子升级旧版单组织数据库。"""
        initialize_database(self.db_path)
        print(f"数据库初始化完成: {self.db_path}")

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

    def upgrade_to_multi_winner_support(self):
        """升级数据库以支持多赢家记录（反向双吃：1输2赢）"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(game_records)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'winner_id2' in columns:
                return

            print("开始升级数据库以支持多赢家记录...")
            cursor.execute('ALTER TABLE game_records ADD COLUMN winner_id2 TEXT')
            conn.commit()
            print("添加了 winner_id2 列")

    def _upgrade_player_retirement(self):
        """升级 players 表以支持退役状态"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(players)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'is_retired' in columns:
                return
            print("添加 is_retired 列...")
            cursor.execute('ALTER TABLE players ADD COLUMN is_retired INTEGER DEFAULT 0')
            conn.commit()
            print("添加了 is_retired 列")

    def _migrate_round_names(self):
        """将旧版轮次名 '1/8 决赛' → '16进8'，'1/4 决赛' → '8进4'。"""
        renames = {
            '1/8 决赛': '16进8',
            '1/4 决赛': '8进4',
        }
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for old, new in renames.items():
                cursor.execute(
                    'UPDATE tournament_rounds SET round_name = ? WHERE round_name = ?',
                    (new, old))
                if cursor.rowcount > 0:
                    print(f'轮次名迁移："{old}" → "{new}"（{cursor.rowcount} 条）')
            conn.commit()

    def _migrate_match_video_columns(self):
        """tournament_matches 加 video_url 列（v1.9.3，存 B 站等视频链接）。"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(tournament_matches)")
            columns = {row[1] for row in cursor.fetchall()}
            if 'video_url' not in columns:
                cursor.execute('ALTER TABLE tournament_matches ADD COLUMN video_url TEXT')
                print('tournament_matches 加列：video_url')
            conn.commit()

    # ===== 组织相关操作 =====

    def get_organization_by_id(self, org_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM organizations WHERE org_id = ?', (org_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_organization_by_slug(self, slug: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM organizations WHERE slug = ?',
                ((slug or '').strip().lower(),),
            ).fetchone()
            return dict(row) if row else None

    def get_organization_by_name_or_slug(self, value: str) -> Optional[Dict]:
        lookup = normalize_name(value)
        if not lookup:
            return None
        with self.get_connection() as conn:
            row = conn.execute(
                '''SELECT * FROM organizations
                   WHERE slug = ? OR name_key = ?''',
                (lookup, lookup),
            ).fetchone()
            return dict(row) if row else None

    def organization_slug_exists(self, slug: str) -> bool:
        return self.get_organization_by_slug(slug) is not None

    def create_organization(self, name: str, admin_password_hash: str) -> Dict:
        """创建组织；调用方必须提供已哈希的非空管理员密码。"""
        if not isinstance(admin_password_hash, str) or not admin_password_hash:
            raise ValueError('非 EMS 组织必须设置管理员密码哈希')
        display_name = validate_organization_name(name)
        name_key = normalize_name(display_name)
        current_time = get_utc_timestamp()
        org_id = str(uuid.uuid4())

        for _ in range(5):
            slug = generate_organization_slug(
                display_name, self.organization_slug_exists
            )
            try:
                with self.get_connection() as conn:
                    conn.execute(
                        '''INSERT INTO organizations
                           (org_id, slug, name, name_key, admin_password_hash,
                            created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        (
                            org_id, slug, display_name, name_key,
                            admin_password_hash, current_time, current_time,
                        ),
                    )
                    conn.commit()
                return self.get_organization_by_id(org_id)
            except sqlite3.IntegrityError as exc:
                if self.get_organization_by_name_or_slug(display_name):
                    raise ValueError('组织名称已存在') from exc
        raise RuntimeError('无法生成唯一的组织链接，请重试')

    def get_ems_organization(self) -> Dict:
        organization = self.get_organization_by_id(EMS_ORG_ID)
        if not organization:
            raise RuntimeError('EMS 组织未初始化')
        return organization

    # ===== 玩家相关操作 =====

    def create_player(self, org_id: str, name: str) -> str:
        player_id, now = str(uuid.uuid4()), get_utc_timestamp()
        with self.get_connection() as conn:
            conn.execute('''INSERT INTO players (player_id, org_id, name, name_key, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                         (player_id, org_id, name, normalize_name(name), now, now))
            conn.commit()
        return player_id

    def get_player_by_name(self, org_id: str, name: str) -> Optional[str]:
        with self.get_connection() as conn:
            row = conn.execute('SELECT player_id FROM players WHERE org_id = ? AND name_key = ?',
                               (org_id, normalize_name(name))).fetchone()
            return row['player_id'] if row else None

    def get_or_create_player(self, org_id: str, name: str) -> str:
        return self.get_player_by_name(org_id, name) or self.create_player(org_id, name)

    def get_player_by_id(self, org_id: str, player_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM players WHERE org_id = ? AND player_id = ?',
                               (org_id, player_id)).fetchone()
            return dict(row) if row else None

    def get_player_name(self, org_id: str, player_id: str) -> str:
        player = self.get_player_by_id(org_id, player_id)
        return player['name'] if player else 'Unknown Player'

    def update_player_name(self, org_id: str, player_id: str, new_name: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute('''UPDATE players SET name = ?, name_key = ?, updated_at = ?
                                     WHERE org_id = ? AND player_id = ?''',
                                  (new_name, normalize_name(new_name), get_utc_timestamp(), org_id, player_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_all_players(self, org_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            return [dict(row) for row in conn.execute(
                'SELECT * FROM players WHERE org_id = ? ORDER BY name', (org_id,)).fetchall()]

    def get_available_players(self, org_id: str, exclude_session_id: str = None) -> List[Dict]:
        with self.get_connection() as conn:
            sql = '''SELECT p.player_id, p.name FROM players p
                     WHERE p.org_id = ? AND (p.is_retired = 0 OR p.is_retired IS NULL)'''
            params = [org_id]
            if exclude_session_id:
                sql += ''' AND NOT EXISTS (SELECT 1 FROM session_players sp
                                            WHERE sp.org_id = p.org_id AND sp.session_id = ?
                                              AND sp.player_id = p.player_id)'''
                params.append(exclude_session_id)
            rows = conn.execute(sql + ' ORDER BY p.name', params).fetchall()
        return [{'id': row['player_id'], 'name': row['name'],
                 'effective_win_rate': self.get_player_effective_win_rate(org_id, row['player_id'])}
                for row in rows]

    # ===== 场次相关操作 =====

    def create_session(self, org_id: str, name: str) -> str:
        session_id, now = str(uuid.uuid4()), get_utc_timestamp()
        with self.get_connection() as conn:
            conn.execute('''INSERT INTO sessions (session_id, org_id, name, active, created_at, updated_at)
                            VALUES (?, ?, ?, 1, ?, ?)''', (session_id, org_id, name, now, now))
            conn.commit()
        return session_id

    def get_session_by_id(self, org_id: str, session_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM sessions WHERE org_id = ? AND session_id = ?',
                               (org_id, session_id)).fetchone()
            return dict(row) if row else None

    def get_session_with_players(self, org_id: str, session_id: str) -> Optional[Dict]:
        session = self.get_session_by_id(org_id, session_id)
        if not session:
            return None
        session.update(players=[], player_ids=[], scores={}, players_with_ids=[],
                       timestamp=session.get('created_at'))
        for player in self.get_session_players(org_id, session_id):
            session['players'].append(player['name'])
            session['player_ids'].append(player['player_id'])
            session['scores'][player['name']] = player['score']
            session['players_with_ids'].append({'name': player['name'], 'id': player['player_id'],
                                                'score': player['score']})
        session['records'] = self.get_session_records(org_id, session_id)
        return session

    def get_active_sessions(self, org_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute('''SELECT * FROM sessions WHERE org_id = ? AND active = 1
                                                     ORDER BY created_at DESC''', (org_id,)).fetchall()]

    def get_ended_sessions(self, org_id: str, limit: int = 3) -> List[Dict]:
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute('''SELECT * FROM sessions WHERE org_id = ? AND active = 0
                                                     ORDER BY end_time DESC, updated_at DESC LIMIT ?''',
                                                  (org_id, limit)).fetchall()]

    def get_all_sessions(self, org_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM sessions WHERE org_id = ? ORDER BY created_at DESC',
                                                  (org_id,)).fetchall()]

    def end_session(self, org_id: str, session_id: str) -> bool:
        now = get_utc_timestamp()
        with self.get_connection() as conn:
            cursor = conn.execute('''UPDATE sessions SET active = 0, end_time = ?, updated_at = ?
                                     WHERE org_id = ? AND session_id = ?''', (now, now, org_id, session_id))
            conn.commit()
            return cursor.rowcount > 0

    def delete_session(self, org_id: str, session_id: str) -> bool:
        with self.get_connection() as conn:
            if not conn.execute('SELECT 1 FROM sessions WHERE org_id = ? AND session_id = ?',
                                (org_id, session_id)).fetchone():
                return False
            for table in ('game_records', 'session_players', 'sessions'):
                conn.execute(f'DELETE FROM {table} WHERE org_id = ? AND session_id = ?', (org_id, session_id))
            conn.commit()
            return True

    # ===== 玩家-场次关联操作 =====

    def add_player_to_session(self, org_id: str, session_id: str, player_id: str,
                              initial_score: int = 0) -> bool:
        with self.get_connection() as conn:
            try:
                cursor = conn.execute('''INSERT INTO session_players (org_id, session_id, player_id, score)
                    SELECT ?, ?, ?, ?
                    WHERE EXISTS (SELECT 1 FROM sessions WHERE org_id = ? AND session_id = ?)
                      AND EXISTS (SELECT 1 FROM players WHERE org_id = ? AND player_id = ?)''',
                    (org_id, session_id, player_id, initial_score, org_id, session_id, org_id, player_id))
                conn.commit()
                return cursor.rowcount > 0
            except sqlite3.IntegrityError:
                return False

    def update_player_score(self, org_id: str, session_id: str, player_id: str, score_change: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute('''UPDATE session_players SET score = score + ?
                                     WHERE org_id = ? AND session_id = ? AND player_id = ?''',
                                  (score_change, org_id, session_id, player_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_session_players(self, org_id: str, session_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute('''SELECT sp.player_id, sp.score, p.name FROM session_players sp
                                   JOIN players p ON p.org_id = sp.org_id AND p.player_id = sp.player_id
                                   WHERE sp.org_id = ? AND sp.session_id = ? ORDER BY sp.score DESC''',
                                (org_id, session_id)).fetchall()
            return [dict(r) for r in rows]

    # ===== 计分记录操作 =====

    def add_game_record(self, org_id: str, session_id: str, winner_id: str, loser_id: str,
                        score: int, special_score: str = None, loser_id2: str = None,
                        winner_id2: str = None) -> Optional[int]:
        participant_ids = {winner_id, loser_id, *([loser_id2] if loser_id2 else []),
                           *([winner_id2] if winner_id2 else [])}
        placeholders = ','.join('?' * len(participant_ids))
        with self.get_connection() as conn:
            valid_session = conn.execute('SELECT 1 FROM sessions WHERE org_id = ? AND session_id = ?',
                                         (org_id, session_id)).fetchone()
            members = conn.execute(f'''SELECT player_id FROM session_players WHERE org_id = ?
                                        AND session_id = ? AND player_id IN ({placeholders})''',
                                   (org_id, session_id, *participant_ids)).fetchall()
            if not valid_session or {r['player_id'] for r in members} != participant_ids:
                return None
            cursor = conn.execute('''INSERT INTO game_records
                (org_id, session_id, winner_id, winner_id2, loser_id, loser_id2, score, created_at, special_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (org_id, session_id, winner_id, winner_id2, loser_id, loser_id2, score,
                 get_utc_timestamp(), special_score))
            if winner_id2:
                changes = ((winner_id, score // 2), (winner_id2, score // 2), (loser_id, -score))
            elif loser_id2:
                changes = ((winner_id, score), (loser_id, -(score // 2)), (loser_id2, -(score // 2)))
            else:
                changes = ((winner_id, score), (loser_id, -score))
            for player_id, change in changes:
                conn.execute('''UPDATE session_players SET score = score + ?
                                WHERE org_id = ? AND session_id = ? AND player_id = ?''',
                             (change, org_id, session_id, player_id))
            conn.commit()
            return cursor.lastrowid

    def get_session_records(self, org_id: str, session_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute('''SELECT gr.*, pw.name AS winner_name, pw2.name AS winner2_name,
                                          pl1.name AS loser_name, pl2.name AS loser2_name
                FROM game_records gr
                JOIN players pw ON pw.org_id = gr.org_id AND pw.player_id = gr.winner_id
                LEFT JOIN players pw2 ON pw2.org_id = gr.org_id AND pw2.player_id = gr.winner_id2
                JOIN players pl1 ON pl1.org_id = gr.org_id AND pl1.player_id = gr.loser_id
                LEFT JOIN players pl2 ON pl2.org_id = gr.org_id AND pl2.player_id = gr.loser_id2
                WHERE gr.org_id = ? AND gr.session_id = ? ORDER BY gr.record_id DESC''',
                                (org_id, session_id)).fetchall()
        records = []
        for row in rows:
            r = dict(row)
            r.update(winner=r['winner_name'], loser=r['loser_name'], timestamp=r['created_at'],
                     is_multi_winner=bool(r['winner2_name']), is_multi_loser=bool(r['loser2_name']))
            r['winners'] = [{'id': r['winner_id'], 'name': r['winner_name']}]
            if r['winner2_name']:
                r['winners'].append({'id': r['winner_id2'], 'name': r['winner2_name']})
            r['losers'] = [{'id': r['loser_id'], 'name': r['loser_name']}]
            r['loser_display'] = r['loser_name']
            if r['loser2_name']:
                r['losers'].append({'id': r['loser_id2'], 'name': r['loser2_name']})
                r['loser_display'] += f" + {r['loser2_name']}"
            records.append(r)
        return records

    def delete_game_record(self, org_id: str, record_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM game_records WHERE org_id = ? AND record_id = ?',
                               (org_id, record_id)).fetchone()
            if not row:
                return None
            record = dict(row)
            if record['winner_id2']:
                changes = ((record['winner_id'], -(record['score'] // 2)),
                           (record['winner_id2'], -(record['score'] // 2)), (record['loser_id'], record['score']))
            elif record['loser_id2']:
                changes = ((record['winner_id'], -record['score']),
                           (record['loser_id'], record['score'] // 2),
                           (record['loser_id2'], record['score'] // 2))
            else:
                changes = ((record['winner_id'], -record['score']), (record['loser_id'], record['score']))
            for player_id, change in changes:
                conn.execute('''UPDATE session_players SET score = score + ?
                                WHERE org_id = ? AND session_id = ? AND player_id = ?''',
                             (change, org_id, record['session_id'], player_id))
            conn.execute('DELETE FROM game_records WHERE org_id = ? AND record_id = ?', (org_id, record_id))
            conn.commit()
            return record

    def get_player_records(self, org_id: str, player_id: str, start_date: str = None,
                           end_date: str = None) -> List[Dict]:
        sql = '''SELECT gr.*, s.name AS session_name, pw.name AS winner_name, pw2.name AS winner2_name,
                        pl1.name AS loser1_name, pl2.name AS loser2_name FROM game_records gr
                 JOIN sessions s ON s.org_id = gr.org_id AND s.session_id = gr.session_id
                 JOIN players pw ON pw.org_id = gr.org_id AND pw.player_id = gr.winner_id
                 LEFT JOIN players pw2 ON pw2.org_id = gr.org_id AND pw2.player_id = gr.winner_id2
                 JOIN players pl1 ON pl1.org_id = gr.org_id AND pl1.player_id = gr.loser_id
                 LEFT JOIN players pl2 ON pl2.org_id = gr.org_id AND pl2.player_id = gr.loser_id2
                 WHERE gr.org_id = ? AND (gr.winner_id = ? OR gr.winner_id2 = ?
                     OR gr.loser_id = ? OR gr.loser_id2 = ?)'''
        params = [org_id, player_id, player_id, player_id, player_id]
        if start_date: sql, params = sql + ' AND gr.created_at >= ?', params + [start_date]
        if end_date: sql, params = sql + ' AND gr.created_at <= ?', params + [end_date]
        with self.get_connection() as conn:
            rows = conn.execute(sql + ' ORDER BY gr.created_at DESC', params).fetchall()
        results = []
        for row in rows:
            r, winner = dict(row), row['winner_id'] == player_id or row['winner_id2'] == player_id
            r['is_winner'] = winner
            if winner:
                if r['winner_id2']: r['score'] //= 2
                opponents = [(r['loser_id'], r['loser1_name'])] + ([(r['loser_id2'], r['loser2_name'])] if r['loser2_name'] else [])
            else:
                if r['loser_id2']: r['score'] //= 2
                opponents = [(r['winner_id'], r['winner_name'])] + ([(r['winner_id2'], r['winner2_name'])] if r['winner2_name'] else [])
            r['opponent_name'] = ' + '.join(x[1] for x in opponents)
            r['opponent_id'] = opponents[0][0] if len(opponents) == 1 else [x[0] for x in opponents]
            r['opponent_names'] = None if len(opponents) == 1 else [{'id': x[0], 'name': x[1]} for x in opponents]
            r['timestamp'] = r['created_at']; results.append(r)
        return results

    # ===== 统计查询 =====

    def _player_record_rows(self, conn, org_id, player_id, start_date=None, end_date=None):
        sql = '''SELECT winner_id, winner_id2, loser_id, loser_id2, score FROM game_records
                 WHERE org_id = ? AND (winner_id = ? OR winner_id2 = ? OR loser_id = ? OR loser_id2 = ?)'''
        params = [org_id, player_id, player_id, player_id, player_id]
        if start_date: sql, params = sql + ' AND DATE(created_at) >= ?', params + [start_date]
        if end_date: sql, params = sql + ' AND DATE(created_at) <= ?', params + [end_date]
        return conn.execute(sql, params).fetchall()

    @staticmethod
    def _stats_from_rows(player_id, rows):
        stats = dict(total_games=0, wins=0, losses=0, total_score=0, effective_games=0, effective_wins=0)
        for r in rows:
            winner = r['winner_id'] == player_id or r['winner_id2'] == player_id
            stats['total_games'] += 1
            if winner:
                stats['wins'] += 1; stats['total_score'] += r['score'] // 2 if r['winner_id2'] else r['score']
                if r['score'] > 1: stats['effective_games'] += 1; stats['effective_wins'] += 1
            else:
                stats['losses'] += 1; stats['total_score'] -= r['score'] // 2 if r['loser_id2'] else r['score']
                if r['score'] > 1: stats['effective_games'] += 1
        return stats

    def get_player_stats(self, org_id: str, player_id: str) -> Dict:
        with self.get_connection() as conn: stats = self._stats_from_rows(player_id, self._player_record_rows(conn, org_id, player_id))
        return {k: stats[k] for k in ('total_games', 'wins', 'losses', 'total_score')}

    def get_global_leaderboard(self, org_id: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        with self.get_connection() as conn:
            players = conn.execute('SELECT player_id, name FROM players WHERE org_id = ?', (org_id,)).fetchall()
            board = []
            for p in players:
                stats = self._stats_from_rows(p['player_id'], self._player_record_rows(conn, org_id, p['player_id'], start_date, end_date))
                if stats['total_games']:
                    stats.update(player_id=p['player_id'], id=p['player_id'], name=p['name'], score=stats['total_score'],
                                 win_rate=(stats['effective_wins'] / stats['effective_games'] * 100 if stats['effective_games'] else 0))
                    board.append(stats)
        return sorted(board, key=lambda x: x['total_score'], reverse=True)

    def get_available_months(self, org_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute('''SELECT strftime('%Y-%m', created_at) AS key, CAST(strftime('%Y', created_at) AS INTEGER) AS year,
                CAST(strftime('%m', created_at) AS INTEGER) AS month, COUNT(DISTINCT session_id) AS count
                FROM sessions WHERE org_id = ? GROUP BY key ORDER BY key DESC''', (org_id,)).fetchall()
        return [{'key': r['key'], 'name': f"{r['year']}年{r['month']}月", 'count': r['count']} for r in rows]

    def get_available_months_for_player(self, org_id: str, player_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute('''SELECT strftime('%Y-%m', s.created_at) AS key, CAST(strftime('%Y', s.created_at) AS INTEGER) AS year,
                CAST(strftime('%m', s.created_at) AS INTEGER) AS month, COUNT(DISTINCT s.session_id) AS count FROM sessions s
                WHERE s.org_id = ? AND EXISTS (SELECT 1 FROM game_records gr WHERE gr.org_id = s.org_id AND gr.session_id = s.session_id
                    AND (gr.winner_id = ? OR gr.winner_id2 = ? OR gr.loser_id = ? OR gr.loser_id2 = ?)) GROUP BY key ORDER BY key DESC''',
                (org_id, player_id, player_id, player_id, player_id)).fetchall()
        return [{'key': r['key'], 'name': f"{r['year']}年{r['month']}月", 'count': r['count']} for r in rows]

    def get_player_effective_win_rate(self, org_id: str, player_id: str) -> Optional[float]:
        with self.get_connection() as conn: stats = self._stats_from_rows(player_id, self._player_record_rows(conn, org_id, player_id))
        return round(stats['effective_wins'] / stats['effective_games'] * 100, 1) if stats['effective_games'] else None

    # ===== 数据迁移工具 =====

    def migrate_from_json(self, json_data: Dict, org_id: str = EMS_ORG_ID):
        """Import the historical JSON format without changing score semantics."""
        with self.get_connection() as conn:
            for player_id, data in json_data.get('players', {}).items():
                conn.execute(
                    '''INSERT OR REPLACE INTO players
                       (player_id, org_id, name, name_key, created_at, updated_at, is_retired)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (
                        player_id, org_id, data['name'], normalize_name(data['name']),
                        data['created_at'], data['updated_at'], data.get('is_retired', 0),
                    ),
                )

            for session_id, data in json_data.get('sessions', {}).items():
                conn.execute(
                    '''INSERT OR REPLACE INTO sessions
                       (session_id, org_id, name, active, created_at, updated_at, end_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (
                        session_id, org_id, data['name'], int(data.get('active', True)),
                        data['timestamp'], data['timestamp'], data.get('end_time'),
                    ),
                )
                player_ids = data.get('player_ids') or [
                    row['player_id']
                    for name in data.get('players', [])
                    for row in conn.execute(
                        '''SELECT player_id FROM players
                           WHERE org_id = ? AND name_key = ?''',
                        (org_id, normalize_name(name)),
                    ).fetchall()
                ]
                for player_id in player_ids:
                    conn.execute(
                        '''INSERT OR REPLACE INTO session_players
                           (org_id, session_id, player_id, score)
                           VALUES (?, ?, ?, 0)''',
                        (org_id, session_id, player_id),
                    )

                records = data.get('records', [])
                normalized_records = []
                index = 0
                while index < len(records):
                    record = dict(records[index])
                    part = record.get('special_score_part')
                    if part and '1/2 (总分' in part and index + 1 < len(records):
                        try:
                            total_score = int(part.split('总分', 1)[1].split(')', 1)[0])
                        except (ValueError, IndexError):
                            total_score = None
                        next_record = records[index + 1]
                        next_part = next_record.get('special_score_part')
                        if (
                            total_score is not None
                            and next_part
                            and f'2/2 (总分{total_score})' in next_part
                            and next_record.get('winner_id') == record.get('winner_id')
                        ):
                            record['loser_id2'] = next_record.get('loser_id')
                            record['score'] = total_score
                            record['special_score'] = '大金' if total_score == 20 else '双吃'
                            index += 1
                    if not record.get('special_score') and part in {'小金', '大金', '双吃'}:
                        record['special_score'] = part
                    normalized_records.append(record)
                    index += 1

                for record in normalized_records:
                    winner_id = record.get('winner_id')
                    winner_id2 = record.get('winner_id2')
                    loser_id = record.get('loser_id')
                    loser_id2 = record.get('loser_id2')
                    score = record['score']
                    conn.execute(
                        '''INSERT INTO game_records
                           (org_id, session_id, winner_id, winner_id2, loser_id,
                            loser_id2, score, created_at, special_score,
                            special_score_part)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (
                            org_id, session_id, winner_id, winner_id2, loser_id,
                            loser_id2, score, record['timestamp'],
                            record.get('special_score'),
                            record.get('special_score_part'),
                        ),
                    )
                    if winner_id2:
                        changes = (
                            (winner_id, score // 2),
                            (winner_id2, score // 2),
                            (loser_id, -score),
                        )
                    elif loser_id2:
                        changes = (
                            (winner_id, score),
                            (loser_id, -(score // 2)),
                            (loser_id2, -(score // 2)),
                        )
                    else:
                        changes = ((winner_id, score), (loser_id, -score))
                    for player_id, delta in changes:
                        conn.execute(
                            '''UPDATE session_players SET score = score + ?
                               WHERE org_id = ? AND session_id = ? AND player_id = ?''',
                            (delta, org_id, session_id, player_id),
                        )
            conn.commit()

    # ===== 成就相关 =====

    def get_player_special_wins(self, org_id: str, player_id: str) -> Dict[str, bool]:
        with self.get_connection() as conn:
            rows = conn.execute('''SELECT DISTINCT special_score FROM game_records WHERE org_id = ?
                AND (winner_id = ? OR winner_id2 = ?) AND special_score IS NOT NULL''', (org_id, player_id, player_id)).fetchall()
        scores = {r['special_score'] for r in rows}; return {'has_small_gold': '小金' in scores, 'has_big_gold': '大金' in scores}

    def get_players_special_wins_batch(self, org_id: str, player_ids: List[str]) -> Dict[str, Dict[str, bool]]:
        result = {pid: {'has_small_gold': False, 'has_big_gold': False} for pid in player_ids}
        if not player_ids: return result
        marks = ','.join('?' * len(player_ids))
        with self.get_connection() as conn:
            rows = conn.execute(f'''SELECT winner_id, winner_id2, special_score FROM game_records WHERE org_id = ?
                AND (winner_id IN ({marks}) OR winner_id2 IN ({marks})) AND special_score IS NOT NULL''', [org_id, *player_ids, *player_ids]).fetchall()
        for r in rows:
            for pid in (r['winner_id'], r['winner_id2']):
                if pid in result: result[pid]['has_small_gold' if r['special_score'] == '小金' else 'has_big_gold'] = True
        return result

    def _achievement_score(self, kind): return {'small_gold': '小金', 'big_gold': '大金'}.get(kind)

    def get_achievement_players(self, org_id: str, achievement_type: str) -> List[Dict]:
        score = self._achievement_score(achievement_type)
        if not score: return []
        with self.get_connection() as conn:
            rows = conn.execute('''SELECT p.player_id, p.name, COUNT(gr.record_id) AS achievement_count, MIN(gr.created_at) AS first_achievement_date, MAX(gr.created_at) AS latest_achievement_date
                FROM players p JOIN game_records gr ON p.org_id = gr.org_id AND p.player_id = gr.winner_id WHERE p.org_id = ? AND gr.special_score = ?
                GROUP BY p.player_id, p.name ORDER BY achievement_count DESC, first_achievement_date ASC''', (org_id, score)).fetchall()
            return [dict(r) for r in rows]

    def get_achievement_records(self, org_id: str, achievement_type: str, player_id: str = None) -> List[Dict]:
        score = self._achievement_score(achievement_type)
        if not score: return []
        sql = '''SELECT gr.record_id, gr.session_id, gr.created_at, gr.score, gr.special_score, winner.name AS winner_name, loser.name AS loser_name,
                 loser2.name AS loser2_name, gr.loser_id, gr.loser_id2, s.name AS session_name FROM game_records gr
                 JOIN players winner ON winner.org_id = gr.org_id AND winner.player_id = gr.winner_id JOIN players loser ON loser.org_id = gr.org_id AND loser.player_id = gr.loser_id
                 LEFT JOIN players loser2 ON loser2.org_id = gr.org_id AND loser2.player_id = gr.loser_id2 JOIN sessions s ON s.org_id = gr.org_id AND s.session_id = gr.session_id
                 WHERE gr.org_id = ? AND gr.special_score = ?'''; params = [org_id, score]
        if player_id: sql, params = sql + ' AND gr.winner_id = ?', params + [player_id]
        with self.get_connection() as conn: rows = conn.execute(sql + ' ORDER BY gr.created_at DESC', params).fetchall()
        out = []
        for row in rows:
            r = dict(row); r['is_multi_loser'] = bool(r['loser2_name']); r['losers'] = [{'id': r['loser_id'], 'name': r['loser_name']}]; r['loser_display'] = r['loser_name']
            if r['loser2_name']: r['losers'].append({'id': r['loser_id2'], 'name': r['loser2_name']}); r['loser_display'] += f" + {r['loser2_name']}"
            out.append(r)
        return out

    def get_achievement_stats(self, org_id: str) -> Dict:
        with self.get_connection() as conn:
            result = {}
            for key, score in [('small_gold_players', '小金'), ('big_gold_players', '大金')]:
                result[key] = conn.execute('SELECT COUNT(DISTINCT winner_id) AS n FROM game_records WHERE org_id = ? AND special_score = ?', (org_id, score)).fetchone()['n']
            for key, score, minimum in [('small_gold_masters', '小金', 10), ('big_gold_masters', '大金', 5), ('big_gold_legends', '大金', 10), ('small_gold_legends', '小金', 20)]:
                result[key] = conn.execute('''SELECT COUNT(*) AS n FROM (SELECT winner_id FROM game_records WHERE org_id = ? AND special_score = ? GROUP BY winner_id HAVING COUNT(*) >= ?)''', (org_id, score, minimum)).fetchone()['n']
            result['gold_loser_players'] = conn.execute('''SELECT COUNT(DISTINCT player_id) AS n FROM (SELECT loser_id AS player_id FROM game_records WHERE org_id = ? AND special_score IN ('小金', '大金') UNION SELECT loser_id2 AS player_id FROM game_records WHERE org_id = ? AND special_score IN ('小金', '大金'))''', (org_id, org_id)).fetchone()['n']
        return result

    def get_achievement_master_players(self, org_id: str, achievement_type: str) -> List[Dict]:
        options = {'small_gold_master': ('小金', 10), 'small_gold_legend': ('小金', 20), 'big_gold_master': ('大金', 5), 'big_gold_legend': ('大金', 10)}
        if achievement_type not in options: return []
        score, minimum = options[achievement_type]
        with self.get_connection() as conn:
            rows = conn.execute('''SELECT p.player_id, p.name, COUNT(gr.record_id) AS achievement_count, MIN(gr.created_at) AS first_achievement_date, MAX(gr.created_at) AS latest_achievement_date
                FROM players p JOIN game_records gr ON p.org_id = gr.org_id AND p.player_id = gr.winner_id WHERE p.org_id = ? AND gr.special_score = ?
                GROUP BY p.player_id, p.name HAVING COUNT(gr.record_id) >= ? ORDER BY achievement_count DESC, first_achievement_date ASC''', (org_id, score, minimum)).fetchall()
            return [dict(r) for r in rows]

    def get_negative_achievement_players(self, org_id: str, achievement_type: str) -> List[Dict]:
        if achievement_type != 'gold_loser': return []
        with self.get_connection() as conn:
            rows = conn.execute('''SELECT p.player_id, p.name, COUNT(gr.record_id) AS defeat_count, MIN(gr.created_at) AS first_defeat_date, MAX(gr.created_at) AS latest_defeat_date
                FROM players p JOIN game_records gr ON p.org_id = gr.org_id AND (p.player_id = gr.loser_id OR p.player_id = gr.loser_id2)
                WHERE p.org_id = ? AND gr.special_score IN ('小金', '大金') GROUP BY p.player_id, p.name ORDER BY defeat_count DESC, first_defeat_date ASC''', (org_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_negative_achievement_records(self, org_id: str, achievement_type: str, player_id: str = None) -> List[Dict]:
        if achievement_type != 'gold_loser': return []
        sql = '''SELECT gr.record_id, gr.session_id, gr.created_at, gr.score, gr.special_score, winner.name AS winner_name, loser.name AS loser_name, loser2.name AS loser2_name, gr.loser_id, gr.loser_id2, s.name AS session_name FROM game_records gr
            JOIN players winner ON winner.org_id = gr.org_id AND winner.player_id = gr.winner_id JOIN players loser ON loser.org_id = gr.org_id AND loser.player_id = gr.loser_id
            LEFT JOIN players loser2 ON loser2.org_id = gr.org_id AND loser2.player_id = gr.loser_id2 JOIN sessions s ON s.org_id = gr.org_id AND s.session_id = gr.session_id
            WHERE gr.org_id = ? AND gr.special_score IN ('小金', '大金')'''; params = [org_id]
        if player_id: sql, params = sql + ' AND (gr.loser_id = ? OR gr.loser_id2 = ?)', params + [player_id, player_id]
        with self.get_connection() as conn: return [dict(r) for r in conn.execute(sql + ' ORDER BY gr.created_at DESC', params).fetchall()]

    def get_best_buddy_stats(self, org_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute('''SELECT gr.winner_id, w.name AS winner_name, gr.loser_id, l.name AS loser_name, COUNT(*) AS gift_count FROM game_records gr
                JOIN players w ON w.org_id = gr.org_id AND w.player_id = gr.winner_id JOIN players l ON l.org_id = gr.org_id AND l.player_id = gr.loser_id
                WHERE gr.org_id = ? AND gr.score = 1 GROUP BY gr.winner_id, gr.loser_id''', (org_id,)).fetchall()
        maxes = {}
        for row in rows:
            r = dict(row)
            if r['winner_id'] not in maxes or r['gift_count'] > maxes[r['winner_id']]['gift_count']: maxes[r['winner_id']] = r
        return sorted([{'player_id': r['winner_id'], 'player_name': r['winner_name'], 'buddy_id': r['loser_id'], 'buddy_name': r['loser_name'], 'gift_count': r['gift_count']} for r in maxes.values()], key=lambda r: r['gift_count'], reverse=True)

    def get_duo_loser_stats(self, org_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute('''SELECT gr.loser_id, l1.name AS loser1_name, gr.loser_id2, l2.name AS loser2_name, COUNT(*) AS duo_count FROM game_records gr
                JOIN players l1 ON l1.org_id = gr.org_id AND l1.player_id = gr.loser_id JOIN players l2 ON l2.org_id = gr.org_id AND l2.player_id = gr.loser_id2
                WHERE gr.org_id = ? AND gr.loser_id2 IS NOT NULL GROUP BY gr.loser_id, gr.loser_id2''', (org_id,)).fetchall()
        pairs = {}
        for row in rows:
            r = dict(row); key = tuple(sorted((r['loser_id'], r['loser_id2'])))
            if key not in pairs:
                a, b = (r['loser_id'], r['loser1_name']), (r['loser_id2'], r['loser2_name'])
                if a[0] != key[0]: a, b = b, a
                pairs[key] = {'player1_id': a[0], 'player1_name': a[1], 'player2_id': b[0], 'player2_name': b[1], 'duo_count': 0}
            pairs[key]['duo_count'] += r['duo_count']
        return sorted(pairs.values(), key=lambda r: r['duo_count'], reverse=True)

    def get_honor_roll_stats(self, org_id: str, top_n: int = 10) -> Dict[str, List[Dict]]:
        valid = '''SELECT sp.session_id, MAX(sp.score) AS high, MIN(sp.score) AS low FROM session_players sp JOIN sessions s ON s.org_id = sp.org_id AND s.session_id = sp.session_id
                   WHERE sp.org_id = ? AND s.active = 0 AND EXISTS (SELECT 1 FROM game_records gr WHERE gr.org_id = sp.org_id AND gr.session_id = sp.session_id) GROUP BY sp.session_id'''
        with self.get_connection() as conn:
            champions = conn.execute(f'''SELECT p.player_id, p.name, COUNT(*) AS champion_count FROM session_players sp JOIN players p ON p.org_id = sp.org_id AND p.player_id = sp.player_id JOIN ({valid}) v ON v.session_id = sp.session_id WHERE sp.org_id = ? AND sp.score = v.high AND sp.score > 0 GROUP BY p.player_id, p.name ORDER BY champion_count DESC, p.name ASC LIMIT ?''', (org_id, org_id, top_n)).fetchall()
            losers = conn.execute(f'''SELECT p.player_id, p.name, COUNT(*) AS loser_count FROM session_players sp JOIN players p ON p.org_id = sp.org_id AND p.player_id = sp.player_id JOIN ({valid}) v ON v.session_id = sp.session_id WHERE sp.org_id = ? AND sp.score = v.low AND sp.score < 0 GROUP BY p.player_id, p.name ORDER BY loser_count DESC, p.name ASC LIMIT ?''', (org_id, org_id, top_n)).fetchall()
        return {'champions': [dict(r) for r in champions], 'losers': [dict(r) for r in losers]}

    # ===== 退役相关 =====

    def _set_retired(self, org_id: str, player_id: str, retired: bool) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute('UPDATE players SET is_retired = ? WHERE org_id = ? AND player_id = ?', (int(retired), org_id, player_id))
            if not cursor.rowcount: return False
            conn.execute('INSERT INTO player_retirement_log (org_id, player_id, action, created_at) VALUES (?, ?, ?, ?)', (org_id, player_id, 'retire' if retired else 'comeback', get_utc_timestamp()))
            conn.commit(); return True

    def retire_player(self, org_id: str, player_id: str) -> bool: return self._set_retired(org_id, player_id, True)
    def comeback_player(self, org_id: str, player_id: str) -> bool: return self._set_retired(org_id, player_id, False)

    def is_player_retired(self, org_id: str, player_id: str) -> bool:
        with self.get_connection() as conn:
            row = conn.execute('SELECT is_retired FROM players WHERE org_id = ? AND player_id = ?', (org_id, player_id)).fetchone()
            return bool(row and row['is_retired'])

    def get_retired_player_ids(self, org_id: str) -> set:
        with self.get_connection() as conn:
            return {r['player_id'] for r in conn.execute('SELECT player_id FROM players WHERE org_id = ? AND is_retired = 1', (org_id,)).fetchall()}


class DatabaseProxy:
    """Resolve the app-scoped manager, with a lazy default outside Flask contexts."""

    def __init__(self):
        self._default_manager = None

    def _manager(self) -> DatabaseManager:
        if has_app_context():
            manager = current_app.extensions.get('database')
            if manager is not None:
                return manager
        if self._default_manager is None:
            self._default_manager = DatabaseManager()
        return self._default_manager

    @property
    def db_path(self):
        return self._manager().db_path

    @db_path.setter
    def db_path(self, value):
        self._manager().db_path = value

    def __getattr__(self, name):
        return getattr(self._manager(), name)


def get_db() -> DatabaseManager:
    """Return the database manager bound to the current Flask application."""
    return db._manager()


# Compatibility proxy used by model and tournament modules.
db = DatabaseProxy()
