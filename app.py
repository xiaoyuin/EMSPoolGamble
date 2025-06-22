from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from collections import defaultdict
import uuid
import datetime
import json
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key_for_testing')  # 用于会话管理

# 内存数据结构，后期可替换为数据库
sessions = {}  # {session_id: {players, viewers, records, scores, timestamp, ...}}

# 默认分数选项（只有正整数1-10）
DEFAULT_SCORE_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

# 全局变量存储最近添加的玩家名字
recent_players = []

# 尝试从文件加载历史数据
def load_data():
    global recent_players
    try:
        if os.path.exists('data.json'):
            with open('data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 转换回set类型
                for sid, s in data.items():
                    s['players'] = set(s['players'])
                    s['viewers'] = set(s['viewers'])
                    # 为旧数据添加默认场次名称
                    if 'name' not in s:
                        s['name'] = f"场次 #{len(data) - list(data.keys()).index(sid)}"
                    # 兼容旧数据：将rounds改为records
                    if 'rounds' in s and 'records' not in s:
                        s['records'] = s['rounds']
                        del s['rounds']
                    if 'records' not in s:
                        s['records'] = []

                    # 确保scores是defaultdict类型，并且所有玩家都有分数条目
                    if not isinstance(s['scores'], defaultdict):
                        scores_dict = defaultdict(int)
                        scores_dict.update(s['scores'])
                        s['scores'] = scores_dict

                    # 确保所有玩家都在scores中有条目
                    for player in s['players']:
                        if player not in s['scores']:
                            s['scores'][player] = 0

                # 收集最近的玩家名字
                all_players = set()
                for s in data.values():
                    all_players.update(s['players'])
                recent_players = list(all_players)[-10:]  # 最多保留10个最近玩家

                return data
        return {}
    except Exception as e:
        print(f"加载数据失败: {e}")
        return {}

# 保存数据到文件
def save_data():
    try:
        # 将set转换为list以便JSON序列化
        data_copy = {}
        for sid, s in sessions.items():
            s_copy = s.copy()
            s_copy['players'] = list(s['players'])
            s_copy['viewers'] = list(s['viewers'])
            data_copy[sid] = s_copy

        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(data_copy, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存数据失败: {e}")

# 尝试加载历史数据
sessions = load_data()

@app.route('/', methods=['GET', 'POST'])
def index():
    # 进入首页，显示当前进行中的场次列表
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create_session':
            # 创建新场次
            session_name = request.form['session_name'].strip()
            if not session_name:
                flash('场次名称不能为空', 'error')
                return redirect(url_for('index'))

            session_id = str(uuid.uuid4())
            sessions[session_id] = {
                'name': session_name,
                'players': set(),
                'viewers': set(),
                'records': [],  # 改为records存储计分记录
                'scores': defaultdict(int),
                'active': True,
                'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            # 保存数据
            save_data()
            flash(f'场次 "{session_name}" 创建成功', 'success')
            return redirect(url_for('index'))

        elif action == 'join_session':
            # 加入现有场次
            username = request.form['username'].strip()
            role = request.form['role']  # player/viewer
            session_id = request.form['session_id']

            # 验证用户名
            if not username:
                flash('用户名不能为空', 'error')
                return redirect(url_for('index'))

            if session_id not in sessions:
                flash('场次不存在', 'error')
                return redirect(url_for('index'))

            # 注册用户
            if role == 'player':
                sessions[session_id]['players'].add(username)
                # 确保新玩家在scores字典中有条目
                if username not in sessions[session_id]['scores']:
                    sessions[session_id]['scores'][username] = 0
            else:
                sessions[session_id]['viewers'].add(username)

            session['username'] = username
            session['role'] = role
            session['session_id'] = session_id

            # 记录用户名到浏览器缓存
            session['last_username'] = username

            # 保存数据
            save_data()

            return redirect(url_for('game'))

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

    # 获取上次登录的用户名
    last_username = session.get('last_username', '')

    return render_template('index.html',
                         active_sessions=sorted_active_sessions,
                         ended_sessions=sorted_ended_sessions,
                         last_username=last_username)

@app.route('/game', methods=['GET', 'POST'])
def game():
    # 游戏主界面
    session_id = session.get('session_id')
    username = session.get('username')
    role = session.get('role')

    if not session_id or session_id not in sessions:
        return redirect(url_for('index'))

    game_session = sessions[session_id]

    if request.method == 'POST' and role == 'player':
        winner = request.form['winner']
        loser = request.form['loser']
        score = int(request.form['score'])

        # 验证
        if winner == loser:
            flash('胜者和败者不能是同一个玩家', 'error')
        elif winner not in game_session['players'] or loser not in game_session['players']:
            flash('选择的玩家不在当前场次中', 'error')
        else:
            # 记录本次计分
            record_data = {
                'winner': winner,
                'loser': loser,
                'score': score,
                'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            game_session['records'].append(record_data)

            # 更新分数
            game_session['scores'][winner] += score
            game_session['scores'][loser] -= score

            # 保存数据
            save_data()
            flash('成功记录分数', 'success')

    # 准备玩家列表，按分数排序
    # 确保所有玩家都在scores字典中有条目
    for player in game_session['players']:
        if player not in game_session['scores']:
            game_session['scores'][player] = 0

    sorted_players = sorted(
        [(p, game_session['scores'][p]) for p in game_session['players']],
        key=lambda x: x[1],
        reverse=True
    )

    return render_template(
        'game.html',
        session=game_session,
        username=username,
        role=role,
        score_options=DEFAULT_SCORE_OPTIONS,
        sorted_players=sorted_players,
        recent_players=recent_players,  # 传递最近玩家列表
        default_loser=next((p for p in game_session['players'] if p != username), '')
    )



@app.route('/history')
def history():
    # 展示所有场次和分数历史
    sorted_sessions = sorted(
        sessions.items(),
        key=lambda x: x[1].get('timestamp', ''),
        reverse=True
    )

    # 计算全局玩家总分
    total_scores = defaultdict(int)
    for _, s in sessions.items():
        for p in s['players']:
            total_scores[p] += s['scores'][p]

    # 按分数排序
    sorted_total_scores = sorted(
        [(p, score) for p, score in total_scores.items()],
        key=lambda x: x[1],
        reverse=True
    )

    return render_template('history.html',
                          sessions=dict(sorted_sessions),
                          total_scores=sorted_total_scores)

@app.route('/logout')
def logout():
    session.clear()
    flash('您已成功退出', 'success')
    return redirect(url_for('index'))

@app.route('/end_session')
def end_session():
    # 结束当前场次
    session_id = session.get('session_id')
    username = session.get('username')
    role = session.get('role')

    if not session_id or session_id not in sessions:
        return redirect(url_for('index'))

    # 验证权限
    if role != 'player':
        flash('只有玩家可以结束场次', 'error')
        return redirect(url_for('game'))

    # 标记为非活跃
    sessions[session_id]['active'] = False
    sessions[session_id]['end_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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

@app.route('/add_player', methods=['POST'])
def add_player():
    global recent_players
    # 在游戏中添加新玩家
    session_id = session.get('session_id')
    username = session.get('username')
    role = session.get('role')

    if not session_id or session_id not in sessions:
        return redirect(url_for('index'))

    # 验证权限
    if role != 'player':
        flash('只有玩家可以添加新玩家', 'error')
        return redirect(url_for('game'))

    new_player_name = request.form['new_player_name'].strip()
    if not new_player_name:
        flash('玩家名称不能为空', 'error')
        return redirect(url_for('game'))

    game_session = sessions[session_id]

    # 检查玩家是否已存在
    if new_player_name in game_session['players'] or new_player_name in game_session['viewers']:
        flash('该用户名已存在', 'error')
        return redirect(url_for('game'))

    # 添加玩家
    game_session['players'].add(new_player_name)
    game_session['scores'][new_player_name] = 0

    # 更新最近玩家列表
    if new_player_name not in recent_players:
        recent_players.append(new_player_name)
        # 只保留最近10个玩家
        if len(recent_players) > 10:
            recent_players = recent_players[-10:]

    # 保存数据
    save_data()

    flash(f'玩家 "{new_player_name}" 添加成功', 'success')
    return redirect(url_for('game'))

@app.route('/delete_session/<session_id>')
def delete_session(session_id):
    # 删除场次
    username = session.get('username')
    role = session.get('role')

    if session_id not in sessions:
        flash('场次不存在', 'error')
        return redirect(url_for('index'))

    # 验证权限：只有玩家才能删除场次
    if role != 'player' or username not in sessions[session_id]['players']:
        flash('只有该场次的玩家才能删除场次', 'error')
        return redirect(url_for('index'))

    session_name = sessions[session_id]['name']
    del sessions[session_id]

    # 如果删除的是当前场次，清除session
    if session.get('session_id') == session_id:
        session.pop('session_id', None)

    # 保存数据
    save_data()

    flash(f'场次 "{session_name}" 已删除', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true')
