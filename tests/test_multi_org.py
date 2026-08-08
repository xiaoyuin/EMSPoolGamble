"""Regression coverage for multi-organization tenancy.

This module deliberately selects a private temporary DATABASE_PATH before loading the
WSGI module: importing app.py creates the production-style global application.
"""
import importlib.util
import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
IMPORT_DIR = tempfile.TemporaryDirectory(prefix="ems-pool-test-import-")
os.environ["DATABASE_PATH"] = str(Path(IMPORT_DIR.name) / "bootstrap.db")
os.environ["ADMIN_PASSWORD"] = "super-secret-test-password"
sys.path.insert(0, str(ROOT))

from app.database import DatabaseManager, db
from app.tenancy import (EMS_ORG_ID, TENANCY_MIGRATION_VERSION, generate_organization_slug,
                         normalize_name, validate_organization_name)
from app import tournament

_wsgi_spec = importlib.util.spec_from_file_location("ems_pool_wsgi_test", ROOT / "app.py")
wsgi = importlib.util.module_from_spec(_wsgi_spec)
_wsgi_spec.loader.exec_module(wsgi)


class TempDatabaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ems-pool-multi-org-")
        self.path = str(Path(self.tmp.name) / "tenant.db")
        self.manager = DatabaseManager(self.path)
        # Tournament functions intentionally use the shared model manager.
        self.original_global_path = db.db_path
        db.db_path = self.path

    def tearDown(self):
        db.db_path = self.original_global_path
        self.tmp.cleanup()

    def create_org(self, name):
        return self.manager.create_organization(name, "pbkdf2:sha256:600000$test$hash")

    def seed_session(self, org_id, names=("Alice", "Bob", "Carol", "Dan")):
        ids = {name: self.manager.create_player(org_id, name) for name in names}
        session_id = self.manager.create_session(org_id, "2026-08-08 session")
        for player_id in ids.values():
            self.assertTrue(self.manager.add_player_to_session(org_id, session_id, player_id))
        return session_id, ids


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ems-pool-legacy-")
        self.path = str(Path(self.tmp.name) / "legacy.db")

    def tearDown(self):
        self.tmp.cleanup()

    def legacy_fixture(self, collision=False):
        conn = sqlite3.connect(self.path)
        conn.executescript("""
            CREATE TABLE players (player_id TEXT PRIMARY KEY, name TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, is_retired INTEGER DEFAULT 0);
            CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT NOT NULL,
              active INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, end_time TEXT);
            CREATE TABLE session_players (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
              player_id TEXT NOT NULL, score INTEGER NOT NULL);
            CREATE TABLE game_records (record_id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
              winner_id TEXT NOT NULL, winner_id2 TEXT, loser_id TEXT NOT NULL, loser_id2 TEXT,
              score INTEGER NOT NULL, created_at TEXT NOT NULL, special_score TEXT, special_score_part TEXT);
            CREATE TABLE player_retirement_log (id INTEGER PRIMARY KEY, player_id TEXT NOT NULL,
              action TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE tournaments (tournament_id TEXT PRIMARY KEY, name TEXT NOT NULL,
              bracket_size INTEGER, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT);
            CREATE TABLE tournament_rounds (tournament_id TEXT NOT NULL, round_index INTEGER NOT NULL,
              round_name TEXT NOT NULL, best_of INTEGER NOT NULL, PRIMARY KEY(tournament_id, round_index));
            CREATE TABLE tournament_participants (tournament_id TEXT NOT NULL, player_id TEXT NOT NULL,
              seed INTEGER, PRIMARY KEY(tournament_id, player_id));
            CREATE TABLE tournament_matches (match_id TEXT PRIMARY KEY, tournament_id TEXT NOT NULL,
              round_index INTEGER NOT NULL, slot_index INTEGER NOT NULL, player1_id TEXT, player2_id TEXT,
              is_bye INTEGER NOT NULL, winner_id TEXT, player1_games_won INTEGER NOT NULL,
              player2_games_won INTEGER NOT NULL, started_at TEXT, finished_at TEXT, video_url TEXT);
            CREATE TABLE tournament_match_games (match_id TEXT NOT NULL, game_index INTEGER NOT NULL,
              winner_id TEXT NOT NULL, PRIMARY KEY(match_id, game_index));
        """)
        names = [("p1", "Alice"), ("p2", " alice " if collision else "Bob")]
        conn.executemany("INSERT INTO players VALUES (?, ?, '2025-01-01T00:00:00Z', '2025-02-01T00:00:00Z', ?)",
                         [(pid, name, int(pid == "p2")) for pid, name in names])
        if not collision:
            conn.execute("INSERT INTO sessions VALUES ('s1', 'Legacy', 0, '2025-01-01T00:00:00Z', '2025-02-01T00:00:00Z', '2025-02-01T00:00:00Z')")
            conn.executemany("INSERT INTO session_players VALUES (?, 's1', ?, ?)", [(7, 'p1', 20), (8, 'p2', -20)])
            conn.execute("INSERT INTO game_records VALUES (9, 's1', 'p1', NULL, 'p2', NULL, 20, '2025-01-02T00:00:00Z', '大金', NULL)")
            conn.execute("INSERT INTO player_retirement_log VALUES (3, 'p2', 'retire', '2025-02-01T00:00:00Z')")
            conn.execute("INSERT INTO tournaments VALUES ('t1', 'Legacy Cup', 2, 'completed', '2025-01-01T00:00:00Z', '2025-02-01T00:00:00Z', '2025-02-01T00:00:00Z')")
            conn.execute("INSERT INTO tournament_rounds VALUES ('t1', 1, '决赛', 3)")
            conn.executemany("INSERT INTO tournament_participants VALUES ('t1', ?, ?)", [('p1', 1), ('p2', 2)])
            conn.execute("INSERT INTO tournament_matches VALUES ('m1', 't1', 1, 1, 'p1', 'p2', 0, 'p1', 2, 0, '2025-01-02T00:00:00Z', '2025-01-02T00:00:00Z', 'https://player.bilibili.com/x')")
            conn.execute("INSERT INTO tournament_match_games VALUES ('m1', 1, 'p1')")
        conn.commit(); conn.close()

    def test_legacy_migration_preserves_values_and_is_idempotent(self):
        self.legacy_fixture()
        DatabaseManager(self.path)
        conn = sqlite3.connect(self.path)
        try:
            self.assertEqual(conn.execute("SELECT org_id, slug FROM organizations").fetchone(), (EMS_ORG_ID, 'ems'))
            self.assertEqual(conn.execute("SELECT name, is_retired FROM players WHERE player_id='p2'").fetchone(), ('Bob', 1))
            self.assertEqual(conn.execute("SELECT id, score FROM session_players WHERE player_id='p1'").fetchone(), (7, 20))
            self.assertEqual(conn.execute("SELECT record_id, score, special_score FROM game_records").fetchone(), (9, 20, '大金'))
            self.assertEqual(conn.execute("SELECT status, completed_at FROM tournaments WHERE tournament_id='t1'").fetchone(), ('completed', '2025-02-01T00:00:00Z'))
            self.assertEqual(conn.execute("SELECT action FROM player_retirement_log").fetchone()[0], 'retire')
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], 'ok')
        finally:
            conn.close()
        DatabaseManager(self.path)
        conn = sqlite3.connect(self.path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=?", (TENANCY_MIGRATION_VERSION,)).fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM game_records").fetchone()[0], 1)
        conn.close()

    def test_normalization_collision_rolls_back_without_legacy_debris(self):
        self.legacy_fixture(collision=True)
        with self.assertRaisesRegex(RuntimeError, '规范化后冲突'):
            DatabaseManager(self.path)
        conn = sqlite3.connect(self.path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn('players', tables)
        self.assertNotIn('players_legacy', tables)
        self.assertNotIn('organizations', tables)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0], 2)
        conn.close()

    def test_empty_target_schema_seeds_ems(self):
        DatabaseManager(self.path)
        conn = sqlite3.connect(self.path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'organizations', 'players', 'sessions', 'game_records', 'tournaments', 'schema_migrations'} <= tables)
        self.assertEqual(conn.execute("SELECT org_id, name FROM organizations WHERE slug='ems'").fetchone(), (EMS_ORG_ID, 'EMS Pool'))
        conn.close()


class SlugAndIsolationTests(TempDatabaseCase):
    def test_names_slugs_and_organization_uniqueness(self):
        self.assertEqual(normalize_name(' ＥＭＳ Pool '), 'ems pool')
        self.assertEqual(validate_organization_name(' 车联天下 '), '车联天下')
        self.assertEqual(generate_organization_slug('车联天下', lambda _s: False), 'cheliantianxia')
        self.assertEqual(generate_organization_slug('Team 42', lambda _s: False), 'team-42')
        self.assertRegex(generate_organization_slug('车联天下', lambda s: s == 'cheliantianxia'), r'^cheliantianxia-[0-9a-f]{6}$')
        self.assertRegex(generate_organization_slug('EMS', lambda _s: False), r'^org-[0-9a-f]{6}$')
        with self.assertRaises(ValueError): validate_organization_name('x\x00')
        first = self.create_org('车联天下')
        self.assertEqual(first['slug'], 'cheliantianxia')
        with self.assertRaises(ValueError): self.create_org(' 车联天下 ')

    def test_two_org_scoring_statistics_achievements_and_cross_org_rejection(self):
        alpha, beta = self.create_org('Alpha'), self.create_org('Beta')
        alpha_session, a = self.seed_session(alpha['org_id'])
        beta_session, b = self.seed_session(beta['org_id'])
        self.assertNotEqual(a['Alice'], b['Alice'])
        self.assertEqual(self.manager.get_player_by_name(alpha['org_id'], 'Alice'), a['Alice'])
        # 1v1, one-versus-two, two-versus-one; then delete the latter two.
        r1 = self.manager.add_game_record(alpha['org_id'], alpha_session, a['Alice'], a['Bob'], 7, '小金')
        r2 = self.manager.add_game_record(alpha['org_id'], alpha_session, a['Alice'], a['Bob'], 20, '大金', a['Carol'])
        r3 = self.manager.add_game_record(alpha['org_id'], alpha_session, a['Alice'], a['Bob'], 14, winner_id2=a['Dan'])
        self.assertTrue(all((r1, r2, r3)))
        self.assertEqual(len(self.manager.get_session_records(alpha['org_id'], alpha_session)), 3)
        self.assertEqual(self.manager.get_player_stats(beta['org_id'], b['Alice'])['total_games'], 0)
        self.assertEqual(self.manager.get_player_special_wins(alpha['org_id'], a['Alice']), {'has_small_gold': True, 'has_big_gold': True})
        self.assertEqual(self.manager.get_achievement_stats(beta['org_id'])['big_gold_players'], 0)
        self.assertEqual(self.manager.get_available_months(alpha['org_id'])[0]['key'], '2026-08')
        self.assertEqual({x['name'] for x in self.manager.get_global_leaderboard(alpha['org_id'])}, set(a))
        self.assertTrue(self.manager.retire_player(alpha['org_id'], a['Carol']))
        self.assertTrue(self.manager.is_player_retired(alpha['org_id'], a['Carol']))
        self.assertFalse(self.manager.is_player_retired(beta['org_id'], a['Carol']))
        self.assertIsNone(self.manager.get_player_by_id(beta['org_id'], a['Alice']))
        self.assertFalse(self.manager.add_player_to_session(beta['org_id'], beta_session, a['Alice']))
        self.assertIsNone(self.manager.add_game_record(beta['org_id'], beta_session, a['Alice'], b['Bob'], 1))
        self.assertFalse(self.manager.delete_session(beta['org_id'], alpha_session))
        self.assertFalse(self.manager.update_player_name(beta['org_id'], a['Alice'], 'Intruder'))
        self.assertFalse(self.manager.retire_player(beta['org_id'], a['Alice']))
        self.assertIsNone(self.manager.delete_game_record(beta['org_id'], r1))
        self.assertIsNotNone(self.manager.delete_game_record(alpha['org_id'], r2))
        self.assertIsNotNone(self.manager.delete_game_record(alpha['org_id'], r3))
        self.assertEqual(len(self.manager.get_session_records(alpha['org_id'], alpha_session)), 1)

    def test_json_import_preserves_special_scores_and_team_score_math(self):
        org_id = EMS_ORG_ID
        players = {
            player_id: {
                'name': name,
                'created_at': '2025-01-01 00:00:00',
                'updated_at': '2025-01-01 00:00:00',
            }
            for player_id, name in (
                ('a', 'Alice'), ('b', 'Bob'), ('c', 'Carol'), ('d', 'Dan')
            )
        }
        records = [
            {
                'winner_id': 'a', 'loser_id': 'b', 'score': 7,
                'timestamp': '2025-01-02 00:00:00',
                'special_score_part': '小金',
            },
            {
                'winner_id': 'a', 'winner_id2': 'd', 'loser_id': 'b',
                'score': 14, 'timestamp': '2025-01-03 00:00:00',
                'special_score': '双吃',
            },
            {
                'winner_id': 'a', 'loser_id': 'b', 'loser_id2': 'c',
                'score': 20, 'timestamp': '2025-01-04 00:00:00',
                'special_score': '大金',
            },
            {
                'winner_id': 'a', 'loser_id': 'b', 'score': 10,
                'timestamp': '2025-01-05 00:00:00',
                'special_score_part': '大金 1/2 (总分20)',
            },
            {
                'winner_id': 'a', 'loser_id': 'c', 'score': 10,
                'timestamp': '2025-01-05 00:00:00',
                'special_score_part': '大金 2/2 (总分20)',
            },
        ]
        self.manager.migrate_from_json({
            'players': players,
            'sessions': {
                'legacy-json-session': {
                    'name': 'Legacy JSON', 'active': False,
                    'timestamp': '2025-01-01 00:00:00',
                    'player_ids': list(players), 'records': records,
                }
            },
        }, org_id)
        session = self.manager.get_session_with_players(org_id, 'legacy-json-session')
        self.assertEqual(session['scores'], {
            'Alice': 54, 'Bob': -41, 'Carol': -20, 'Dan': 7,
        })
        imported = self.manager.get_session_records(org_id, 'legacy-json-session')
        self.assertEqual(len(imported), 4)
        self.assertTrue(any(record['special_score'] == '小金' for record in imported))
        combined = next(
            record for record in imported
            if record['special_score'] == '大金' and record['created_at'] == '2025-01-05 00:00:00'
        )
        self.assertEqual(combined['score'], 20)
        self.assertEqual({player['id'] for player in combined['losers']}, {'b', 'c'})

    def test_tournament_scope_scoring_video_reset_undo_and_history(self):
        alpha, beta = self.create_org('Tournament Alpha'), self.create_org('Tournament Beta')
        _, a = self.seed_session(alpha['org_id'])
        _, b = self.seed_session(beta['org_id'])
        rounds = [{'name': '半决赛', 'best_of': 3}, {'name': '决赛', 'best_of': 3}]
        tid = tournament.create_tournament(alpha['org_id'], 'Alpha Cup', rounds)
        self.assertFalse(tournament.add_participant(beta['org_id'], tid, b['Alice']))
        self.assertFalse(tournament.add_participant(alpha['org_id'], tid, b['Alice']))
        for player_id in a.values(): self.assertTrue(tournament.add_participant(alpha['org_id'], tid, player_id))
        self.assertEqual(len(tournament.list_tournaments(alpha['org_id'])), 1)
        self.assertEqual(tournament.list_tournaments(beta['org_id']), [])
        self.assertTrue(tournament.generate_bracket(alpha['org_id'], tid)[0])
        bracket = tournament.get_bracket(alpha['org_id'], tid)
        match_id = bracket[0][0]['match_id']
        self.assertIsNone(tournament.get_match(beta['org_id'], match_id))
        self.assertFalse(tournament.record_match_game(beta['org_id'], match_id, 1)[0])
        self.assertTrue(tournament.set_match_video_url(alpha['org_id'], match_id, 'http://player.bilibili.com/video/BV1')[0])
        self.assertEqual(tournament.get_match(alpha['org_id'], match_id)['video_url'], 'https://player.bilibili.com/video/BV1')
        self.assertTrue(tournament.record_match_game(alpha['org_id'], match_id, 1)[0])
        self.assertTrue(tournament.undo_last_game(alpha['org_id'], match_id)[0])
        self.assertTrue(tournament.record_match_result(alpha['org_id'], match_id, 2, 0)[0])
        self.assertTrue(tournament.reset_match(alpha['org_id'], match_id)[0])
        self.assertEqual(len(tournament.get_player_tournament_history(alpha['org_id'], a['Alice'])), 1)
        self.assertEqual(tournament.get_player_tournament_history(beta['org_id'], a['Alice']), [])


class HttpTenantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ems-pool-http-")
        self.path = str(Path(self.tmp.name) / 'http.db')
        self.original_global_path = db.db_path
        db.db_path = self.path
        self.app = wsgi.create_app({'TESTING': True, 'DATABASE_PATH': self.path, 'SECRET_KEY': 'test-secret'})
        self.client = self.app.test_client()
        self.manager = DatabaseManager(self.path)
        self.alpha = self.manager.create_organization('HTTP Alpha', generate_password_hash('alpha-organization-password'))
        self.beta = self.manager.create_organization('HTTP Beta', generate_password_hash('beta-organization-password'))

    def tearDown(self):
        db.db_path = self.original_global_path
        self.tmp.cleanup()

    def csrf(self):
        response = self.client.get('/')
        match = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(match)
        return match.group(1)

    def test_portal_creation_selection_gateway_and_tenant_pwa(self):
        body = self.client.get('/').get_data(as_text=True)
        self.assertIn('选择组织', body); self.assertNotIn('HTTP Alpha', body)
        token = self.csrf()
        create = self.client.post('/organizations/new', data={'name': 'HTTP New', 'password': 'new-organization-password', 'password_confirm': 'new-organization-password', 'csrf_token': token})
        self.assertEqual(create.status_code, 302)
        created = self.manager.get_organization_by_name_or_slug('HTTP New')
        self.assertNotEqual(created['admin_password_hash'], 'new-organization-password')
        self.assertTrue(created['admin_password_hash'])
        token = self.csrf()
        selected = self.client.post('/organizations/select', data={'organization': 'HTTP Alpha', 'csrf_token': token})
        self.assertEqual(selected.location, '/o/http-alpha/')
        token = self.csrf()
        continued = self.client.post('/organizations/continue', data={'organization': 'HTTP Alpha', 'continue': '/history?search=abc&bad=drop', 'csrf_token': token})
        self.assertEqual(continued.location, '/o/http-alpha/history?search=abc')
        token = self.csrf()
        rejected_continue = self.client.post('/organizations/continue', data={'organization': 'HTTP Alpha', 'continue': 'https://evil.test/', 'csrf_token': token})
        self.assertEqual(rejected_continue.location, '/o/http-alpha/')
        self.assertEqual(self.client.get('/o/no-such-org/').status_code, 404)
        old = self.client.get('/history?search=abc&bad=drop').get_data(as_text=True)
        self.assertIn('continue', old); self.assertIn('/history?search=abc', old); self.assertNotIn('bad=drop', old)
        for bad in ('https://evil.test/', '//evil.test/', '/history/../admin', '/delete_session/x'):
            self.assertNotIn(bad, self.client.get('/?continue=' + bad).get_data(as_text=True))
        self.assertEqual(self.client.post('/history').status_code, 405)
        manifest = self.client.get('/o/http-alpha/manifest.webmanifest')
        self.assertEqual(manifest.status_code, 200)
        payload = json.loads(manifest.get_data(as_text=True))
        self.assertEqual(payload['name'], 'HTTP Alpha')
        self.assertEqual(payload['short_name'], 'HTTP Alpha')
        self.assertNotIn('EMS Pool', payload['name'])
        self.assertEqual(payload['start_url'], '/o/http-alpha/')
        self.assertEqual(payload['scope'], '/o/http-alpha/')
        self.assertEqual(self.client.get('/o/http-alpha/sw.js').headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get('/o/http-beta/manifest.webmanifest').get_json()['scope'], '/o/http-beta/')

    def test_admin_is_tenant_scoped_super_admin_and_logout_csrf(self):
        # Old legacy session claim is not authority.
        with self.client.session_transaction() as sess: sess['admin_authenticated'] = True
        response = self.client.get('/o/http-alpha/admin')
        self.assertEqual(response.status_code, 200)
        token = self.csrf()
        login = self.client.post('/o/http-alpha/admin', data={'password': 'super-secret-test-password', 'csrf_token': token})
        self.assertEqual(login.status_code, 302)
        self.assertEqual(self.client.get('/o/http-beta/admin').status_code, 302)  # super-admin reaches tenant index
        self.assertEqual(self.client.get('/o/http-beta/tournament/new').status_code, 200)
        self.assertEqual(self.client.post('/o/http-alpha/admin/logout').status_code, 302)  # invalid CSRF is rejected
        self.assertEqual(self.client.get('/o/http-alpha/admin').status_code, 302)  # still super-admin
        token = self.csrf()
        self.client.post('/o/http-alpha/admin/logout', data={'csrf_token': token})
        self.assertEqual(self.client.get('/o/http-alpha/admin').status_code, 200)
        # Organization-specific admin cannot administer another organization.
        token = self.csrf()
        org_login = self.client.post('/o/http-alpha/admin', data={'password': 'alpha-organization-password', 'csrf_token': token})
        self.assertEqual(org_login.status_code, 302)
        self.assertEqual(self.client.get('/o/http-alpha/tournament/new').status_code, 200)
        alpha_session = self.manager.create_session(self.alpha['org_id'], 'Admin player creation')
        add_player = self.client.post(
            f'/o/http-alpha/add_player/{alpha_session}',
            data={'new_player_name': 'Created By Org Admin'},
        )
        self.assertEqual(add_player.status_code, 302)
        self.assertIsNotNone(
            self.manager.get_player_by_name(self.alpha['org_id'], 'Created By Org Admin')
        )
        self.assertEqual(self.client.get('/o/http-beta/tournament/new').status_code, 302)

    def test_wrong_org_entities_and_pages_do_not_leak_names(self):
        alpha_player = self.manager.create_player(self.alpha['org_id'], 'Alpha Secret')
        beta_player = self.manager.create_player(self.beta['org_id'], 'Beta Secret')
        alpha_session = self.manager.create_session(self.alpha['org_id'], 'Alpha Session')
        self.manager.add_player_to_session(self.alpha['org_id'], alpha_session, alpha_player)
        self.assertNotIn('Alpha Secret', self.client.get('/o/http-beta/history').get_data(as_text=True))
        self.assertNotIn('Alpha Session', self.client.get('/o/http-beta/').get_data(as_text=True))
        # Player route explicitly treats a foreign UUID as not found / redirect, never renders it.
        response = self.client.get('/o/http-beta/player/' + alpha_player)
        self.assertEqual(response.status_code, 404)
        response = self.client.get('/o/http-beta/game/' + alpha_session)
        self.assertEqual(response.status_code, 404)
        response = self.client.get('/o/http-beta/session_detail/' + alpha_session)
        self.assertEqual(response.status_code, 404)


class AppFactoryIsolationTests(unittest.TestCase):
    def test_two_apps_keep_independent_database_managers(self):
        with tempfile.TemporaryDirectory(prefix='ems-pool-factory-') as directory:
            first_path = str(Path(directory) / 'first.db')
            second_path = str(Path(directory) / 'second.db')
            first_app = wsgi.create_app({
                'TESTING': True,
                'DATABASE_PATH': first_path,
                'SECRET_KEY': 'first-secret',
            })
            first_db = first_app.extensions['database']
            organization = first_db.create_organization(
                'Factory Alpha', generate_password_hash('factory-alpha-password')
            )
            first_client = first_app.test_client()
            self.assertEqual(first_client.get('/o/factory-alpha/').status_code, 200)

            second_app = wsgi.create_app({
                'TESTING': True,
                'DATABASE_PATH': second_path,
                'SECRET_KEY': 'second-secret',
            })
            second_client = second_app.test_client()
            self.assertEqual(second_client.get('/o/factory-alpha/').status_code, 404)
            self.assertEqual(first_client.get('/o/factory-alpha/').status_code, 200)
            self.assertEqual(
                first_app.extensions['database'].db_path,
                first_path,
            )
            self.assertEqual(
                second_app.extensions['database'].db_path,
                second_path,
            )
            self.assertEqual(
                first_app.extensions['database'].get_organization_by_id(
                    organization['org_id']
                )['slug'],
                'factory-alpha',
            )


class TemplateContractTests(unittest.TestCase):
    def test_recent_org_and_tenant_template_contracts(self):
        portal = (ROOT / 'templates/organization_portal.html').read_text()
        presence = (ROOT / 'templates/_tenant_presence.html').read_text()
        game = (ROOT / 'templates/game.html').read_text()
        history = (ROOT / 'templates/history.html').read_text()
        self.assertIn("ems-pool.recent-organizations.v1", portal)
        self.assertIn('document.createElement', portal)
        self.assertIn('.textContent = entry.name', portal)
        self.assertNotIn('innerHTML', portal)
        self.assertIn("{% include '_tenant_presence.html' %}", game)
        self.assertIn("{% include '_tenant_presence.html' %}", history)
        self.assertIn("url_for('tenant.add_score'", game)
        self.assertIn("url_for('tenant.load_more_sessions')", history)
        self.assertIn("url_for('tenant.player_detail'", history)
        heading_expectations = {
            ROOT / 'templates/history.html': "organization_page_title = '历史统计'",
            ROOT / 'templates/game.html': "organization_page_title = '游戏中'",
            ROOT / 'templates/player_detail.html': "organization_page_title = '玩家详情'",
            ROOT / 'templates/session_detail.html': "organization_page_title = '场次详情'",
            ROOT / 'templates/achievements/index.html': "organization_page_title = '特殊记录'",
            ROOT / 'templates/tournament_index.html': "organization_page_title = '赛事'",
        }
        for path, expected in heading_expectations.items():
            self.assertIn(expected, path.read_text(), path)
        switcher = (ROOT / 'templates/_organization_switcher.html').read_text()
        self.assertIn("{{ organization_page_title }} -&nbsp;", switcher)
        title_sources = [
            ROOT / 'templates/base.html',
            ROOT / 'templates/index.html',
            ROOT / 'templates/game.html',
            ROOT / 'templates/history.html',
            ROOT / 'templates/player_detail.html',
            ROOT / 'templates/session_detail.html',
            ROOT / 'templates/admin_login.html',
            ROOT / 'templates/achievements.html',
            *(ROOT / 'templates/achievements').glob('*.html'),
            *(ROOT / 'templates').glob('tournament_*.html'),
        ]
        for path in title_sources:
            title_markup = re.findall(r'<title>.*?</title>|\{% block title %\}.*?\{% endblock %\}', path.read_text())
            self.assertTrue(title_markup, path)
            self.assertNotIn('EMS Pool', ''.join(title_markup), path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
