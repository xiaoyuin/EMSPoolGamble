"""
数据库模型定义
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from collections import defaultdict

db = SQLAlchemy()

class GameSession(db.Model):
    """游戏场次模型"""
    __tablename__ = 'game_sessions'

    id = db.Column(db.String(36), primary_key=True)  # UUID
    name = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Boolean, default=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)

    # 关联关系
    players = db.relationship('Player', backref='session', lazy=True, cascade='all, delete-orphan')
    viewers = db.relationship('Viewer', backref='session', lazy=True, cascade='all, delete-orphan')
    records = db.relationship('GameRecord', backref='session', lazy=True, cascade='all, delete-orphan')
    scores = db.relationship('PlayerScore', backref='session', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<GameSession {self.name}>'

    def to_dict(self):
        """转换为字典格式，兼容原有代码"""
        players_set = set(player.username for player in self.players)
        viewers_set = set(viewer.username for viewer in self.viewers)

        # 构建分数字典
        scores_dict = defaultdict(int)
        for score in self.scores:
            scores_dict[score.player_name] = score.score

        # 确保所有玩家都在scores中有条目
        for player in self.players:
            if player.username not in scores_dict:
                scores_dict[player.username] = 0

        return {
            'name': self.name,
            'players': players_set,
            'viewers': viewers_set,
            'records': [record.to_dict() for record in self.records],
            'scores': scores_dict,
            'active': self.active,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else None
        }

class Player(db.Model):
    """玩家模型"""
    __tablename__ = 'players'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    session_id = db.Column(db.String(36), db.ForeignKey('game_sessions.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 唯一约束：同一个会话中不能有重名玩家
    __table_args__ = (db.UniqueConstraint('username', 'session_id', name='unique_player_session'),)

    def __repr__(self):
        return f'<Player {self.username}>'

class Viewer(db.Model):
    """观众模型"""
    __tablename__ = 'viewers'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    session_id = db.Column(db.String(36), db.ForeignKey('game_sessions.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 唯一约束：同一个会话中不能有重名观众
    __table_args__ = (db.UniqueConstraint('username', 'session_id', name='unique_viewer_session'),)

    def __repr__(self):
        return f'<Viewer {self.username}>'

class PlayerScore(db.Model):
    """玩家分数模型"""
    __tablename__ = 'player_scores'

    id = db.Column(db.Integer, primary_key=True)
    player_name = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Integer, default=0)
    session_id = db.Column(db.String(36), db.ForeignKey('game_sessions.id'), nullable=False)

    # 唯一约束：同一个会话中每个玩家只有一个分数记录
    __table_args__ = (db.UniqueConstraint('player_name', 'session_id', name='unique_player_score'),)

    def __repr__(self):
        return f'<PlayerScore {self.player_name}: {self.score}>'

class GameRecord(db.Model):
    """游戏记录模型"""
    __tablename__ = 'game_records'

    id = db.Column(db.Integer, primary_key=True)
    winner = db.Column(db.String(50), nullable=False)
    loser = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    session_id = db.Column(db.String(36), db.ForeignKey('game_sessions.id'), nullable=False)

    def __repr__(self):
        return f'<GameRecord {self.winner} beats {self.loser} ({self.score})>'

    def to_dict(self):
        """转换为字典格式，兼容原有代码"""
        return {
            'winner': self.winner,
            'loser': self.loser,
            'score': self.score,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

class RecentPlayer(db.Model):
    """最近玩家记录模型"""
    __tablename__ = 'recent_players'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    last_used = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<RecentPlayer {self.username}>'
