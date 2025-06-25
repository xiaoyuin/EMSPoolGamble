"""
数据库服务层
提供数据操作的接口，兼容原有代码结构
"""
from models import db, GameSession, Player, Viewer, PlayerScore, GameRecord, RecentPlayer
from collections import defaultdict
from datetime import datetime
import uuid

class DatabaseService:
    """数据库服务类"""

    @staticmethod
    def init_db():
        """初始化数据库"""
        db.create_all()

    @staticmethod
    def get_all_sessions():
        """获取所有游戏场次"""
        sessions_dict = {}
        db_sessions = GameSession.query.all()

        for session in db_sessions:
            sessions_dict[session.id] = session.to_dict()

        return sessions_dict

    @staticmethod
    def create_session(session_name):
        """创建新的游戏场次"""
        session_id = str(uuid.uuid4())
        new_session = GameSession(
            id=session_id,
            name=session_name,
            active=True,
            timestamp=datetime.utcnow()
        )

        db.session.add(new_session)
        db.session.commit()

        return session_id

    @staticmethod
    def get_session(session_id):
        """获取单个游戏场次"""
        session = GameSession.query.get(session_id)
        if session:
            return session.to_dict()
        return None

    @staticmethod
    def add_player_to_session(session_id, username):
        """添加玩家到场次"""
        # 检查是否已存在
        existing_player = Player.query.filter_by(
            session_id=session_id,
            username=username
        ).first()

        existing_viewer = Viewer.query.filter_by(
            session_id=session_id,
            username=username
        ).first()

        if existing_player or existing_viewer:
            return False, "用户名已存在"

        # 添加玩家
        new_player = Player(session_id=session_id, username=username)
        db.session.add(new_player)

        # 初始化分数
        new_score = PlayerScore(
            session_id=session_id,
            player_name=username,
            score=0
        )
        db.session.add(new_score)

        # 更新最近玩家记录
        DatabaseService._update_recent_player(username)

        db.session.commit()
        return True, "添加成功"

    @staticmethod
    def add_viewer_to_session(session_id, username):
        """添加观众到场次"""
        # 检查是否已存在
        existing_player = Player.query.filter_by(
            session_id=session_id,
            username=username
        ).first()

        existing_viewer = Viewer.query.filter_by(
            session_id=session_id,
            username=username
        ).first()

        if existing_player or existing_viewer:
            return False, "用户名已存在"

        # 添加观众
        new_viewer = Viewer(session_id=session_id, username=username)
        db.session.add(new_viewer)

        db.session.commit()
        return True, "添加成功"

    @staticmethod
    def add_game_record(session_id, winner, loser, score):
        """添加游戏记录"""
        # 验证玩家是否存在
        winner_exists = Player.query.filter_by(
            session_id=session_id,
            username=winner
        ).first()

        loser_exists = Player.query.filter_by(
            session_id=session_id,
            username=loser
        ).first()

        if not winner_exists or not loser_exists:
            return False, "选择的玩家不在当前场次中"

        if winner == loser:
            return False, "胜者和败者不能是同一个玩家"

        # 添加记录
        new_record = GameRecord(
            session_id=session_id,
            winner=winner,
            loser=loser,
            score=score,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_record)

        # 更新分数
        winner_score = PlayerScore.query.filter_by(
            session_id=session_id,
            player_name=winner
        ).first()

        loser_score = PlayerScore.query.filter_by(
            session_id=session_id,
            player_name=loser
        ).first()

        if winner_score:
            winner_score.score += score
        else:
            winner_score = PlayerScore(
                session_id=session_id,
                player_name=winner,
                score=score
            )
            db.session.add(winner_score)

        if loser_score:
            loser_score.score -= score
        else:
            loser_score = PlayerScore(
                session_id=session_id,
                player_name=loser,
                score=-score
            )
            db.session.add(loser_score)

        db.session.commit()
        return True, "记录添加成功"

    @staticmethod
    def delete_game_record(session_id, record_index):
        """删除游戏记录"""
        # 获取所有记录，按时间排序
        records = GameRecord.query.filter_by(session_id=session_id)\
                                  .order_by(GameRecord.timestamp).all()

        if record_index < 0 or record_index >= len(records):
            return False, "无效的记录索引"

        record_to_delete = records[record_index]

        # 恢复分数
        winner_score = PlayerScore.query.filter_by(
            session_id=session_id,
            player_name=record_to_delete.winner
        ).first()

        loser_score = PlayerScore.query.filter_by(
            session_id=session_id,
            player_name=record_to_delete.loser
        ).first()

        if winner_score:
            winner_score.score -= record_to_delete.score

        if loser_score:
            loser_score.score += record_to_delete.score

        # 删除记录
        db.session.delete(record_to_delete)
        db.session.commit()

        return True, f"已删除记录：{record_to_delete.winner} 胜 {record_to_delete.loser} ({record_to_delete.score}分)"

    @staticmethod
    def end_session(session_id):
        """结束游戏场次"""
        session = GameSession.query.get(session_id)
        if session:
            session.active = False
            session.end_time = datetime.utcnow()
            db.session.commit()
            return True
        return False

    @staticmethod
    def delete_session(session_id):
        """删除游戏场次"""
        session = GameSession.query.get(session_id)
        if session:
            db.session.delete(session)
            db.session.commit()
            return True
        return False

    @staticmethod
    def get_recent_players():
        """获取最近使用的玩家名单"""
        recent_players = RecentPlayer.query.order_by(RecentPlayer.last_used.desc()).limit(10).all()
        return [player.username for player in recent_players]

    @staticmethod
    def _update_recent_player(username):
        """更新最近玩家记录"""
        existing = RecentPlayer.query.filter_by(username=username).first()

        if existing:
            existing.last_used = datetime.utcnow()
        else:
            new_recent = RecentPlayer(username=username, last_used=datetime.utcnow())
            db.session.add(new_recent)

        # 保持最近玩家列表不超过10个
        all_recent = RecentPlayer.query.order_by(RecentPlayer.last_used.desc()).all()
        if len(all_recent) > 10:
            for old_player in all_recent[10:]:
                db.session.delete(old_player)

    @staticmethod
    def get_total_scores():
        """计算全局玩家总分"""
        total_scores = defaultdict(int)

        # 获取所有分数记录
        all_scores = PlayerScore.query.all()

        for score_record in all_scores:
            total_scores[score_record.player_name] += score_record.score

        # 按分数排序
        sorted_total_scores = sorted(
            [(p, score) for p, score in total_scores.items()],
            key=lambda x: x[1],
            reverse=True
        )

        return sorted_total_scores
