from codex.metrics.reporters._base import MonthlyReporter
from codex.metrics.reports import MonthlyReport


def list_monthly_reports(reporter: MonthlyReporter) -> list[MonthlyReport]:
    _reports = (
        reporter.report(**_kwargs)
        for _kwargs in reporter.iter_report_kwargs()
    )
    return [_report for _report in _reports if (_report is not None)]
