{
    "name": "Payroll Timesheet Bug Test (RLS demo)",
    "summary": "Deliberately-broken wizard that reproduces a cross-company timesheet write bug, to demonstrate PSQL RLS protection",
    "description": """
Payroll Timesheet Bug Test (RLS demo)
=====================================

Intentionally-buggy demo module. Not for production.

Ships a wizard that runs:

    self.env['account.analytic.line'].search([]).write({
        'company_id': target_company_id
    })

A classic multi-company bug: search without company filter, blind
bulk update. On a database without RLS, this silently corrupts
every other company's timesheets. With
`multi_company_protect_psql_payroll` installed and the user locked
via `psql_company_lock_id`, PostgreSQL rejects the write.

Meant to be paired with `multi_company_example_ba_hr_si_data` on a
test bed. See README.md for the expected behavior matrix.
    """,
    "version": "16.0.1.1.1",
    "author": "bring.out doo Sarajevo",
    "website": "https://www.bring.out.ba",
    "category": "Human Resources/Payroll",
    "license": "AGPL-3",
    "depends": [
        "hr_timesheet",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/payroll_timesheet_bug_wizard_view.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
