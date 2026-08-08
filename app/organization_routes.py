"""Root organization portal and safe gateways for pre-tenancy read-only URLs."""
from pathlib import PurePosixPath
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

from flask import flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from .database import db
from .security import generate_csrf_token, validate_csrf_token

_ALLOWED_QUERY = {
    '/history': {'search', 'month', 'start_date', 'end_date'},
    '/player': {'month', 'start_date', 'end_date'},
}


def _safe_legacy_path(value):
    """Return a normalized, known read-only legacy location, else None."""
    if not value or not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith('//') or '\\' in value:
        return None
    path = unquote(parsed.path)
    if not path.startswith('/') or '..' in PurePosixPath(path).parts:
        return None
    segments = [part for part in path.split('/') if part]
    if not segments:
        return '/'
    first = segments[0]
    # Exact public read-only route shapes. Mutating actions and API paths are absent.
    permitted = (
        (first == 'history' and len(segments) == 1)
        or (first == 'game' and len(segments) <= 2)
        or (first == 'player' and len(segments) == 2)
        or (first == 'session_detail' and len(segments) == 2)
        or (first == 'achievements' and len(segments) == 1)
        or (first == 'achievement' and len(segments) == 2)
        or (first == 'tournament' and len(segments) in (1, 2, 4)
            and (len(segments) != 4 or segments[2] == 'match'))
        or (first == 'admin' and len(segments) == 1)
    )
    if not permitted:
        return None
    prefix = '/' + first
    allowed = _ALLOWED_QUERY.get(prefix, set())
    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
             if key in allowed]
    return path + (('?' + urlencode(query)) if query else '')


def _portal(continuation=None):
    return render_template('organization_portal.html', continuation=_safe_legacy_path(continuation))


def _select_organization(value):
    return db.get_organization_by_name_or_slug(value or '')


def _redirect_to_org(organization, continuation=None):
    path = _safe_legacy_path(continuation) or '/'
    return redirect(f"/o/{quote(organization['slug'])}{path}")


def register_organization_routes(app):
    @app.route('/', methods=['GET'])
    def organization_portal():
        return _portal(request.args.get('continue'))

    @app.route('/organizations/select', methods=['POST'])
    def select_organization():
        if not validate_csrf_token(request.form.get('csrf_token')):
            flash('安全验证失败，请重试', 'error')
            return redirect(url_for('organization_portal'))
        organization = _select_organization(request.form.get('organization', ''))
        if not organization:
            flash('未找到该组织，请核对名称或组织链接', 'error')
            return _portal(request.form.get('continue'))
        return _redirect_to_org(organization, request.form.get('continue'))

    @app.route('/organizations/continue', methods=['POST'])
    def continue_organization():
        if not validate_csrf_token(request.form.get('csrf_token')):
            flash('安全验证失败，请重试', 'error')
            return redirect(url_for('organization_portal'))
        organization = _select_organization(request.form.get('organization', ''))
        continuation = _safe_legacy_path(request.form.get('continue'))
        if not organization:
            flash('未找到该组织，请核对名称或组织链接', 'error')
            return _portal(continuation)
        return _redirect_to_org(organization, continuation)

    @app.route('/organizations/new', methods=['GET', 'POST'])
    def new_organization():
        if request.method == 'GET':
            return render_template('organization_new.html')
        if not validate_csrf_token(request.form.get('csrf_token')):
            flash('安全验证失败，请重试', 'error')
            return redirect(url_for('new_organization'))
        name = request.form.get('name', '')
        password = request.form.get('password', '')
        confirmation = request.form.get('password_confirm', '')
        if password != confirmation:
            flash('两次输入的管理员密码不一致', 'error')
            return render_template('organization_new.html')
        if not 12 <= len(password) <= 128:
            flash('管理员密码长度必须为 12 到 128 个字符', 'error')
            return render_template('organization_new.html')
        try:
            organization = db.create_organization(name, generate_password_hash(password))
        except (ValueError, RuntimeError) as exc:
            flash(str(exc), 'error')
            return render_template('organization_new.html')
        # New organization creator is logged in only for this organization.
        from flask import session
        session['organization_admin_org_id'] = organization['org_id']
        session.pop('super_admin_authenticated', None)
        session.pop('admin_authenticated', None)
        session.permanent = True
        flash('组织已创建，你现在是该组织的管理员', 'success')
        return _redirect_to_org(organization)

    def legacy_gateway(path=''):
        suffix = '/' + path if path else ''
        return _portal(request.path + (('?' + request.query_string.decode()) if request.query_string else ''))

    # Explicit GET-only legacy gateways; old POST mutation paths intentionally do not exist.
    for rule in (
        '/history', '/game', '/game/<path:path>', '/player/<path:path>',
        '/session_detail/<path:path>', '/achievements', '/achievement/<path:path>',
        '/tournament', '/tournament/<path:path>', '/admin',
    ):
        app.add_url_rule(rule, endpoint='legacy_' + rule.replace('/', '_').replace('<path:path>', 'path').strip('_'),
                         view_func=legacy_gateway, methods=['GET'])
