"""Home Maintenance logic: groups, tasks, recurrence and due states.

Everything lives in the hub's central SQLite database. Tables are prefixed
``maintenance_`` and there are no owner columns: the hub is open inside the
family tailnet and every task is shared.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from shared.database import get_db
from shared.utilities import clean_text, format_date, utc_now

REPEAT_UNITS = ("days", "weeks", "months", "years")
UNIT_NAMES = {
    "days": "day",
    "weeks": "week",
    "months": "month",
    "years": "year",
}
OVERDUE_AFTER_DAYS = 7
MAX_INTERVAL = 365
MAX_TITLE = 120
MAX_GROUP_NAME = 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS maintenance_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS maintenance_groups_name
    ON maintenance_groups (name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS maintenance_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER
        REFERENCES maintenance_groups (id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    interval_count INTEGER NOT NULL DEFAULT 0,
    interval_unit TEXT NOT NULL DEFAULT 'once'
        CHECK (interval_unit IN ('once', 'days', 'weeks', 'months', 'years')),
    due_on TEXT NOT NULL,
    last_completed_on TEXT,
    completed_on TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS maintenance_tasks_group
    ON maintenance_tasks (group_id, due_on);

CREATE INDEX IF NOT EXISTS maintenance_tasks_due
    ON maintenance_tasks (due_on);
"""


# --- schema -----------------------------------------------------------------


def ensure_schema() -> None:
    """Create the module's tables. Safe to run on every startup."""

    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


# --- groups -----------------------------------------------------------------


def list_groups() -> list[dict]:
    rows = get_db().execute(
        """
        SELECT id, name FROM maintenance_groups
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """
    ).fetchall()
    return [{"id": int(row["id"]), "name": row["name"]} for row in rows]


def create_group(name: str) -> tuple[int | None, str | None]:
    cleaned = clean_text(name, MAX_GROUP_NAME)
    if not cleaned:
        return None, "Give the group a name."

    db = get_db()
    existing = db.execute(
        "SELECT 1 FROM maintenance_groups WHERE lower(name) = lower(?)",
        (cleaned,),
    ).fetchone()
    if existing:
        return None, f"There is already a group named {cleaned}."

    next_position = db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM maintenance_groups"
    ).fetchone()["next"]
    cursor = db.execute(
        "INSERT INTO maintenance_groups (name, position, created_at) VALUES (?, ?, ?)",
        (cleaned, int(next_position), utc_now()),
    )
    db.commit()
    return int(cursor.lastrowid), None


def delete_group(group_id: int) -> bool:
    """Delete a group; its tasks stay and move to the one-time task list."""

    db = get_db()
    if not db.execute(
        "SELECT 1 FROM maintenance_groups WHERE id = ?", (group_id,)
    ).fetchone():
        return False
    db.execute("DELETE FROM maintenance_groups WHERE id = ?", (group_id,))
    db.commit()
    return True


# --- recurrence -------------------------------------------------------------


def _add_months(anchor: date, months: int) -> date:
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def advance_due(anchor: date, count: int, unit: str) -> date:
    """Return the next due date after completing a task on ``anchor``."""

    if unit == "days":
        return anchor + timedelta(days=count)
    if unit == "weeks":
        return anchor + timedelta(weeks=count)
    if unit == "months":
        return _add_months(anchor, count)
    if unit == "years":
        return _add_months(anchor, count * 12)
    return anchor


def describe_recurrence(count: int, unit: str) -> str:
    """The small descriptor shown on a recurring task, e.g. ``Every 3 months``."""

    name = UNIT_NAMES.get(unit)
    if not name or count <= 0:
        return "One-time"
    if count == 1:
        return f"Every {name}"
    return f"Every {count} {name}s"


# --- tasks ------------------------------------------------------------------


def blank_task_values() -> dict[str, str]:
    return {
        "title": "",
        "repeat": "once",
        "interval_count": "1",
        "interval_unit": "months",
        "group_id": "",
        "due_enabled": "",
        "due_on": date.today().isoformat(),
    }


def validate_task(data) -> tuple[dict, str | None]:
    """Validate a task form, returning the values so a failed form can keep them."""

    values = {
        "title": clean_text(data.get("title"), MAX_TITLE),
        "repeat": (
            "recurring"
            if clean_text(data.get("repeat"), 20) == "recurring"
            else "once"
        ),
        "interval_count": clean_text(data.get("interval_count"), 8) or "1",
        "interval_unit": clean_text(data.get("interval_unit"), 12) or "months",
        "group_id": clean_text(data.get("group_id"), 20),
        "due_enabled": (
            "yes" if clean_text(data.get("due_enabled"), 10) == "yes" else ""
        ),
        "due_on": clean_text(data.get("due_on"), 10),
    }

    if not values["title"]:
        return values, "Give the task a name."

    # The date field only counts when its checkbox is ticked; otherwise the
    # task is simply due today and any submitted date is ignored.
    if values["due_enabled"] and values["due_on"]:
        try:
            date.fromisoformat(values["due_on"])
        except ValueError:
            return values, "Use a real due date (YYYY-MM-DD)."
    else:
        values["due_on"] = date.today().isoformat()

    if values["group_id"]:
        try:
            group_id = int(values["group_id"])
        except (TypeError, ValueError):
            return values, "That group no longer exists."
        if not get_db().execute(
            "SELECT 1 FROM maintenance_groups WHERE id = ?", (group_id,)
        ).fetchone():
            return values, "That group no longer exists."
        values["group_id"] = str(group_id)

    if values["repeat"] == "recurring":
        if values["interval_unit"] not in REPEAT_UNITS:
            return values, "Choose how often the task repeats."
        try:
            count = int(values["interval_count"])
        except (TypeError, ValueError):
            return values, "Use a whole number for how often the task repeats."
        if not 1 <= count <= MAX_INTERVAL:
            return values, f"The repeat interval must be between 1 and {MAX_INTERVAL}."
        values["interval_count"] = str(count)

    return values, None


def create_task(values: dict) -> int:
    db = get_db()
    recurring = values["repeat"] == "recurring"
    now = utc_now()
    cursor = db.execute(
        """
        INSERT INTO maintenance_tasks
            (group_id, title, interval_count, interval_unit, due_on,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(values["group_id"]) if values["group_id"] else None,
            values["title"],
            int(values["interval_count"]) if recurring else 0,
            values["interval_unit"] if recurring else "once",
            values["due_on"],
            now,
            now,
        ),
    )
    db.commit()
    return int(cursor.lastrowid)


def complete_task(task_id: int, today: date | None = None) -> bool:
    """Complete a task.

    A recurring task stores the completion and moves its due date on: from the
    original due date when it was completed early, or from today when it was
    completed on time or late. A one-time task is simply marked completed.
    """

    current = today or date.today()
    db = get_db()
    row = db.execute(
        "SELECT * FROM maintenance_tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if not row:
        return False

    interval_count = int(row["interval_count"] or 0)
    unit = row["interval_unit"]
    now = utc_now()

    if unit in REPEAT_UNITS and interval_count > 0:
        due = _parse_date(row["due_on"]) or current
        next_due = advance_due(max(due, current), interval_count, unit)
        db.execute(
            """
            UPDATE maintenance_tasks
            SET due_on = ?, last_completed_on = ?, completed_on = NULL, updated_at = ?
            WHERE id = ?
            """,
            (next_due.isoformat(), current.isoformat(), now, task_id),
        )
    else:
        db.execute(
            """
            UPDATE maintenance_tasks
            SET completed_on = ?, updated_at = ?
            WHERE id = ?
            """,
            (current.isoformat(), now, task_id),
        )

    db.commit()
    return True


def reopen_task(task_id: int, today: date | None = None) -> bool:
    """Undo a completion. A recurring task becomes due now."""

    current = today or date.today()
    db = get_db()
    row = db.execute(
        "SELECT * FROM maintenance_tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if not row:
        return False

    interval_count = int(row["interval_count"] or 0)
    unit = row["interval_unit"]
    now = utc_now()

    if unit in REPEAT_UNITS and interval_count > 0:
        db.execute(
            """
            UPDATE maintenance_tasks
            SET due_on = ?, last_completed_on = NULL, completed_on = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (current.isoformat(), now, task_id),
        )
    else:
        db.execute(
            """
            UPDATE maintenance_tasks
            SET completed_on = NULL, updated_at = ?
            WHERE id = ?
            """,
            (now, task_id),
        )

    db.commit()
    return True


def delete_task(task_id: int) -> bool:
    db = get_db()
    if not db.execute(
        "SELECT 1 FROM maintenance_tasks WHERE id = ?", (task_id,)
    ).fetchone():
        return False
    db.execute("DELETE FROM maintenance_tasks WHERE id = ?", (task_id,))
    db.commit()
    return True


# --- reading ----------------------------------------------------------------


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _due_label(*, completed: bool, resting: bool, due: date, days_until: int) -> str:
    if completed:
        return "Completed"
    if resting:
        return f"Next due {format_date(due.isoformat())}"
    if days_until == 0:
        return "Due today"
    if days_until == 1:
        return "Due tomorrow"
    if days_until > 1:
        return f"Due in {days_until} days"
    if days_until == -1:
        return "Due 1 day ago"
    return f"Due {abs(days_until)} days ago"


def _countdown(days_until: int) -> str:
    if days_until == 1:
        return "in 1 day"
    return f"in {days_until} days"


def _task_view(row, today: date) -> dict[str, Any]:
    interval_count = int(row["interval_count"] or 0)
    unit = row["interval_unit"]
    recurring = unit in REPEAT_UNITS and interval_count > 0
    due = _parse_date(row["due_on"]) or today
    days_until = (due - today).days
    days_overdue = -days_until
    completed = row["completed_on"] is not None
    # A recurring task rests after completion until its next due date arrives.
    resting = (
        recurring
        and row["last_completed_on"] is not None
        and not completed
        and days_until > 0
    )
    overdue = (
        not completed
        and not resting
        and days_overdue >= OVERDUE_AFTER_DAYS
    )

    if completed:
        status = "done"
    elif overdue:
        status = "overdue"
    elif resting:
        status = "resting"
    elif days_until <= 0:
        status = "due"
    else:
        status = "active"

    return {
        "id": int(row["id"]),
        "group_id": None if row["group_id"] is None else int(row["group_id"]),
        "title": row["title"],
        "recurring": recurring,
        "recurrence_label": (
            describe_recurrence(interval_count, unit) if recurring else "One-time"
        ),
        "due_on": due.isoformat(),
        "due_label": _due_label(
            completed=completed,
            resting=resting,
            due=due,
            days_until=days_until,
        ),
        "countdown": _countdown(days_until) if resting else "",
        "status": status,
        "completed": completed,
        "days_until": days_until,
        "days_overdue": days_overdue,
    }


STATUS_ORDER = {"overdue": 0, "due": 1, "active": 1, "resting": 2, "done": 2}


def sort_tasks(tasks: list[dict]) -> list[dict]:
    """Overdue first, then what is due soonest, then resting or completed."""

    return sorted(
        tasks,
        key=lambda task: (
            STATUS_ORDER.get(task["status"], 1),
            task["due_on"],
            task["title"].lower(),
        ),
    )


def list_board(today: date | None = None) -> dict[str, Any]:
    current = today or date.today()
    rows = get_db().execute("SELECT * FROM maintenance_tasks").fetchall()
    tasks = [_task_view(row, current) for row in rows]

    groups = []
    for group in list_groups():
        groups.append(
            {
                **group,
                "tasks": sort_tasks(
                    [task for task in tasks if task["group_id"] == group["id"]]
                ),
            }
        )

    standalone = sort_tasks(
        [task for task in tasks if task["group_id"] is None]
    )

    return {
        "groups": groups,
        "standalone": standalone,
        "total": len(tasks),
        "overdue": sum(1 for task in tasks if task["status"] == "overdue"),
        "resting": sum(1 for task in tasks if task["status"] in {"resting", "done"}),
    }
