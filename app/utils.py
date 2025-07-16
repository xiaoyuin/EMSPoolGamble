"""
时间处理和工具函数模块
"""
import datetime


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
