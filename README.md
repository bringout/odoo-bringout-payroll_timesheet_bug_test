# bringout_payroll_timesheet_bug_test

**Intentionally-buggy demo module.** Ships two classic multi-company
bugs and demonstrates that `multi_company_protect_psql_payroll` catches
both at the PostgreSQL level.

## Bug A — Count All Employees (read bug, non-destructive)

```python
count = len(env['hr.employee'].sudo().search([]))
```

A developer writes a "headcount" widget for a dashboard and never asks
"of which company?" The call silently returns the grand total across
every entity in the database. On a locked session, RLS filters the
underlying SELECT down to the locked company so the buggy code
accidentally returns the correct value.

| Session | Result |
| --- | --- |
| Admin / unlocked user | **Bug manifests.** Returns total headcount across all 5 companies (e.g. 10). |
| Payroll clerk locked to CompanyBA-1 | **Bug contained.** Returns 3 — only Bosnia employees visible. |

## Bug B — Tag All Timesheets (write bug, visible in UI)

```python
tag = f"BUG-B run by {env.user.name}"
env['account.analytic.line'].search([]).write({'name': tag})
```

A "mark all timesheets as reviewed by me" routine forgets the company
filter on search and overwrites every returned row's `name` field
(the description that shows up in the Timesheets list). The effect is
immediately visible in *Timesheets → All Timesheets* — no need to
inspect the DB.

| Session | Result |
| --- | --- |
| Admin / unlocked user | **Bug manifests.** Every timesheet in the database gets its `name` overwritten with `"BUG-B run by …"` — including Slovenia, both Croatias, Bosnia. Visible in the UI right away. |
| Locked payroll clerk | **Bug contained.** `USING` filter returns only the clerk's company rows; only those get tagged. Other companies' timesheets untouched. No error. |

## Installation

Dependency on `multi_company_protect_psql_payroll` is **not** technical —
the module works without it. But the whole point is to run it in an
environment where the RLS module is installed and a user is locked.

## Running

*Payroll → Bug Testing → Run Timesheet Bug Reproduction*

1. Choose a "target company" — the `company_id` that the bug will write
   into every timesheet.
2. Click *Run Buggy Bulk Update*.
3. The result screen shows:
   - Before/after per-company counts of `account.analytic.line`
   - Any PostgreSQL error raised (RLS violations land here)

## License

AGPL-3. Do not install on production databases — the module is
destructive by design.
