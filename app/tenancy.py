"""Organization tenancy schema, validation, and legacy migration helpers."""
import re
import secrets
import sqlite3
import unicodedata
import uuid
from typing import Callable

from pypinyin import Style, lazy_pinyin

from .utils import get_utc_timestamp


TENANCY_MIGRATION_VERSION = "20260808_multi_organization_tenancy"
EMS_ORG_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://emspool.app/organizations/ems"))
EMS_ORG_SLUG = "ems"
_RESERVED_SLUGS = {
    "admin", "api", "static", "organizations", "organization", "o",
    "history", "game", "player", "achievement", "achievements",
    "tournament", "super-admin", "ems",
}
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?$")


def normalize_name(name: str) -> str:
    """Return the canonical lookup key for an organization or player name."""
    return unicodedata.normalize("NFKC", name or "").strip().casefold()


def validate_organization_name(name: str) -> str:
    """Validate and return the normalized display form of an organization name."""
    display_name = unicodedata.normalize("NFKC", name or "").strip()
    if not display_name or len(display_name) > 80:
        raise ValueError("组织名称长度必须为 1 到 80 个字符")
    if any(unicodedata.category(char).startswith("C") for char in display_name):
        raise ValueError("组织名称不能包含控制字符")
    return display_name


def _slug_base(name: str) -> str:
    transliterated = "".join(
        lazy_pinyin(name, style=Style.NORMAL, errors="default")
    ).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", transliterated).strip("-")
    slug = re.sub(r"-+", "-", slug)[:48].rstrip("-")
    if not slug or not _SLUG_RE.fullmatch(slug):
        return ""
    return slug


def generate_organization_slug(
    name: str,
    slug_exists: Callable[[str], bool],
) -> str:
    """Generate an immutable readable slug, adding entropy on collisions."""
    base = _slug_base(validate_organization_name(name))
    if not base or base in _RESERVED_SLUGS:
        base = f"org-{secrets.token_hex(3)}"
    if not slug_exists(base):
        return base

    stem = base[:41].rstrip("-") or "org"
    for _ in range(20):
        candidate = f"{stem}-{secrets.token_hex(3)}"
        if not slug_exists(candidate):
            return candidate
    raise RuntimeError("无法生成唯一的组织链接，请重试")


def _create_target_tables(cursor: sqlite3.Cursor) -> None:
    cursor.executescript("""
        CREATE TABLE organizations (
            org_id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            name_key TEXT NOT NULL UNIQUE,
            admin_password_hash TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE players (
            player_id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            name TEXT NOT NULL,
            name_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_retired INTEGER NOT NULL DEFAULT 0,
            UNIQUE (org_id, player_id),
            UNIQUE (org_id, name_key),
            FOREIGN KEY (org_id) REFERENCES organizations (org_id)
        );

        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            end_time TEXT,
            UNIQUE (org_id, session_id),
            FOREIGN KEY (org_id) REFERENCES organizations (org_id)
        );

        CREATE TABLE session_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            UNIQUE (org_id, session_id, player_id),
            FOREIGN KEY (org_id, session_id)
                REFERENCES sessions (org_id, session_id) ON DELETE CASCADE,
            FOREIGN KEY (org_id, player_id)
                REFERENCES players (org_id, player_id)
        );

        CREATE TABLE game_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            winner_id TEXT NOT NULL,
            winner_id2 TEXT,
            loser_id TEXT NOT NULL,
            loser_id2 TEXT,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            special_score TEXT,
            special_score_part TEXT,
            FOREIGN KEY (org_id, session_id, winner_id)
                REFERENCES session_players (org_id, session_id, player_id),
            FOREIGN KEY (org_id, session_id, winner_id2)
                REFERENCES session_players (org_id, session_id, player_id),
            FOREIGN KEY (org_id, session_id, loser_id)
                REFERENCES session_players (org_id, session_id, player_id),
            FOREIGN KEY (org_id, session_id, loser_id2)
                REFERENCES session_players (org_id, session_id, player_id)
        );

        CREATE TABLE player_retirement_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (org_id, player_id)
                REFERENCES players (org_id, player_id)
        );

        CREATE TABLE tournaments (
            tournament_id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            name TEXT NOT NULL,
            bracket_size INTEGER,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE (org_id, tournament_id),
            FOREIGN KEY (org_id) REFERENCES organizations (org_id)
        );

        CREATE TABLE tournament_rounds (
            org_id TEXT NOT NULL,
            tournament_id TEXT NOT NULL,
            round_index INTEGER NOT NULL,
            round_name TEXT NOT NULL,
            best_of INTEGER NOT NULL,
            PRIMARY KEY (org_id, tournament_id, round_index),
            FOREIGN KEY (org_id, tournament_id)
                REFERENCES tournaments (org_id, tournament_id) ON DELETE CASCADE
        );

        CREATE TABLE tournament_participants (
            org_id TEXT NOT NULL,
            tournament_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            seed INTEGER,
            PRIMARY KEY (org_id, tournament_id, player_id),
            FOREIGN KEY (org_id, tournament_id)
                REFERENCES tournaments (org_id, tournament_id) ON DELETE CASCADE,
            FOREIGN KEY (org_id, player_id)
                REFERENCES players (org_id, player_id)
        );

        CREATE TABLE tournament_matches (
            match_id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            tournament_id TEXT NOT NULL,
            round_index INTEGER NOT NULL,
            slot_index INTEGER NOT NULL,
            player1_id TEXT,
            player2_id TEXT,
            is_bye INTEGER NOT NULL DEFAULT 0,
            winner_id TEXT,
            player1_games_won INTEGER NOT NULL DEFAULT 0,
            player2_games_won INTEGER NOT NULL DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            video_url TEXT,
            UNIQUE (org_id, match_id),
            UNIQUE (org_id, tournament_id, round_index, slot_index),
            FOREIGN KEY (org_id, tournament_id)
                REFERENCES tournaments (org_id, tournament_id) ON DELETE CASCADE,
            FOREIGN KEY (org_id, tournament_id, player1_id)
                REFERENCES tournament_participants (org_id, tournament_id, player_id),
            FOREIGN KEY (org_id, tournament_id, player2_id)
                REFERENCES tournament_participants (org_id, tournament_id, player_id),
            FOREIGN KEY (org_id, tournament_id, winner_id)
                REFERENCES tournament_participants (org_id, tournament_id, player_id)
        );

        CREATE TABLE tournament_match_games (
            org_id TEXT NOT NULL,
            match_id TEXT NOT NULL,
            game_index INTEGER NOT NULL,
            winner_id TEXT NOT NULL,
            PRIMARY KEY (org_id, match_id, game_index),
            FOREIGN KEY (org_id, match_id)
                REFERENCES tournament_matches (org_id, match_id) ON DELETE CASCADE,
            FOREIGN KEY (org_id, winner_id)
                REFERENCES players (org_id, player_id)
        );
    """)


def _create_target_indexes(cursor: sqlite3.Cursor) -> None:
    cursor.executescript("""
        CREATE INDEX idx_players_org_name ON players (org_id, name_key);
        CREATE INDEX idx_players_org_retired ON players (org_id, is_retired, name);
        CREATE INDEX idx_sessions_org_active ON sessions (org_id, active, created_at DESC);
        CREATE INDEX idx_sessions_org_ended ON sessions (org_id, active, end_time DESC, updated_at DESC);
        CREATE INDEX idx_session_players_org_session ON session_players (org_id, session_id);
        CREATE INDEX idx_session_players_org_player ON session_players (org_id, player_id);
        CREATE INDEX idx_game_records_org_session ON game_records (org_id, session_id, record_id DESC);
        CREATE INDEX idx_game_records_org_winner ON game_records (org_id, winner_id, created_at DESC);
        CREATE INDEX idx_game_records_org_winner2 ON game_records (org_id, winner_id2, created_at DESC);
        CREATE INDEX idx_game_records_org_loser ON game_records (org_id, loser_id, created_at DESC);
        CREATE INDEX idx_game_records_org_loser2 ON game_records (org_id, loser_id2, created_at DESC);
        CREATE INDEX idx_retirement_log_org_player ON player_retirement_log (org_id, player_id, created_at DESC);
        CREATE INDEX idx_tournaments_org_created ON tournaments (org_id, created_at DESC);
        CREATE INDEX idx_tournament_participants_org_player ON tournament_participants (org_id, player_id);
        CREATE INDEX idx_tournament_matches_org_round ON tournament_matches (org_id, tournament_id, round_index, slot_index);
    """)


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _is_tenant_schema(cursor: sqlite3.Cursor) -> bool:
    if not _table_exists(cursor, "organizations"):
        return False
    cursor.execute("PRAGMA table_info(players)")
    return "org_id" in {row[1] for row in cursor.fetchall()}


def _validate_legacy_names(cursor: sqlite3.Cursor) -> None:
    cursor.execute("SELECT player_id, name FROM players")
    seen = {}
    for player_id, name in cursor.fetchall():
        key = normalize_name(name)
        if not key:
            raise RuntimeError(f"玩家 {player_id} 的名称为空，无法迁移")
        if key in seen:
            raise RuntimeError(
                f"玩家名称规范化后冲突：{seen[key]} 与 {player_id}"
            )
        seen[key] = player_id


def _copy_legacy_rows(cursor: sqlite3.Cursor, now: str) -> None:
    cursor.execute(
        """INSERT INTO organizations
           (org_id, slug, name, name_key, admin_password_hash, created_at, updated_at)
           VALUES (?, ?, ?, ?, NULL, ?, ?)""",
        (EMS_ORG_ID, EMS_ORG_SLUG, "EMS Pool", normalize_name("EMS Pool"), now, now),
    )
    cursor.execute(
        """SELECT player_id, name, created_at, updated_at,
                  COALESCE(is_retired, 0)
           FROM players_legacy"""
    )
    legacy_players = cursor.fetchall()
    cursor.executemany(
        """INSERT INTO players
           (player_id, org_id, name, name_key, created_at, updated_at, is_retired)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                player_id,
                EMS_ORG_ID,
                name,
                normalize_name(name),
                created_at,
                updated_at,
                is_retired,
            )
            for player_id, name, created_at, updated_at, is_retired
            in legacy_players
        ],
    )
    cursor.execute(
        """INSERT INTO sessions
           (session_id, org_id, name, active, created_at, updated_at, end_time)
           SELECT session_id, ?, name, active, created_at, updated_at, end_time
           FROM sessions_legacy""",
        (EMS_ORG_ID,),
    )
    cursor.execute(
        """INSERT INTO session_players
           (id, org_id, session_id, player_id, score)
           SELECT id, ?, session_id, player_id, score FROM session_players_legacy""",
        (EMS_ORG_ID,),
    )
    cursor.execute(
        """INSERT INTO game_records
           (record_id, org_id, session_id, winner_id, winner_id2, loser_id,
            loser_id2, score, created_at, special_score, special_score_part)
           SELECT record_id, ?, session_id, winner_id, winner_id2, loser_id,
                  loser_id2, score, created_at, special_score, special_score_part
           FROM game_records_legacy""",
        (EMS_ORG_ID,),
    )
    cursor.execute(
        """INSERT INTO player_retirement_log
           (id, org_id, player_id, action, created_at)
           SELECT id, ?, player_id, action, created_at
           FROM player_retirement_log_legacy""",
        (EMS_ORG_ID,),
    )
    cursor.execute(
        """INSERT INTO tournaments
           (tournament_id, org_id, name, bracket_size, status, created_at,
            updated_at, completed_at)
           SELECT tournament_id, ?, name, bracket_size, status, created_at,
                  updated_at, completed_at FROM tournaments_legacy""",
        (EMS_ORG_ID,),
    )
    cursor.execute(
        """INSERT INTO tournament_rounds
           (org_id, tournament_id, round_index, round_name, best_of)
           SELECT ?, tournament_id, round_index, round_name, best_of
           FROM tournament_rounds_legacy""",
        (EMS_ORG_ID,),
    )
    cursor.execute(
        """INSERT INTO tournament_participants
           (org_id, tournament_id, player_id, seed)
           SELECT ?, tournament_id, player_id, seed
           FROM tournament_participants_legacy""",
        (EMS_ORG_ID,),
    )
    cursor.execute(
        """INSERT INTO tournament_matches
           (match_id, org_id, tournament_id, round_index, slot_index,
            player1_id, player2_id, is_bye, winner_id, player1_games_won,
            player2_games_won, started_at, finished_at, video_url)
           SELECT match_id, ?, tournament_id, round_index, slot_index,
                  player1_id, player2_id, is_bye, winner_id, player1_games_won,
                  player2_games_won, started_at, finished_at, video_url
           FROM tournament_matches_legacy""",
        (EMS_ORG_ID,),
    )
    cursor.execute(
        """INSERT INTO tournament_match_games
           (org_id, match_id, game_index, winner_id)
           SELECT ?, match_id, game_index, winner_id
           FROM tournament_match_games_legacy""",
        (EMS_ORG_ID,),
    )


def _ensure_legacy_source_tables(cursor: sqlite3.Cursor) -> None:
    """Supply empty late-added tables and columns for every supported legacy version."""
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS player_retirement_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT NOT NULL,
            action TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tournaments (
            tournament_id TEXT PRIMARY KEY, name TEXT NOT NULL, bracket_size INTEGER,
            status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tournament_rounds (
            tournament_id TEXT NOT NULL, round_index INTEGER NOT NULL,
            round_name TEXT NOT NULL, best_of INTEGER NOT NULL,
            PRIMARY KEY (tournament_id, round_index)
        );
        CREATE TABLE IF NOT EXISTS tournament_participants (
            tournament_id TEXT NOT NULL, player_id TEXT NOT NULL, seed INTEGER,
            PRIMARY KEY (tournament_id, player_id)
        );
        CREATE TABLE IF NOT EXISTS tournament_matches (
            match_id TEXT PRIMARY KEY, tournament_id TEXT NOT NULL,
            round_index INTEGER NOT NULL, slot_index INTEGER NOT NULL,
            player1_id TEXT, player2_id TEXT, is_bye INTEGER NOT NULL DEFAULT 0,
            winner_id TEXT, player1_games_won INTEGER NOT NULL DEFAULT 0,
            player2_games_won INTEGER NOT NULL DEFAULT 0, started_at TEXT,
            finished_at TEXT, video_url TEXT
        );
        CREATE TABLE IF NOT EXISTS tournament_match_games (
            match_id TEXT NOT NULL, game_index INTEGER NOT NULL, winner_id TEXT NOT NULL,
            PRIMARY KEY (match_id, game_index)
        );
    """)
    required_columns = {
        'players': [('is_retired', 'INTEGER NOT NULL DEFAULT 0')],
        'sessions': [('end_time', 'TEXT')],
        'game_records': [
            ('loser_id2', 'TEXT'), ('winner_id2', 'TEXT'), ('special_score', 'TEXT'),
            ('special_score_part', 'TEXT'),
        ],
        'tournaments': [('completed_at', 'TEXT')],
        'tournament_matches': [('video_url', 'TEXT')],
    }
    for table_name, columns in required_columns.items():
        cursor.execute(f'PRAGMA table_info({table_name})')
        existing = {row[1] for row in cursor.fetchall()}
        for column_name, definition in columns:
            if column_name not in existing:
                cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}')


def migrate_legacy_database(db_path: str) -> None:
    """Migrate a normalized single-organization database to the tenant schema."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = OFF")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)
        cursor.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (TENANCY_MIGRATION_VERSION,),
        )
        if cursor.fetchone():
            return
        if _is_tenant_schema(cursor):
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (TENANCY_MIGRATION_VERSION, get_utc_timestamp()),
            )
            conn.commit()
            return

        conn.execute("BEGIN IMMEDIATE")
        _ensure_legacy_source_tables(cursor)
        _validate_legacy_names(cursor)
        legacy_tables = [
            "tournament_match_games", "tournament_matches",
            "tournament_participants", "tournament_rounds", "tournaments",
            "player_retirement_log", "game_records", "session_players",
            "sessions", "players",
        ]
        for table in legacy_tables:
            cursor.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy")

        _create_target_tables(cursor)
        _copy_legacy_rows(cursor, get_utc_timestamp())

        for table in legacy_tables:
            cursor.execute(f"DROP TABLE {table}_legacy")
        _create_target_indexes(cursor)

        cursor.execute("PRAGMA foreign_key_check")
        violations = cursor.fetchall()
        if violations:
            raise RuntimeError(f"组织迁移后的外键检查失败：{violations[:5]}")
        cursor.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (TENANCY_MIGRATION_VERSION, get_utc_timestamp()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


def initialize_database(db_path: str) -> None:
    """Create target tables for a new database, or upgrade a legacy one once."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'players'")
        has_players = cursor.fetchone() is not None
        if has_players:
            cursor.execute("PRAGMA table_info(players)")
            is_tenant = 'org_id' in {row[1] for row in cursor.fetchall()}
            if not is_tenant:
                conn.close()
                conn = None
                migrate_legacy_database(db_path)
                return
            cursor.execute("SELECT 1 FROM organizations WHERE org_id = ?", (EMS_ORG_ID,))
            if not cursor.fetchone():
                now = get_utc_timestamp()
                cursor.execute(
                    '''INSERT INTO organizations
                       (org_id, slug, name, name_key, admin_password_hash, created_at, updated_at)
                       VALUES (?, ?, ?, ?, NULL, ?, ?)''',
                    (EMS_ORG_ID, EMS_ORG_SLUG, 'EMS Pool', normalize_name('EMS Pool'), now, now),
                )
            conn.commit()
            return

        cursor.execute('BEGIN IMMEDIATE')
        _create_target_tables(cursor)
        now = get_utc_timestamp()
        cursor.execute(
            '''INSERT INTO organizations
               (org_id, slug, name, name_key, admin_password_hash, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, ?, ?)''',
            (EMS_ORG_ID, EMS_ORG_SLUG, 'EMS Pool', normalize_name('EMS Pool'), now, now),
        )
        _create_target_indexes(cursor)
        cursor.execute('''CREATE TABLE schema_migrations (
            version TEXT PRIMARY KEY, applied_at TEXT NOT NULL
        )''')
        cursor.execute('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)',
                       (TENANCY_MIGRATION_VERSION, now))
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()
