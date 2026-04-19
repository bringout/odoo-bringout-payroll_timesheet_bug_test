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

## Bug B — Reassign All Timesheets (write bug, destructive)

```python
env['account.analytic.line'].search([]).write({'company_id': target_id})
```

A "bulk-fix" routine forgets the company filter on search and blindly
rewrites every returned row's `company_id`.

| Session | Result |
| --- | --- |
| Admin / unlocked user | **Bug manifests.** All analytic lines get their `company_id` rewritten. Silent cross-company data corruption. |
| Locked clerk, target = locked company | **Bug contained.** `USING` filter returns only locked-company rows; in-company write succeeds. |
| Locked clerk, target ≠ locked company | **Bug caught.** `WITH CHECK` rejects with `new row violates row-level security policy`. Transaction rolled back. |

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
