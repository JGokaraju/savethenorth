"""§6.7 Plant throughput ceiling and flare-slip plausibility."""
from __future__ import annotations

from backend.settings import cfg, cfg_entry


def ceiling_t_h(capacity_mmscfd: float, ch4_fraction: float | None = None) -> float:
    f = cfg("plant", "ch4_fraction") if ch4_fraction is None else ch4_fraction
    g_per_day = capacity_mmscfd * 1e6 * f * cfg("plant", "ch4_g_per_scf")
    return g_per_day / 24 / 1e6


def bounds(q_kg_h: float, capacity_mmscfd: float) -> dict:
    f_lo, f_hi = cfg_entry("plant", "ch4_fraction")["range"]
    ce = cfg("plant", "combustion_efficiency")
    ce_lo, ce_hi = cfg_entry("plant", "combustion_efficiency")["range"]
    ceil = ceiling_t_h(capacity_mmscfd)
    q_t = q_kg_h / 1000
    req = q_t / (1 - ce)
    if q_t > ceil:  # the estimate alone exceeds the plant's throughput -> data-quality flag
        cls = "estimate_physically_implausible"
    elif req > ceil:
        cls = "flare_slip_implausible"
    else:
        cls = "flare_slip_possible"
    return {
        "q_t_h": q_t, "capacity_mmscfd": capacity_mmscfd,
        "ceiling_t_h": ceil, "ceiling_range_t_h": [ceiling_t_h(capacity_mmscfd, f_lo), ceiling_t_h(capacity_mmscfd, f_hi)],
        "combustion_efficiency": ce,
        "required_flared_ch4_t_h": req,
        "required_flared_range_t_h": [q_t / (1 - ce_lo), q_t / (1 - ce_hi)],
        "required_fraction_of_ceiling": req / ceil,
        "q_fraction_of_ceiling": q_t / ceil,
        "classification": cls,
        "interpretation": {
            "flare_slip_implausible": "Explaining the plume as unburned slip from a lit flare would require flaring "
                                      "more methane than the plant can process; a lit, efficient flare is not a plausible sole source.",
            "estimate_physically_implausible": "The estimate exceeds the plant's total methane throughput — treat as a data-quality flag.",
            "flare_slip_possible": "Combustion slip from a lit flare is physically possible at this rate.",
        }[cls],
    }
