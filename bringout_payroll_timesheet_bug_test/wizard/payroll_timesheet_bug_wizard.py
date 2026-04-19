import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PayrollTimesheetBugWizard(models.TransientModel):
    _name = "payroll.timesheet.bug.wizard"
    _description = "Multi-company bug reproductions (test bed for PSQL RLS)"

    scenario = fields.Char(readonly=True)

    # --- Scenario A: count-employees bug ---------------------------------
    employee_count = fields.Integer(readonly=True, string="Total employees found")
    employee_breakdown = fields.Text(readonly=True, string="Per-company breakdown")

    # --- Scenario B: timesheet-rewrite bug -------------------------------
    target_company_id = fields.Many2one(
        "res.company",
        string="Target Company (rewrite bug)",
        default=lambda self: self.env.company,
        help=(
            "Used only by the 'Reassign All Timesheets' button. The "
            "company_id that the buggy bulk update will write into "
            "every analytic line."
        ),
    )
    lines_affected = fields.Integer(readonly=True)
    before_state = fields.Text(readonly=True, string="Counts BEFORE write")
    after_state = fields.Text(readonly=True, string="Counts AFTER write")
    error_message = fields.Text(readonly=True, string="PostgreSQL error (if any)")

    finished = fields.Boolean(default=False, readonly=True)

    # --- Helpers ---------------------------------------------------------

    def _analytic_counts(self):
        """Per-company row counts of ``account_analytic_line``.

        Runs via direct SQL so the RLS policy applies to this query
        exactly as it does to the buggy write path. On a locked
        session this returns only the locked company's rows.
        """
        self.env.cr.execute(
            "SELECT COALESCE(c.name, '(null)') AS company, COUNT(l.id) "
            "FROM account_analytic_line l "
            "LEFT JOIN res_company c ON c.id = l.company_id "
            "GROUP BY c.name ORDER BY c.name"
        )
        rows = self.env.cr.fetchall()
        if not rows:
            return "(no rows visible)"
        return "\n".join(f"  {name}: {n}" for name, n in rows)

    def _employee_counts(self):
        self.env.cr.execute(
            "SELECT COALESCE(c.name, '(null)') AS company, COUNT(e.id) "
            "FROM hr_employee e "
            "LEFT JOIN res_company c ON c.id = e.company_id "
            "GROUP BY c.name ORDER BY c.name"
        )
        rows = self.env.cr.fetchall()
        if not rows:
            return "(no rows visible)"
        return "\n".join(f"  {name}: {n}" for name, n in rows)

    # --- Scenario A: count-employees bug ---------------------------------

    def action_run_count_bug(self):
        """Count employees without any company filter.

        The bug: a developer writes a dashboard/report query like
        ``len(env['hr.employee'].search([]))`` and never asks
        "from which company?". In a multi-company database this
        returns the grand total across every entity — a privacy /
        correctness problem depending on intent.

        Outcome matrix:
          - Admin / unlocked user: returns the total row count
            across every company in the database. The bug
            manifests silently.
          - Locked payroll clerk: the RLS ``USING`` policy on
            ``hr_employee`` filters ``search([])`` to their own
            company. The buggy query accidentally returns the
            correct value — RLS contained the bug.
        """
        self.ensure_one()
        # Note: .sudo() is deliberate — it mirrors a naive dashboard
        # that tries to count "all employees" regardless of the
        # user's access rights. ORM record rules would also filter
        # this, but we explicitly bypass them to prove that RLS is
        # the backstop even when the application-layer rules are
        # side-stepped.
        all_employees = self.env["hr.employee"].sudo().search([])
        count = len(all_employees)
        _logger.warning(
            "payroll_timesheet_bug_test: buggy count-all-employees "
            "returned %d rows", count,
        )
        self.scenario = "count_employees"
        self.employee_count = count
        self.employee_breakdown = self._employee_counts()
        self.finished = True
        return self._reopen()

    # --- Scenario B: timesheet-rewrite bug -------------------------------

    def action_run_rewrite_bug(self):
        """Bulk rewrite every analytic line's ``company_id``.

        The bug: a "fix this company's data" routine forgets the
        company filter on search, and blindly writes the target
        company_id onto every returned row.

        Outcome matrix:
          - Admin / unlocked user: every analytic line in the
            database is reassigned. Silent data corruption.
          - Locked payroll clerk, target = locked company:
            ``USING`` filter returns only locked-company rows;
            write succeeds in-company — contained but still
            "wrong" from the intent perspective.
          - Locked payroll clerk, target != locked company:
            ``WITH CHECK`` rejects with ``new row violates
            row-level security policy``. Transaction rolled back.
        """
        self.ensure_one()
        if not self.target_company_id:
            self.target_company_id = self.env.company
        self.scenario = "rewrite_timesheets"
        self.before_state = self._analytic_counts()
        self.error_message = ""
        self.lines_affected = 0
        try:
            # === THE BUG ===
            lines = self.env["account.analytic.line"].search([])
            count = len(lines)
            if count:
                lines.write({"company_id": self.target_company_id.id})
            self.env.cr.flush()
            self.lines_affected = count
            _logger.warning(
                "payroll_timesheet_bug_test: buggy rewrite touched "
                "%d analytic lines -> company_id=%d",
                count, self.target_company_id.id,
            )
        except Exception as exc:  # noqa: BLE001
            self.error_message = f"{type(exc).__name__}: {exc}"
            _logger.info(
                "payroll_timesheet_bug_test: rewrite aborted by %s",
                type(exc).__name__,
            )
            self.env.cr.rollback()
        self.after_state = self._analytic_counts()
        self.finished = True
        return self._reopen()

    # --- Reopen helper ---------------------------------------------------

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
