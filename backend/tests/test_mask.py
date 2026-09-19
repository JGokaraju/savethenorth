import numpy as np
import pytest

from backend.science import mask
from backend.science.common import DataGap


def test_mask_keeps_component_near_source_and_ignores_distant_blob(crop_factory):
    rng = np.random.default_rng(3)
    enh = rng.normal(0, 20, (201, 201))
    enh[80:101, 98:103] += 1500     # near source (centre pixel 100,100)
    enh[10:25, 10:25] += 1500       # distant blob, > 5 km away
    crop = crop_factory(enh)
    bg = mask.background(crop)
    m = mask.plume_mask(crop, bg, 2.5)
    assert m.mask[90, 100]
    assert not m.mask[15:20, 15:20].any()
    assert m.n_components == 1


def test_no_plume_is_data_gap(crop_factory):
    rng = np.random.default_rng(4)
    crop = crop_factory(rng.normal(0, 20, (201, 201)))
    bg = mask.background(crop)
    with pytest.raises(DataGap):
        mask.plume_mask(crop, bg, 4.0)
