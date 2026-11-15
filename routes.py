"""Home Maintenance routes, mounted at /maintenance by the hub.

Every handler stays relative to the Blueprint prefix. There is no login, no
``current_user`` and no CSRF token: the hub is open inside the tailnet.
"""

from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for

from .logic import (
    REPEAT_UNITS,
    blank_task_values,
    complete_task,
    create_group,
    create_task,
    delete_group,
    delete_task,
    list_board,
    reopen_task,
    validate_task,
)

blueprint = Blueprint(
    "home_maintenance",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


def _render(
    *,
    error: str | None = None,
    values: dict | None = None,
    group_error: str | None = None,
    status: int = 200,
):
    return (
        render_template(
            "home_maintenance/home_maintenance.html",
            board=list_board(),
            error=error,
            group_error=group_error,
            values=values or blank_task_values(),
            repeat_units=REPEAT_UNITS,
        ),
        status,
    )


def _back():
    return redirect(url_for("home_maintenance.index"), code=303)


# --- pages ------------------------------------------------------------------


@blueprint.get("/", strict_slashes=False)
def index():
    return _render()


# --- task actions -----------------------------------------------------------


@blueprint.post("/tasks")
def task_create():
    values, error = validate_task(request.form)
    if error:
        return _render(error=error, values=values, status=400)

    create_task(values)
    return _back()


@blueprint.post("/tasks/<int:task_id>/complete")
def task_complete(task_id: int):
    if not complete_task(task_id):
        abort(404)
    return _back()


@blueprint.post("/tasks/<int:task_id>/reopen")
def task_reopen(task_id: int):
    if not reopen_task(task_id):
        abort(404)
    return _back()


@blueprint.post("/tasks/<int:task_id>/delete")
def task_delete(task_id: int):
    if not delete_task(task_id):
        abort(404)
    return _back()


# --- group actions ----------------------------------------------------------


@blueprint.post("/groups")
def group_create():
    _, error = create_group(request.form.get("name"))
    if error:
        return _render(group_error=error, status=400)
    return _back()


@blueprint.post("/groups/<int:group_id>/delete")
def group_delete(group_id: int):
    if not delete_group(group_id):
        abort(404)
    return _back()
