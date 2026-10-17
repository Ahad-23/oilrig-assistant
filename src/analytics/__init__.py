"""
Analytics package providing deterministic query execution.
"""

from src.analytics.domain_queries import (
    get_well_current_status,
    get_area_non_producing_wells,
    get_well_temperature_trend,
    get_well_spills_history,
    calculate_well_downtime_days,
    rank_area_downtime,
    get_area_recent_spills_geospatial,
    aggregate_spills_matrix,
)
from src.analytics.compliance_queries import (
    get_well_compliance_status,
    get_area_uncontained_spills,
)

__all__ = [
    "get_well_current_status",
    "get_area_non_producing_wells",
    "get_well_temperature_trend",
    "get_well_spills_history",
    "calculate_well_downtime_days",
    "rank_area_downtime",
    "get_area_recent_spills_geospatial",
    "aggregate_spills_matrix",
    "get_well_compliance_status",
    "get_area_uncontained_spills",
]

