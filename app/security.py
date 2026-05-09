"""
安全模块 - 防止恶意访问和操作
"""
import os
import secrets
from functools import wraps
from urllib.parse import urlparse
from flask import request, session, flash, redirect, url_for, render_template_string


# 管理员密码（从环境变量获取，如果没有则使用默认值）
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# 生成CSRF token的密钥
CSRF_SECRET_KEY = os.environ.get('CSRF_SECRET_KEY', 'csrf_secret_key_for_dev')

# IP白名单（可选，从环境变量获取）
ALLOWED_IPS = os.environ.get('ALLOWED_IPS', '').split(',') if os.environ.get('ALLOWED_IPS') else []


def generate_csrf_token():
    """生成CSRF token"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)
    return session['csrf_token']


def validate_csrf_token(token):
    """验证CSRF token"""
    return token and session.get('csrf_token') == token


def check_ip_whitelist():
    """检查IP白名单（如果设置了的话）"""
    if not ALLOWED_IPS or not ALLOWED_IPS[0]:  # 如果没有设置IP白名单，则跳过检查
        return True
    
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', ''))
    # 处理代理情况，取第一个IP
    if ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()
    
    return client_ip in ALLOWED_IPS


def require_admin_auth(f):
    """装饰器：要求管理员认证"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查IP白名单
        if not check_ip_whitelist():
            flash('访问被拒绝：IP地址不在白名单中', 'error')
            return redirect(url_for('index'))
        
        # 检查管理员认证状态
        if not session.get('admin_authenticated'):
            # 存储referrer信息
            session['pending_admin_operation'] = {
                'referrer': request.referrer or url_for('index')
            }
            # 显示密码输入页面
            return render_admin_login_form()
        
        return f(*args, **kwargs)
    return decorated_function


def require_csrf_protection(f):
    """装饰器：要求CSRF保护"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            token = request.form.get('csrf_token')
            if not validate_csrf_token(token):
                flash('安全验证失败，请重试', 'error')
                return redirect(request.referrer or url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


def render_admin_login_form():
    """渲染管理员登录表单"""
    form_html = '''
    <!DOCTYPE html>
    <html lang="zh">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>管理员验证 - EMS Pool</title>
        <style>
            body { 
                font-family: sans-serif; 
                max-width: 400px; 
                margin: 100px auto; 
                padding: 2em; 
                background-color: #f0f2f5; 
            }
            .auth-card { 
                background: #ffffff; 
                border-radius: 10px; 
                padding: 2em; 
                box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
                text-align: center;
            }
            .title { 
                color: #1890ff; 
                margin-bottom: 1em; 
                font-size: 1.5em;
            }
            .form-group { 
                margin-bottom: 1em; 
                text-align: left;
            }
            label { 
                display: block; 
                margin-bottom: 0.5em; 
                color: #333; 
            }
            input[type="password"] { 
                width: 100%; 
                padding: 0.8em; 
                border: 1px solid #d9d9d9; 
                border-radius: 5px; 
                font-size: 1em;
                box-sizing: border-box;
            }
            .btn { 
                width: 100%;
                padding: 0.8em; 
                border: none; 
                border-radius: 5px; 
                cursor: pointer; 
                font-size: 1em; 
                background: #1890ff; 
                color: white;
                margin-top: 1em;
            }
            .btn:hover { 
                background: #40a9ff; 
            }
            .warning { 
                color: #ff4d4f; 
                font-size: 0.9em; 
                margin-top: 1em;
            }
            .back-link { 
                margin-top: 2em; 
            }
            .back-link a { 
                color: #1890ff; 
                text-decoration: none; 
            }
            .back-link a:hover { 
                text-decoration: underline; 
            }
        </style>
    </head>
    <body>
        <div class="auth-card">
            <h2 class="title">🔒 管理员验证</h2>
            
            <p>此操作需要管理员权限，请输入管理员密码：</p>
            
            <form method="post" action="{{ url_for('admin_login') }}">
                <div class="form-group">
                    <label for="password">管理员密码：</label>
                    <input type="password" id="password" name="password" required autocomplete="current-password">
                </div>
                
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                
                <button type="submit" class="btn">验证身份</button>
            </form>
            
            <div class="warning">
                ⚠️ 为了防止恶意访问，关键操作需要管理员验证
            </div>
            
            <div class="back-link">
                <a href="{{ url_for('index') }}">← 取消操作，返回首页</a>
            </div>
        </div>
    </body>
    </html>
    '''
    
    return render_template_string(form_html, csrf_token=generate_csrf_token)


def register_security_routes(app):
    """注册安全相关路由"""
    
    @app.route('/admin_login', methods=['POST'])
    def admin_login():
        """处理管理员登录"""
        password = request.form.get('password', '')
        
        # 验证CSRF token
        if not validate_csrf_token(request.form.get('csrf_token')):
            flash('安全验证失败，请重试', 'error')
            return redirect(url_for('index'))
        
        # 验证密码
        if password == ADMIN_PASSWORD:
            session['admin_authenticated'] = True
            session.permanent = True  # 使session持久化
            
            # 检查是否有待执行的操作
            operation_info = session.pop('pending_admin_operation', None)  
            if operation_info:
                referrer = operation_info.get('referrer', url_for('index'))
                flash('✅ 管理员身份验证成功！现在可以重新执行操作了。', 'success')
                return redirect(referrer)
            else:
                flash('管理员身份验证成功', 'success')
                return redirect(url_for('index'))
        else:
            flash('密码错误', 'error')
            return redirect(url_for('index'))
    
    @app.route('/admin_logout')
    def admin_logout():
        """管理员登出"""
        session.pop('admin_authenticated', None)
        flash('已退出管理员模式', 'success')
        return redirect(url_for('index'))
    
    # 添加模板全局函数
    @app.template_global()
    def csrf_token():
        """在模板中生成CSRF token"""
        return generate_csrf_token()
    
    @app.template_global()
    def is_admin_authenticated():
        """检查是否已通过管理员认证"""
        return session.get('admin_authenticated', False)


def get_security_status():
    """获取安全状态信息"""
    return {
        'admin_authenticated': session.get('admin_authenticated', False),
        'csrf_enabled': True,
        'ip_whitelist_enabled': bool(ALLOWED_IPS and ALLOWED_IPS[0]),
        'allowed_ips': ALLOWED_IPS if ALLOWED_IPS and ALLOWED_IPS[0] else [],
        'admin_password_set': ADMIN_PASSWORD != 'admin123'
    }
