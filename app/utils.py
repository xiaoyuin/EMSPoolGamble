"""
时间处理和工具函数模块
"""
import datetime
from collections import defaultdict


def compute_pairwise_edges(records):
    """从一场比赛的 records 列表算两两玩家之间的净得分。

    每条 record 按 (胜者数 × 败者数) 平均分摊分数：
      - 1v1 score=10: 胜者从败者身上 +10
      - 1v2 score=14: 胜者从每个败者身上 +7
      - 2v1 score=8:  每个胜者从败者身上 +4
    最后合并成有向边（from = 净赢方，to = 净输方，net > 0）。
    净分为 0 的 pair 忽略。
    """
    flow = defaultdict(float)
    for r in records:
        winners = r.get('winners') or []
        losers = r.get('losers') or []
        if not winners or not losers:
            continue
        try:
            score = float(r.get('score') or 0)
        except (TypeError, ValueError):
            continue
        if score <= 0:
            continue
        share = score / (len(winners) * len(losers))
        for w in winners:
            for l in losers:
                w_id, l_id = w.get('id'), l.get('id')
                if not w_id or not l_id or w_id == l_id:
                    continue
                flow[(w_id, l_id)] += share

    edges = []
    seen = set()
    for (a, b), val in flow.items():
        key = tuple(sorted([a, b]))
        if key in seen:
            continue
        seen.add(key)
        net = val - flow.get((b, a), 0)
        if net > 0:
            edges.append({'from': a, 'to': b, 'net': round(net, 1)})
        elif net < 0:
            edges.append({'from': b, 'to': a, 'net': round(-net, 1)})
    return edges


def get_utc_timestamp():
    """
    获取UTC时间戳字符串，用于统一存储
    :return: UTC时间戳字符串
    """
    return datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')


def get_utc_iso_timestamp():
    """
    获取ISO格式的UTC时间戳，便于前端处理
    :return: ISO格式的UTC时间戳
    """
    return datetime.datetime.utcnow().isoformat() + 'Z'


def get_user_local_time(timezone_offset_minutes=None):
    """
    获取用户本地时间（保留兼容性）
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


def generate_session_name():
    """
    生成自动场次名称（使用服务器本地时间作为降级处理）
    """
    now = datetime.datetime.now()  # 使用服务器本地时间
    month = now.month
    day = now.day
    hour = now.hour

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
