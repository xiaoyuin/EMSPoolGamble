"""EMS Pool application entry point."""
import os

from flask import Blueprint, Flask, abort, g

from app import APP_NAME, APP_VERSION, VERSION_DATE
from app.achievement_routes import register_achievement_routes
from app.database import DatabaseManager, db
from app.game_routes import register_game_routes
from app.main_routes import register_main_routes
from app.models import get_data_file_path, get_all_sessions, init_data
from app.organization_routes import register_organization_routes
from app.player_routes import register_player_routes
from app.security import register_security_globals, register_security_routes
from app.tournament_routes import register_tournament_routes


def _install_tenant_resolution(tenant):
    @tenant.url_value_preprocessor
    def resolve_organization(endpoint, values):
        slug = (values or {}).pop('org_slug', '').lower()
        organization = db.get_organization_by_slug(slug)
        if organization is None:
            abort(404)
        g.organization = organization

    @tenant.url_defaults
    def inject_organization_slug(endpoint, values):
        if endpoint.startswith('tenant.') and 'org_slug' not in values:
            organization = getattr(g, 'organization', None)
            if organization:
                values['org_slug'] = organization['slug']


def create_app(test_config=None):
    """Build the Flask application, optionally targeting an isolated test database."""
    application = Flask(__name__)
    application.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev_secret_key_for_testing'),
        PERMANENT_SESSION_LIFETIME=604800,
    )
    if test_config:
        application.config.update(test_config)

    database = DatabaseManager(application.config.get('DATABASE_PATH'))
    application.extensions['database'] = database
    with application.app_context():
        init_data()

    tenant = Blueprint('tenant', __name__, url_prefix='/o/<org_slug>')
    _install_tenant_resolution(tenant)
    register_main_routes(tenant)
    register_game_routes(tenant)
    register_player_routes(tenant)
    register_achievement_routes(tenant)
    register_tournament_routes(tenant)
    register_security_routes(tenant)
    application.register_blueprint(tenant)

    register_organization_routes(application)
    register_security_globals(application)
    return application


# Production WSGI globals.
application = create_app()
app = application


if __name__ == '__main__':
    data_file = get_data_file_path()
    is_azure = os.environ.get('WEBSITE_SITE_NAME') is not None
    database = app.extensions['database']
    ems_org_id = database.get_ems_organization()['org_id']
    all_sessions = database.get_all_sessions(ems_org_id)
    all_players = database.get_all_players(ems_org_id)
    print(f'\n{APP_NAME} {APP_VERSION}')
    print(f'数据存储位置: SQLite数据库 ({database.db_path})')
    print(f'Azure环境: {"是" if is_azure else "否"}')
    print(f'已加载 {len(all_sessions)} 个场次, {len(all_players)} 个玩家\n')
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true')
