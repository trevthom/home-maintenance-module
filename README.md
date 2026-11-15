# Home Maintenance

A Thompson hub module for the jobs around the house: gutters, filters,
servicing, seasonal checks and the rest of it.

## What it does

- **Groups are optional.** Add groups such as *Outside* or *Kitchen*, or leave a
  task standalone. Deleting a group keeps its tasks and makes them standalone.
- **One-time or recurring tasks.** A recurring task stores how often it comes
  back (for example every 1 week, every 3 months or every 1 year) and shows that
  descriptor on the task.
- **Click to complete.** A completed recurring task turns grey with a countdown
  of the days until it is due again — for example *in 27 days*. One-time tasks
  turn grey and read *Completed*, and either kind can be reopened.
- **Overdue at one week.** A task that is seven or more days past due turns red
  and gets an **Overdue** label.

Everything is family-shared. Like the rest of the hub there are no accounts,
sessions or per-user data, and the tailnet is the access boundary.

## Install in the hub

Copy the module files into the hub's `applications/` folder as
`applications/home-maintenance-module/`:

```
applications/home-maintenance-module/
├── __init__.py
├── app.py
├── logic.py
├── routes.py
├── app.json
├── templates/home_maintenance/home_maintenance.html
└── static/
    ├── home_maintenance.css
    └── home_maintenance.js
```

The hub discovers any folder with an `app.py` and mounts it automatically.
This module's Blueprint is `home_maintenance`, so its default route is
`/home-maintenance-module`.

For the card name, route and colour used in the Thompson hub, add the matching
entry to `config/apps.json`:

```json
{
  "id": "home_maintenance_module",
  "name": "Home Maintenance",
  "enabled": true,
  "route": "/maintenance",
  "icon": "list-checks",
  "description": "The jobs around the house, and when they're next due.",
  "accent": "#6E8A79",
  "order": 2
}
```

## Data

All tables live in the hub's central SQLite database:

- `maintenance_groups` — optional groups, in display order.
- `maintenance_tasks` — tasks, their group (or `NULL` when standalone), repeat
  interval, next due date and completion dates.

`init_app()` creates them idempotently on every startup.

## Behaviour notes

- A new task is due on the date chosen, or today when none is given.
- Completing a recurring task early advances from its original due date;
  completing it on time or late advances from today. Completing a weekly task
  on its due date puts it `in 7 days`.
- Reopening a recurring task makes it due now. Reopening a one-time task clears
  its completion.
- A completed recurring task stays visible and grey until its next due date
  arrives, then returns to the normal list.
- Overdue means seven or more days past the due date and not completed.

## Check

```bash
python -m compileall -q applications/home-maintenance-module
```

Then open `/maintenance` in the hub: add a group, add a standalone task, add a
recurring task, mark each complete, and check the grey countdown and the
overdue state (a task due more than a week ago).
