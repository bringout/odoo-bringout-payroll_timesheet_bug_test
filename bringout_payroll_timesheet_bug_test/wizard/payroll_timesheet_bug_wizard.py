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

    # --- Scenario B: timesheet-tag bug -----------------------------------
    lines_affected = fields.Integer(readonly=True, string="Timesheets tagged")
    before_state = fields.Text(readonly=True, string="Visible BEFORE")
    after_state = fields.Text(readonly=True, string="Visible AFTER")
    error_message = fields.Text(readonly=True, string="PostgreSQL error (if any)")

    finished = fields.Boolean(default=False, readonly=True)

    # --- Helpers ---------------------------------------------------------

    def _analytic_lines_preview(self, limit=30):
        """Return a readable preview of what this session currently
        sees on ``account_analytic_line``. RLS applies, so on a locked
        session the output is naturally filtered.
        """
        self.env.cr.execute(
            "SELECT l.id, "
            "       COALESCE(c.name, '(null)') AS company, "
            "       l.name "
            "FROM account_analytic_line l "
            "LEFT JOIN res_company c ON c.id = l.company_id "
            "ORDER BY l.id "
            "LIMIT %s",
            [limit],
        )
        rows = self.env.cr.fetchall()
        if not rows:
            return "(no rows visible)"
        return "\n".join(f"  #{rid}  {comp}  {name}" for rid, comp, name in rows)

    # --- Scenario A: count-employees bug ---------------------------------

    def action_run_count_bug(self):
        """Count employees without any company filter.

        Outcome matrix:
          - Admin / unlocked user: returns the grand total across every
            company. The bug manifests silently.
          - Locked payroll clerk: RLS ``USING`` policy on
            ``hr_employee`` filters ``search([])`` to the locked
            company. The buggy query accidentally returns the correct
            per-company value — RLS contained the bug.
        """
        self.ensure_one()
        all_employees = self.env["hr.employee"].sudo().search([])
        count = len(all_employees)
        _logger.warning(
            "payroll_timesheet_bug_test: buggy count-all-employees "
            "returned %d rows", count,
        )
        self.scenario = "count_employees"
        self.employee_count = count
        # Per-company breakdown via direct SQL (also RLS-subject):
        self.env.cr.execute(
            "SELECT COALESCE(c.name, '(null)'), COUNT(e.id) "
            "FROM hr_employee e "
            "LEFT JOIN res_company c ON c.id = e.company_id "
            "GROUP BY c.name ORDER BY c.name"
        )
        rows = self.env.cr.fetchall()
        self.employee_breakdown = "\n".join(
            f"  {name}: {n}" for name, n in rows
        ) or "(no rows visible)"
        self.finished = True
        return self._reopen()

    # --- Scenario B: timesheet-tag bug -----------------------------------

    def action_run_tag_bug(self):
        """Tag every timesheet entry with a 'reviewed by X' marker.

        The intent a developer might have had: "stamp all my
        reviewed timesheets with my name for audit". The bug: no
        company filter on the search.

        Outcome matrix:
          - Admin / unlocked user: every analytic line in the
            database gets its ``name`` overwritten with the tag —
            including other companies' timesheets. Silent
            cross-company pollution visible in the Timesheets list.
          - Locked payroll clerk: RLS ``USING`` policy filters
            ``search([])`` to the locked company. Only the clerk's
            own timesheets get tagged. Other companies untouched.
            The bug is fully contained without any error.

        This is the cleanest demo of RLS because the effect is
        immediately visible in the Timesheets UI (the ``name`` column
        is the default description shown in tree views).
        """
        self.ensure_one()
        self.scenario = "tag_timesheets"
        self.before_state = self._analytic_lines_preview()
        self.error_message = ""
        self.lines_affected = 0
        tag = f"BUG-B run by {self.env.user.name}"
        try:
            # === THE BUG ===
            # Missing: ("company_id", "=", some_expected.id)
            # .sudo() bypasses ORM record rules — the user's company
            # switcher state is ignored. On a non-RLS session, this is
            # equivalent to "what every row in the DB actually is" and
            # the buggy write cascades everywhere. On a RLS-locked
            # session, PostgreSQL still filters the SELECT to the
            # locked company (sudo cannot override SQL-level RLS), so
            # the same line of code only touches one company's rows.
            lines = self.env["account.analytic.line"].sudo().search([])
            count = len(lines)
            if count:
                lines.write({"name": tag})
            self.env.cr.flush()
            self.lines_affected = count
            _logger.warning(
                "payroll_timesheet_bug_test: buggy tag bulk-update "
                "touched %d analytic lines with %r",
                count, tag,
            )
        except Exception as exc:  # noqa: BLE001
            self.error_message = f"{type(exc).__name__}: {exc}"
            _logger.info(
                "payroll_timesheet_bug_test: tag update aborted by %s",
                type(exc).__name__,
            )
            self.env.cr.rollback()
        self.after_state = self._analytic_lines_preview()
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
