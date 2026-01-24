"""Human interaction task actions.

This module provides task actions for human-in-the-loop workflows:
- Data entry (structured input collection)
- Data display (information presentation with acknowledgment)
"""

from zebra_tasks.human.data_display import DataDisplayAction
from zebra_tasks.human.data_entry import DataEntryAction

__all__ = [
    "DataEntryAction",
    "DataDisplayAction",
]
