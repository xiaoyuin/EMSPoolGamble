from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from collections import defaultdict
import uuid
import datetime
import json
import os

# 时区处理工具函数
def get_user_local_time(timezone_offset_minutes=None):
    """
    获取用户本地时间
    :param timezone_offset_minutes: 用户时区偏移量（分钟），正数表示UTC+，负数表示UTC-
    :return: 格式化的本地时间字符串
    """
    utc_now = datetime.datetime.utcnow()

    if timezone_offset_minutes is not None:
        # 根据用户时区调整时间
        local_time = utc_now + datetime.timedelta(minutes=timezone_offset_minutes)
    else:
        # 降级到服务器本地时间（兼容性）
        local_time = datetime.datetime.now()

    return local_time.strftime('%Y-%m-%d %H:%M:%S')

def get_user_local_datetime(timezone_offset_minutes=None):
    """
    获取用户本地时间的datetime对象
    :param timezone_offset_minutes: 用户时区偏移量（分钟）
    :return: datetime对象
    """
    utc_now = datetime.datetime.utcnow()

    if timezone_offset_minutes is not None:
        return utc_now + datetime.timedelta(minutes=timezone_offset_minutes)
    else:
        return datetime.datetime.now()

# 应用版本信息
APP_VERSION = "v1.3.2"
APP_NAME = "EMS Pool Gamble"
VERSION_DATE = "2025-06-26"

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key_for_testing')  # 用于会话管理

# 内存数据结构，后期可替换为数据库
sessions = {}  # {session_id: {player_ids, viewer_ids, records, scores, timestamp, ...}}
players = {}   # {player_id: {name, created_at, updated_at, stats, ...}}

# 默认分数选项（包含特殊分数14和20）
DEFAULT_SCORE_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14, 20]

# 全局变量存储最近添加的玩家ID
recent_player_ids = []

# 玩家管理函数
def create_player(name, timezone_offset_minutes=None):
    """创建新玩家，返回player_id"""
    player_id = str(uuid.uuid4())
    current_time = get_user_local_time(timezone_offset_minutes)
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

def get_or_create_player(name, timezone_offset_minutes=None):
    """获取或创建玩家，返回player_id"""
    player_id = get_player_by_name(name)
    if player_id is None:
        player_id = create_player(name, timezone_offset_minutes)
    return player_id

def update_player_name(player_id, new_name, timezone_offset_minutes=None):
    """更新玩家名字"""
    if player_id in players:
        players[player_id]['name'] = new_name
        players[player_id]['updated_at'] = get_user_local_time(timezone_offset_minutes)
        return True
    return False

def get_player_name(player_id):
    """根据player_id获取玩家名字"""
    return players.get(player_id, {}).get('name', 'Unknown Player')

# 生成自动场次名称
def generate_session_name(timezone_offset_minutes=None):
    """
    生成自动场次名称
    :param timezone_offset_minutes: 用户时区偏移量（分钟），正数表示UTC+，负数表示UTC-
    """
    now = datetime.datetime.utcnow()  # 使用UTC时间作为基准

    if timezone_offset_minutes is not None:
        # 根据用户时区调整时间
        user_time = now + datetime.timedelta(minutes=timezone_offset_minutes)
    else:
        # 降级到服务器本地时间（兼容性）
        user_time = datetime.datetime.now()

    month = user_time.month
    day = user_time.day
    hour = user_time.hour

    # 判断时间段
    if 6 <= hour < 11:
        time_period = "上午"
    elif 11 <= hour < 14:
        time_period = "中午"
    elif 14 <= hour < 18:
        time_period = "下午"
    else:
        time_period = "晚上"

    return f"{month}月{day}号{time_period}场"

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
    try:
        # 加载场次数据
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

                # 加载玩家数据（如果存在）
                if 'players' in data:
                    players = data['players']
                    sessions_data = data.get('sessions', {})
                else:
                    # 兼容旧数据格式，将玩家名字转换为ID
                    sessions_data = data
                    players = {}

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
        import traceback
        traceback.print_exc()
        return {}

# 保存数据到文件
def save_data():
    data_file = get_data_file_path()
    try:
        # 确保数据目录存在
        os.makedirs(os.path.dirname(data_file), exist_ok=True)

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
        import traceback
        traceback.print_exc()

# 尝试加载历史数据
sessions = load_data()
if 'players' not in globals() or not players:
    players = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    # 进入首页，显示当前进行中的场次列表
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create_session':
            # 获取用户时区偏移量（从前端传递）
            timezone_offset = request.form.get('timezone_offset')
            try:
                timezone_offset_minutes = int(timezone_offset) if timezone_offset else None
            except (ValueError, TypeError):
                timezone_offset_minutes = None

            # 自动创建新场次，根据用户时区生成名称
            session_name = generate_session_name(timezone_offset_minutes)

            # 如果已经存在相同名称的活跃场次，添加序号
            existing_names = [s['name'] for s in sessions.values() if s.get('active', True)]
            counter = 1
            original_name = session_name
            while session_name in existing_names:
                counter += 1
                session_name = f"{original_name} ({counter})"

            session_id = str(uuid.uuid4())
            sessions[session_id] = {
                'name': session_name,
                'players': set(),          # 暂时保留用于显示
                'player_ids': set(),       # 新增：存储玩家ID
                'viewers': set(),
                'records': [],             # 改为records存储计分记录
                'scores': defaultdict(int),
                'active': True,
                'timestamp': get_user_local_time(timezone_offset_minutes)
            }

            # 保存数据
            save_data()
            flash(f'场次 "{session_name}" 创建成功', 'success')
            # 直接进入新创建的房间
            return redirect(url_for('game', session_id=session_id))

        elif action == 'join_session':
            # 直接加入现有场次，所有人都是玩家
            session_id = request.form['session_id']

            if session_id not in sessions:
                flash('场次不存在', 'error')
                return redirect(url_for('index'))

            # 直接跳转到游戏页面，无需登录
            return redirect(url_for('game', session_id=session_id))

    # 获取所有活跃的场次
    active_sessions = {k: v for k, v in sessions.items() if v.get('active', True)}
    sorted_active_sessions = sorted(
        active_sessions.items(),
        key=lambda x: x[1].get('timestamp', ''),
        reverse=True
    )

    # 获取最近结束的场次（最多3个）
    ended_sessions = {k: v for k, v in sessions.items() if not v.get('active', True)}
    sorted_ended_sessions = sorted(
        ended_sessions.items(),
        key=lambda x: x[1].get('end_time', x[1].get('timestamp', '')),
        reverse=True
    )[:3]

    return render_template('index.html',
                         active_sessions=sorted_active_sessions,
                         ended_sessions=sorted_ended_sessions,
                         sessions=sessions,
                         suggested_session_name=generate_session_name(),  # 默认用服务器时间，前端会替换
                         app_version=APP_VERSION,
                         app_name=APP_NAME,
                         version_date=VERSION_DATE)

@app.route('/game')
@app.route('/game/<session_id>')
def game(session_id=None):
    # 游戏主界面 - 通过URL参数或session获取session_id
    if session_id is None:
        session_id = session.get('session_id')

    if not session_id or session_id not in sessions:
        flash('请先选择一个场次', 'error')
        return redirect(url_for('index'))

    game_session = sessions[session_id]

    # 检查场次是否已被结束
    if not game_session.get('active', True):
        flash('该场次已经结束', 'error')
        return redirect(url_for('index'))

    # 准备玩家列表，按分数排序，包含player_id
    # 确保所有玩家都在scores字典中有条目
    for player in game_session['players']:
        if player not in game_session['scores']:
            game_session['scores'][player] = 0

    # 构建包含player_id的玩家列表
    players_with_ids = []
    for player_name in game_session['players']:
        player_id = get_player_by_name(player_name)
        score = game_session['scores'][player_name]
        players_with_ids.append({
            'name': player_name,
            'id': player_id,
            'score': score
        })

    # 按分数排序
    sorted_players = sorted(players_with_ids, key=lambda x: x['score'], reverse=True)

    # 准备最近玩家的信息（用于显示）
    recent_player_data = []
    for pid in recent_player_ids:
        player_name = get_player_name(pid)
        if player_name not in game_session['players']:  # 只显示不在当前场次的玩家
            recent_player_data.append({
                'id': pid,
                'name': player_name
            })

    return render_template(
        'game.html',
        session_id=session_id,
        session=game_session,
        score_options=DEFAULT_SCORE_OPTIONS,
        sorted_players=sorted_players,
        recent_players=recent_player_data,  # 传递包含ID的最近玩家列表
        app_version=APP_VERSION
    )



@app.route('/history')
def history():
    # 展示所有场次和分数历史
    sorted_sessions = sorted(
        sessions.items(),
        key=lambda x: x[1].get('timestamp', ''),
        reverse=True
    )

    # 计算全局玩家总分，包含player_id
    total_scores = defaultdict(int)
    for _, s in sessions.items():
        for p in s['players']:
            total_scores[p] += s['scores'][p]

    # 构建包含player_id的排行榜数据
    sorted_total_scores = []
    for player_name, score in total_scores.items():
        player_id = get_player_by_name(player_name)
        sorted_total_scores.append({
            'name': player_name,
            'id': player_id,
            'score': score
        })

    # 按分数排序
    sorted_total_scores.sort(key=lambda x: x['score'], reverse=True)

    # 为每个场次构建包含player_id的玩家数据
    sessions_with_player_ids = {}
    for sid, session_data in sorted_sessions:
        session_copy = session_data.copy()
        # 构建包含ID的玩家列表
        players_with_ids = []
        for player_name in session_data['players']:
            player_id = get_player_by_name(player_name)
            score = session_data['scores'].get(player_name, 0)
            players_with_ids.append({
                'name': player_name,
                'id': player_id,
                'score': score
            })

        # 按分数排序
        players_with_ids.sort(key=lambda x: x['score'], reverse=True)
        session_copy['players_with_ids'] = players_with_ids
        sessions_with_player_ids[sid] = session_copy

    return render_template('history.html',
                          sessions=sessions_with_player_ids,
                          total_scores=sorted_total_scores,
                          app_version=APP_VERSION)


@app.route('/end_session/<session_id>')
def end_session(session_id):
    # 结束当前场次（GET方式，兼容性保留）
    return end_session_post(session_id)

@app.route('/end_session/<session_id>', methods=['POST'])
def end_session_post(session_id):
    # 结束当前场次
    if session_id not in sessions:
        flash('场次不存在', 'error')
        return redirect(url_for('index'))

    # 获取用户时区偏移量（POST请求才有）
    timezone_offset = request.form.get('timezone_offset') if request.method == 'POST' else None
    try:
        timezone_offset_minutes = int(timezone_offset) if timezone_offset else None
    except (ValueError, TypeError):
        timezone_offset_minutes = None

    # 标记为非活跃
    sessions[session_id]['active'] = False
    sessions[session_id]['end_time'] = get_user_local_time(timezone_offset_minutes)

    # 保存数据
    save_data()

    flash('本场比赛已结束', 'success')
    return redirect(url_for('history'))

@app.route('/api/scores')
def api_scores():
    """提供API接口获取分数数据，方便扩展"""
    session_id = request.args.get('session_id')
    if session_id and session_id in sessions:
        return jsonify({
            'players': list(sessions[session_id]['players']),
            'scores': dict(sessions[session_id]['scores']),
            'records': sessions[session_id]['records']
        })
    else:
        return jsonify({'error': 'Invalid session ID'}), 400

@app.route('/add_player/<session_id>', methods=['POST'])
def add_player(session_id):
    global recent_player_ids
    # 在游戏中添加新玩家
    if session_id not in sessions:
        flash('场次不存在', 'error')
        return redirect(url_for('index'))

    game_session = sessions[session_id]

    # 检查场次是否已被结束
    if not game_session.get('active', True):
        flash('该场次已经结束', 'error')
        return redirect(url_for('index'))

    new_player_name = request.form['new_player_name'].strip()
    if not new_player_name:
        flash('玩家名称不能为空', 'error')
        return redirect(url_for('game', session_id=session_id))

    # 检查玩家是否已存在（按名字）
    if new_player_name in game_session['players'] or new_player_name in game_session['viewers']:
        flash('该用户名已存在', 'error')
        return redirect(url_for('game', session_id=session_id))

    # 获取用户时区偏移量
    timezone_offset = request.form.get('timezone_offset')
    try:
        timezone_offset_minutes = int(timezone_offset) if timezone_offset else None
    except (ValueError, TypeError):
        timezone_offset_minutes = None

    # 获取或创建玩家
    player_id = get_or_create_player(new_player_name, timezone_offset_minutes)

    # 添加玩家到场次
    game_session['player_ids'].add(player_id)
    game_session['players'].add(new_player_name)  # 为了兼容性保留
    game_session['scores'][new_player_name] = 0

    # 更新最近玩家列表
    if player_id not in recent_player_ids:
        recent_player_ids.append(player_id)
        # 只保留最近10个玩家
        if len(recent_player_ids) > 10:
            recent_player_ids = recent_player_ids[-10:]

    # 保存数据
    save_data()

    flash(f'玩家 "{new_player_name}" 添加成功', 'success')
    return redirect(url_for('game', session_id=session_id))

@app.route('/delete_session/<session_id>')
def delete_session(session_id):
    # 删除场次
    if session_id not in sessions:
        flash('场次不存在', 'error')
        return redirect(url_for('history'))

    session_name = sessions[session_id]['name']
    del sessions[session_id]

    # 保存数据
    save_data()

    flash(f'场次 "{session_name}" 已删除', 'success')
    return redirect(url_for('history'))

@app.route('/session_detail/<session_id>')
def session_detail(session_id):
    # 显示场次详情页
    if session_id not in sessions:
        flash('场次不存在', 'error')
        return redirect(url_for('index'))

    session_data = sessions[session_id]

    # 构建包含player_id的玩家列表并按分数排序
    players_with_ids = []
    for player_name in session_data['players']:
        player_id = get_player_by_name(player_name)
        score = session_data['scores'].get(player_name, 0)
        players_with_ids.append({
            'name': player_name,
            'id': player_id,
            'score': score
        })

    # 按分数排序
    sorted_players = sorted(players_with_ids, key=lambda x: x['score'], reverse=True)

    # 为记录添加玩家ID（如果需要）
    records_with_ids = []
    for record in session_data.get('records', []):
        record_copy = record.copy()
        if 'winner_id' not in record_copy and 'winner' in record_copy:
            record_copy['winner_id'] = get_player_by_name(record_copy['winner'])
        if 'loser_id' not in record_copy and 'loser' in record_copy:
            record_copy['loser_id'] = get_player_by_name(record_copy['loser'])
        records_with_ids.append(record_copy)

    return render_template('session_detail.html',
                         session_id=session_id,
                         session_data=session_data,
                         sorted_players=sorted_players,
                         records=records_with_ids,
                         app_version=APP_VERSION)

@app.route('/delete_record/<session_id>/<int:record_index>', methods=['POST'])
def delete_record(session_id, record_index):
    # 删除计分记录
    if session_id not in sessions:
        flash('场次不存在', 'error')
        return redirect(url_for('index'))

    game_session = sessions[session_id]

    # 检查场次是否已被结束
    if not game_session.get('active', True):
        flash('该场次已经结束，无法删除记录', 'error')
        return redirect(url_for('index'))

    # 验证记录索引
    if record_index < 0 or record_index >= len(game_session['records']):
        flash('无效的记录索引', 'error')
        return redirect(url_for('game', session_id=session_id))

    # 获取要删除的记录
    record_to_delete = game_session['records'][record_index]

    # 恢复分数（撤销这条记录的分数变化）
    winner = record_to_delete['winner']
    loser = record_to_delete['loser']
    score = record_to_delete['score']

    # 撤销分数变化
    game_session['scores'][winner] -= score
    game_session['scores'][loser] += score

    # 删除记录
    del game_session['records'][record_index]

    # 保存数据
    save_data()

    flash(f'已删除记录：{winner} 胜 {loser} ({score}分)', 'success')
    return redirect(url_for('game', session_id=session_id))

@app.route('/add_score/<session_id>', methods=['POST'])
def add_score(session_id):
    # 记分功能
    if session_id not in sessions:
        flash('场次不存在', 'error')
        return redirect(url_for('index'))

    game_session = sessions[session_id]

    # 检查场次是否已被结束
    if not game_session.get('active', True):
        flash('该场次已经结束', 'error')
        return redirect(url_for('index'))

    winner = request.form['winner']
    loser = request.form['loser']
    score = int(request.form['score'])

    # 获取用户时区偏移量
    timezone_offset = request.form.get('timezone_offset')
    try:
        timezone_offset_minutes = int(timezone_offset) if timezone_offset else None
    except (ValueError, TypeError):
        timezone_offset_minutes = None

    # 验证
    if winner == loser:
        flash('胜者和败者不能是同一个玩家', 'error')
    elif winner not in game_session['players'] or loser not in game_session['players']:
        flash('选择的玩家不在当前场次中', 'error')
    else:
        # 获取玩家ID
        winner_id = get_player_by_name(winner)
        loser_id = get_player_by_name(loser)

        # 记录本次计分
        record_data = {
            'winner': winner,
            'loser': loser,
            'winner_id': winner_id,
            'loser_id': loser_id,
            'score': score,
            'timestamp': get_user_local_time(timezone_offset_minutes)
        }
        game_session['records'].append(record_data)

        # 更新分数
        game_session['scores'][winner] += score
        game_session['scores'][loser] -= score

        # 保存数据
        save_data()
        flash('成功记录分数', 'success')

    return redirect(url_for('game', session_id=session_id))

@app.route('/add_special_score/<session_id>', methods=['POST'])
def add_special_score(session_id):
    # 处理特殊分数（14分和20分）的记分功能
    if session_id not in sessions:
        flash('场次不存在', 'error')
        return redirect(url_for('index'))

    game_session = sessions[session_id]

    # 检查场次是否已被结束
    if not game_session.get('active', True):
        flash('该场次已经结束', 'error')
        return redirect(url_for('index'))

    winner = request.form.get('winner')
    losers = request.form.getlist('losers')  # 获取多个败者
    total_score = int(request.form.get('score', 0))

    # 验证输入
    if not winner or not losers or total_score not in [14, 20]:
        flash('参数错误', 'error')
        return redirect(url_for('game', session_id=session_id))

    if winner in losers:
        flash('胜者不能同时是败者', 'error')
        return redirect(url_for('game', session_id=session_id))

    if len(losers) != 2:
        flash('特殊分数需要选择2个败者', 'error')
        return redirect(url_for('game', session_id=session_id))

    # 检查所有玩家是否存在
    all_players = [winner] + losers
    for player in all_players:
        if player not in game_session['players']:
            flash(f'玩家 {player} 不在当前场次中', 'error')
            return redirect(url_for('game', session_id=session_id))

    # 计算分数
    half_score = total_score // 2

    # 获取用户时区偏移量
    timezone_offset = request.form.get('timezone_offset')
    try:
        timezone_offset_minutes = int(timezone_offset) if timezone_offset else None
    except (ValueError, TypeError):
        timezone_offset_minutes = None

    # 获取玩家ID
    winner_id = get_player_by_name(winner)
    loser_ids = [get_player_by_name(loser) for loser in losers]

    # 记录第一笔：胜者得分，第一个败者失分
    record_data_1 = {
        'winner': winner,
        'loser': losers[0],
        'winner_id': winner_id,
        'loser_id': loser_ids[0],
        'score': half_score,
        'timestamp': get_user_local_time(timezone_offset_minutes),
        'special_score_part': f'1/2 (总分{total_score})'
    }
    game_session['records'].append(record_data_1)

    # 记录第二笔：胜者得分，第二个败者失分
    record_data_2 = {
        'winner': winner,
        'loser': losers[1],
        'winner_id': winner_id,
        'loser_id': loser_ids[1],
        'score': half_score,
        'timestamp': get_user_local_time(timezone_offset_minutes),
        'special_score_part': f'2/2 (总分{total_score})'
    }
    game_session['records'].append(record_data_2)

    # 更新分数
    game_session['scores'][winner] += total_score
    game_session['scores'][losers[0]] -= half_score
    game_session['scores'][losers[1]] -= half_score

    # 保存数据
    save_data()
    flash(f'成功记录特殊分数：{winner} +{total_score}，{losers[0]} -{half_score}，{losers[1]} -{half_score}', 'success')

    return redirect(url_for('game', session_id=session_id))

@app.route('/player/<player_id>')
def player_detail(player_id):
    """玩家详情页面"""
    if player_id not in players:
        flash('玩家不存在', 'error')
        return redirect(url_for('index'))

    player = players[player_id]

    # 收集这个玩家的所有对战记录
    player_records = []
    for session_id, session_data in sessions.items():
        for record in session_data.get('records', []):
            if (record.get('winner_id') == player_id or record.get('loser_id') == player_id or
                record.get('winner') == player['name'] or record.get('loser') == player['name']):

                # 确保记录有player_id信息
                if 'winner_id' not in record and 'winner' in record:
                    record['winner_id'] = get_or_create_player(record['winner'])
                if 'loser_id' not in record and 'loser' in record:
                    record['loser_id'] = get_or_create_player(record['loser'])

                player_records.append({
                    'session_name': session_data.get('name', '未命名场次'),
                    'session_id': session_id,
                    'record': record,
                    'is_winner': (record.get('winner_id') == player_id or record.get('winner') == player['name']),
                    'opponent_id': record.get('loser_id') if (record.get('winner_id') == player_id or record.get('winner') == player['name']) else record.get('winner_id'),
                    'opponent_name': get_player_name(record.get('loser_id')) if (record.get('winner_id') == player_id or record.get('winner') == player['name']) else get_player_name(record.get('winner_id')),
                    'score': record.get('score', 0)
                })

    # 按时间排序（最新的在前面）
    player_records.sort(key=lambda x: x['record'].get('timestamp', ''), reverse=True)

    # 计算统计数据
    stats = {
        'total_games': len(player_records),
        'wins': len([r for r in player_records if r['is_winner']]),
        'losses': len([r for r in player_records if not r['is_winner']]),
        'total_score': sum(r['score'] if r['is_winner'] else -r['score'] for r in player_records)
    }
    stats['win_rate'] = (stats['wins'] / stats['total_games'] * 100) if stats['total_games'] > 0 else 0

    # 对手统计
    opponent_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total_score': 0})
    for record in player_records:
        opponent_id = record['opponent_id']
        if opponent_id:
            if record['is_winner']:
                opponent_stats[opponent_id]['wins'] += 1
                opponent_stats[opponent_id]['total_score'] += record['score']
            else:
                opponent_stats[opponent_id]['losses'] += 1
                opponent_stats[opponent_id]['total_score'] -= record['score']

    # 转换对手统计为列表，包含名字
    opponent_list = []
    for opponent_id, stat in opponent_stats.items():
        opponent_list.append({
            'id': opponent_id,
            'name': get_player_name(opponent_id),
            'wins': stat['wins'],
            'losses': stat['losses'],
            'total_games': stat['wins'] + stat['losses'],
            'win_rate': (stat['wins'] / (stat['wins'] + stat['losses']) * 100) if (stat['wins'] + stat['losses']) > 0 else 0,
            'total_score': stat['total_score']
        })

    # 按总对局数排序
    opponent_list.sort(key=lambda x: x['total_games'], reverse=True)

    return render_template(
        'player_detail.html',
        player=player,
        player_id=player_id,
        stats=stats,
        records=player_records[:50],  # 只显示最近50场
        opponents=opponent_list,
        app_version=APP_VERSION
    )

@app.route('/player/<player_id>/rename', methods=['POST'])
def rename_player(player_id):
    """重命名玩家"""
    if player_id not in players:
        flash('玩家不存在', 'error')
        return redirect(url_for('index'))

    new_name = request.form.get('new_name', '').strip()
    if not new_name:
        flash('新名字不能为空', 'error')
        return redirect(url_for('player_detail', player_id=player_id))

    # 检查新名字是否已被其他玩家使用
    existing_player_id = get_player_by_name(new_name)
    if existing_player_id and existing_player_id != player_id:
        flash('该名字已被其他玩家使用', 'error')
        return redirect(url_for('player_detail', player_id=player_id))

    # 获取用户时区偏移量
    timezone_offset = request.form.get('timezone_offset')
    try:
        timezone_offset_minutes = int(timezone_offset) if timezone_offset else None
    except (ValueError, TypeError):
        timezone_offset_minutes = None

    old_name = players[player_id]['name']

    # 更新玩家名字
    update_player_name(player_id, new_name, timezone_offset_minutes)

    # 更新所有场次中的玩家名字（为了兼容性）
    for session_data in sessions.values():
        if old_name in session_data.get('players', set()):
            session_data['players'].remove(old_name)
            session_data['players'].add(new_name)
            # 更新分数记录
            if old_name in session_data.get('scores', {}):
                session_data['scores'][new_name] = session_data['scores'][old_name]
                del session_data['scores'][old_name]

        # 更新记录中的名字（为了显示）
        for record in session_data.get('records', []):
            if record.get('winner') == old_name:
                record['winner'] = new_name
            if record.get('loser') == old_name:
                record['loser'] = new_name

    # 保存数据
    save_data()

    flash(f'玩家名字已从 "{old_name}" 更改为 "{new_name}"', 'success')
    return redirect(url_for('player_detail', player_id=player_id))

if __name__ == '__main__':
    # 加载历史数据
    sessions = load_data()

    # 输出数据存储位置信息
    data_file = get_data_file_path()
    is_azure = os.environ.get('WEBSITE_SITE_NAME') is not None
    print(f"")
    print(f"🎱 {APP_NAME} {APP_VERSION}")
    print(f"📊 数据存储位置: {data_file}")
    print(f"☁️  Azure环境: {'是' if is_azure else '否'}")
    print(f"📝 已加载 {len(sessions)} 个场次, {len(players)} 个玩家")
    print(f"")

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true')
