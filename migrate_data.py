"""
数据迁移脚本
将现有的 data.json 文件数据迁移到 SQLite 数据库
"""
import json
import os
from datetime import datetime
from models import db, GameSession, Player, Viewer, PlayerScore, GameRecord, RecentPlayer
from collections import defaultdict

def migrate_data_from_json():
    """从 JSON 文件迁移数据到数据库"""
    json_file = 'data.json'

    if not os.path.exists(json_file):
        print("未找到 data.json 文件，跳过数据迁移")
        return

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"开始迁移 {len(data)} 个游戏场次...")

        for session_id, session_data in data.items():
            # 创建游戏场次
            game_session = GameSession(
                id=session_id,
                name=session_data.get('name', f'场次 #{session_id}'),
                active=session_data.get('active', True),
                timestamp=datetime.strptime(session_data['timestamp'], '%Y-%m-%d %H:%M:%S'),
                end_time=datetime.strptime(session_data['end_time'], '%Y-%m-%d %H:%M:%S')
                         if session_data.get('end_time') else None
            )
            db.session.add(game_session)

            # 添加玩家
            players = session_data.get('players', [])
            if isinstance(players, list):
                players_set = set(players)
            else:
                players_set = players

            for player_name in players_set:
                player = Player(
                    username=player_name,
                    session_id=session_id,
                    joined_at=game_session.timestamp
                )
                db.session.add(player)

                # 添加玩家分数
                score_value = session_data.get('scores', {}).get(player_name, 0)
                player_score = PlayerScore(
                    player_name=player_name,
                    score=score_value,
                    session_id=session_id
                )
                db.session.add(player_score)

            # 添加观众
            viewers = session_data.get('viewers', [])
            if isinstance(viewers, list):
                viewers_set = set(viewers)
            else:
                viewers_set = viewers

            for viewer_name in viewers_set:
                viewer = Viewer(
                    username=viewer_name,
                    session_id=session_id,
                    joined_at=game_session.timestamp
                )
                db.session.add(viewer)

            # 添加游戏记录
            records = session_data.get('records', [])
            for record in records:
                game_record = GameRecord(
                    winner=record['winner'],
                    loser=record['loser'],
                    score=record['score'],
                    timestamp=datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S'),
                    session_id=session_id
                )
                db.session.add(game_record)

        # 收集所有玩家名字作为最近玩家
        all_players = set()
        for session_data in data.values():
            players = session_data.get('players', [])
            if isinstance(players, list):
                all_players.update(players)
            else:
                all_players.update(players)

        # 添加最近玩家记录（最多10个）
        recent_players_list = list(all_players)[-10:]
        for i, player_name in enumerate(recent_players_list):
            recent_player = RecentPlayer(
                username=player_name,
                last_used=datetime.utcnow()
            )
            db.session.add(recent_player)

        # 提交所有更改
        db.session.commit()

        print(f"数据迁移完成！迁移了 {len(data)} 个游戏场次")

        # 备份原始文件
        backup_file = f"data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.rename(json_file, backup_file)
        print(f"原始 data.json 已备份为 {backup_file}")

    except Exception as e:
        print(f"数据迁移失败: {e}")
        db.session.rollback()
        raise

if __name__ == '__main__':
    from app import app
    with app.app_context():
        db.create_all()
        migrate_data_from_json()
