"""
数据模型和数据库操作模块
"""
import uuid
import json
import os
import traceback
from collections import defaultdict
from .utils import get_utc_timestamp


# 内存数据结构，后期可替换为数据库
sessions = {}  # {session_id: {player_ids, viewer_ids, records, scores, timestamp, ...}}
players = {}   # {player_id: {name, created_at, updated_at, stats, ...}}

# 全局变量存储最近添加的玩家ID
recent_player_ids = []


# 玩家管理函数
def create_player(name):
    """创建新玩家，返回player_id"""
    player_id = str(uuid.uuid4())
    current_time = get_utc_timestamp()  # 统一使用UTC时间存储
    players[player_id] = {
        'name': name,
        'created_at': current_time,
        'updated_at': current_time,
        'stats': {
            'total_games': 0,
            'total_wins': 0,
            'total_losses': 0,
            'total_score': 0
        }
    }
    return player_id


def get_player_by_name(name):
    """根据名字查找玩家，返回player_id或None"""
    for player_id, player_data in players.items():
        if player_data['name'] == name:
            return player_id
    return None


def get_or_create_player(name):
    """获取或创建玩家，返回player_id"""
    player_id = get_player_by_name(name)
    if player_id is None:
        player_id = create_player(name)
    return player_id


def update_player_name(player_id, new_name):
    """更新玩家名字"""
    if player_id in players:
        players[player_id]['name'] = new_name
        players[player_id]['updated_at'] = get_utc_timestamp()  # 统一使用UTC时间存储
        return True
    return False


def get_player_name(player_id):
    """根据player_id获取玩家名字"""
    return players.get(player_id, {}).get('name', 'Unknown Player')


# 数据文件路径配置
def get_data_file_path():
    """获取数据文件路径，Azure中使用/home目录以保证持久化"""
    if os.environ.get('WEBSITE_SITE_NAME'):  # 检测是否在Azure App Service中
        # Azure App Service中，/home目录是持久化的
        data_dir = '/home/data'
        try:
            os.makedirs(data_dir, exist_ok=True)
        except OSError as e:
            print(f"警告：无法创建Azure数据目录 {data_dir}: {e}")
            # 降级到使用/home目录
            data_dir = '/home'
        return os.path.join(data_dir, 'data.json')
    else:
        # 本地开发环境
        return 'data.json'


# 尝试从文件加载历史数据
def load_data():
    global recent_player_ids, sessions, players
    data_file = get_data_file_path()
    
    # 保证机制：如果get_data_file_path返回有问题的路径，降级到当前目录的data.json
    if not data_file or data_file.strip() == '':
        print("警告：数据文件路径为空，降级到当前目录")
        data_file = 'data.json'
        
    try:
        # 加载场次数据
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

                # 加载玩家数据（如果存在）
                if 'players' in data:
                    players.update(data['players'])  # 使用update而不是直接赋值
                    sessions_data = data.get('sessions', {})
                else:
                    # 兼容旧数据格式，将玩家名字转换为ID
                    sessions_data = data

                # 处理场次数据
                for sid, s in sessions_data.items():
                    # 兼容旧数据：从玩家名字转换为player_ids
                    if 'players' in s and isinstance(list(s['players'])[0] if s['players'] else '', str):
                        # 旧格式：players是名字的set
                        player_names = s['players'] if isinstance(s['players'], list) else list(s['players'])
                        s['player_ids'] = set()
                        for name in player_names:
                            player_id = get_or_create_player(name)
                            s['player_ids'].add(player_id)
                        # 保留原有的players字段暂时兼容
                        s['players'] = set(player_names)
                    elif 'player_ids' in s:
                        # 新格式：已经有player_ids
                        s['player_ids'] = set(s['player_ids'])
                        # 为了显示需要，重建players字段
                        s['players'] = set(get_player_name(pid) for pid in s['player_ids'])
                    else:
                        s['player_ids'] = set()
                        s['players'] = set()

                    # 处理viewers
                    if 'viewers' in s:
                        s['viewers'] = set(s['viewers']) if isinstance(s['viewers'], list) else s['viewers']
                    else:
                        s['viewers'] = set()

                    # 为旧数据添加默认场次名称
                    if 'name' not in s:
                        s['name'] = f"场次 #{len(sessions_data) - list(sessions_data.keys()).index(sid)}"

                    # 兼容旧数据：将rounds改为records
                    if 'rounds' in s and 'records' not in s:
                        s['records'] = s['rounds']
                        del s['rounds']
                    if 'records' not in s:
                        s['records'] = []

                    # 处理records中的玩家名字，转换为player_id（如果需要）
                    for record in s['records']:
                        if 'winner_id' not in record and 'winner' in record:
                            record['winner_id'] = get_or_create_player(record['winner'])
                        if 'loser_id' not in record and 'loser' in record:
                            record['loser_id'] = get_or_create_player(record['loser'])

                    # 确保scores是defaultdict类型，并且所有玩家都有分数条目
                    if not isinstance(s['scores'], defaultdict):
                        scores_dict = defaultdict(int)
                        scores_dict.update(s['scores'])
                        s['scores'] = scores_dict

                    # 确保所有玩家都在scores中有条目（使用名字作为键）
                    for player_name in s['players']:
                        if player_name not in s['scores']:
                            s['scores'][player_name] = 0

                # 收集最近的玩家ID
                all_player_ids = set()
                for s in sessions_data.values():
                    all_player_ids.update(s.get('player_ids', set()))
                recent_player_ids = list(all_player_ids)[-10:]  # 最多保留10个最近玩家

                return sessions_data
        return {}
    except Exception as e:
        print(f"加载数据失败: {e}")
        traceback.print_exc()
        return {}


# 保存数据到文件
def save_data():
    data_file = get_data_file_path()
    
    # 保证机制：如果get_data_file_path返回有问题的路径，降级到当前目录的data.json
    if not data_file or data_file.strip() == '':
        print("警告：数据文件路径为空，降级到当前目录")
        data_file = 'data.json'
    
    try:
        # 确保数据目录存在（只有当目录不为空时才创建）
        data_dir = os.path.dirname(data_file)
        if data_dir and data_dir.strip() != '':  # 只有当目录路径不为空时才创建
            os.makedirs(data_dir, exist_ok=True)

        # 构建完整的数据结构
        data = {
            'players': players,
            'sessions': {}
        }

        # 将set转换为list以便JSON序列化
        for sid, s in sessions.items():
            s_copy = s.copy()
            s_copy['players'] = list(s.get('players', set()))
            s_copy['viewers'] = list(s.get('viewers', set()))
            s_copy['player_ids'] = list(s.get('player_ids', set()))
            data['sessions'][sid] = s_copy

        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"数据已保存到: {data_file}")
    except Exception as e:
        print(f"保存数据失败: {e}")
        traceback.print_exc()


# 初始化数据
def init_data():
    """初始化数据，在应用启动时调用"""
    global sessions, players
    loaded_sessions = load_data()
    sessions.update(loaded_sessions)
    print(f"初始化完成: 加载了 {len(sessions)} 个场次, {len(players)} 个玩家")
