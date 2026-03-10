from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, MutableMapping, Optional

import streamlit as st


LOGGER = logging.getLogger(__name__)
_WARNED: set[str] = set()
_DEFAULT_TABLE = "app_state"
_STATE_KEYS = ("patients", "training_history", "audit_events", "psych_label_counts", "last_report")


def _warn_once(key: str, message: str) -> None:
    if key in _WARNED:
        return
    _WARNED.add(key)
    LOGGER.warning(message)


def _safe_secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def _import_psycopg() -> Any:
    try:
        import psycopg  # type: ignore

        return psycopg
    except Exception:
        _warn_once(
            "missing_psycopg",
            "PostgreSQL persistence is enabled but 'psycopg' is not installed. Falling back to session memory.",
        )
        return None


def _postgres_config() -> Dict[str, Any]:
    port_raw = (
        _safe_secret("POSTGRES_PORT")
        or os.environ.get("POSTGRES_PORT", "").strip()
        or os.environ.get("PGPORT", "5432").strip()
    )
    try:
        port = int(port_raw)
    except Exception:
        port = 5432

    table = (
        _safe_secret("POSTGRES_TABLE")
        or os.environ.get("POSTGRES_TABLE", "").strip()
        or _safe_secret("APP_STATE_TABLE")
        or os.environ.get("APP_STATE_TABLE", "").strip()
        or _DEFAULT_TABLE
    )
    table = table if re.fullmatch(r"[A-Za-z0-9_]+", table) else _DEFAULT_TABLE

    return {
        "host": _safe_secret("POSTGRES_HOST") or os.environ.get("POSTGRES_HOST", "").strip() or os.environ.get("PGHOST", "").strip(),
        "port": port,
        "user": _safe_secret("POSTGRES_USER") or os.environ.get("POSTGRES_USER", "").strip() or os.environ.get("PGUSER", "").strip(),
        "password": _safe_secret("POSTGRES_PASSWORD")
        or os.environ.get("POSTGRES_PASSWORD", "").strip()
        or os.environ.get("PGPASSWORD", "").strip(),
        "database": _safe_secret("POSTGRES_DATABASE")
        or os.environ.get("POSTGRES_DATABASE", "").strip()
        or os.environ.get("PGDATABASE", "").strip(),
        "sslmode": _safe_secret("POSTGRES_SSLMODE") or os.environ.get("POSTGRES_SSLMODE", "").strip() or os.environ.get("PGSSLMODE", "").strip(),
        "table": table,
    }


def _is_postgres_configured(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("host") and cfg.get("user") and cfg.get("database"))


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _connect_postgres(cfg: Dict[str, Any]) -> Optional[Any]:
    psycopg = _import_psycopg()
    if not psycopg:
        return None

    kwargs: Dict[str, Any] = {
        "host": cfg["host"],
        "port": int(cfg["port"]),
        "user": cfg["user"],
        "dbname": cfg["database"],
        "autocommit": True,
    }
    if cfg.get("password"):
        kwargs["password"] = cfg["password"]
    if cfg.get("sslmode"):
        kwargs["sslmode"] = cfg["sslmode"]

    try:
        return psycopg.connect(**kwargs)
    except Exception as exc:
        _warn_once("postgres_connect_failed", f"PostgreSQL connection failed: {exc}")
        return None


def _ensure_schema(conn: Any, table_name: str) -> None:
    table = _quote_ident(table_name)
    sql = f"""
    CREATE TABLE IF NOT EXISTS {table} (
        state_key VARCHAR(64) PRIMARY KEY,
        state_value JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """
    with conn.cursor() as cur:
        cur.execute(sql)


def _is_valid_payload(key: str, value: Any) -> bool:
    if key in {"patients", "training_history", "audit_events"}:
        return isinstance(value, list)
    if key == "psych_label_counts":
        return isinstance(value, dict)
    if key == "last_report":
        return isinstance(value, str)
    return True


def _read_state_value(conn: Any, table_name: str, key: str) -> Any:
    table = _quote_ident(table_name)
    with conn.cursor() as cur:
        cur.execute(f"SELECT state_value FROM {table} WHERE state_key=%s", (key,))
        row = cur.fetchone()
    if not row:
        return None

    raw = row[0]
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            _warn_once(f"decode_{key}", f"Failed to decode JSON for key '{key}', skip loading it.")
            return None
    return raw


def _write_state_value(conn: Any, table_name: str, key: str, value: Any) -> None:
    table = _quote_ident(table_name)
    payload = json.dumps(value, ensure_ascii=False)
    sql = f"""
    INSERT INTO {table} (state_key, state_value, updated_at)
    VALUES (%s, %s::jsonb, NOW())
    ON CONFLICT (state_key)
    DO UPDATE SET state_value = EXCLUDED.state_value, updated_at = NOW()
    """
    with conn.cursor() as cur:
        cur.execute(sql, (key, payload))


def initialize_persistent_state(session_state: MutableMapping[str, Any]) -> bool:
    cfg = _postgres_config()
    if not _is_postgres_configured(cfg):
        session_state["storage_backend"] = "memory"
        return False

    conn = _connect_postgres(cfg)
    if not conn:
        session_state["storage_backend"] = "memory"
        return False

    loaded = False
    try:
        _ensure_schema(conn, cfg["table"])
        for key in _STATE_KEYS:
            db_value = _read_state_value(conn, cfg["table"], key)
            if db_value is not None and _is_valid_payload(key, db_value):
                session_state[key] = db_value
                loaded = True
            elif key in session_state:
                _write_state_value(conn, cfg["table"], key, session_state[key])
        session_state["storage_backend"] = f"postgresql://{cfg['host']}:{cfg['port']}/{cfg['database']}"
        return loaded
    except Exception as exc:
        _warn_once("postgres_initialize_failed", f"PostgreSQL initialization failed: {exc}")
        session_state["storage_backend"] = "memory"
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _persist_key(session_state: MutableMapping[str, Any], key: str) -> bool:
    cfg = _postgres_config()
    if not _is_postgres_configured(cfg):
        return False

    conn = _connect_postgres(cfg)
    if not conn:
        return False
    try:
        _ensure_schema(conn, cfg["table"])
        _write_state_value(conn, cfg["table"], key, session_state.get(key))
        return True
    except Exception as exc:
        _warn_once(f"persist_{key}", f"Persist key '{key}' failed: {exc}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def save_patients(session_state: MutableMapping[str, Any]) -> bool:
    return _persist_key(session_state, "patients")


def save_training_history(session_state: MutableMapping[str, Any]) -> bool:
    return _persist_key(session_state, "training_history")


def save_audit_events(session_state: MutableMapping[str, Any]) -> bool:
    return _persist_key(session_state, "audit_events")


def save_psych_label_counts(session_state: MutableMapping[str, Any]) -> bool:
    return _persist_key(session_state, "psych_label_counts")


def save_last_report(session_state: MutableMapping[str, Any]) -> bool:
    return _persist_key(session_state, "last_report")


def get_patients(session_state: MutableMapping[str, Any]) -> List[Dict[str, Any]]:
    patients = session_state.get("patients", [])
    return patients if isinstance(patients, list) else []


def get_training_history(session_state: MutableMapping[str, Any]) -> List[Dict[str, Any]]:
    training_history = session_state.get("training_history", [])
    return training_history if isinstance(training_history, list) else []


def get_audit_events(session_state: MutableMapping[str, Any]) -> List[Dict[str, Any]]:
    events = session_state.get("audit_events", [])
    return events if isinstance(events, list) else []


def append_audit_event(session_state: MutableMapping[str, Any], event_type: str, payload: Dict[str, Any]) -> None:
    events = get_audit_events(session_state)
    if "audit_events" not in session_state:
        session_state["audit_events"] = events
    session_state["audit_events"].append(
        {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event_type": event_type,
            "payload": payload,
        }
    )
    save_audit_events(session_state)
