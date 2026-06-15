"""Cell–cell contact detection + classification (analysis/contacts.py)."""
import numpy as np

from maskviewer.analysis import contacts, cell_metrics, exporters


def test_classify_contact_thresholds():
    assert contacts.classify_contact(0.0, 0) == "free"
    assert contacts.classify_contact(0.5, 1) == "free"          # below MIN_CONTACT_PX
    assert contacts.classify_contact(0.10, 20) == "point"       # small interface
    assert contacts.classify_contact(0.40, 50) == "extensive"   # large interface
    assert contacts.classify_contact(0.25, 50) == "extensive"   # at the threshold


def _two_touching():
    """Two cells sharing a long vertical edge (an extensive interface)."""
    L = np.zeros((40, 40), np.int32)
    L[5:25, 5:15] = 1
    L[5:25, 15:25] = 2
    return L


def test_frame_contacts_extensive_shared_edge():
    fc = contacts.frame_contacts(_two_touching(), scale=1.0)
    assert fc[1]["contact_class"] == "extensive"
    assert fc[2]["contact_class"] == "extensive"
    assert fc[1]["n_contacts"] == 1 and fc[2]["n_contacts"] == 1
    assert 2 in fc[1]["partners"] and 1 in fc[2]["partners"]
    assert fc[1]["contact_fraction"] > 0.25
    assert fc[1]["contact_length"] > 0


def test_frame_contacts_free_when_far_apart():
    L = np.zeros((40, 40), np.int32)
    L[2:8, 2:8] = 1
    L[30:38, 30:38] = 2                       # nowhere near cell 1
    fc = contacts.frame_contacts(L)
    assert fc[1]["contact_class"] == "free" and fc[1]["n_contacts"] == 0
    assert fc[2]["contact_class"] == "free"
    assert fc[1]["contact_fraction"] == 0.0 and fc[1]["partners"] == {}


def test_frame_contacts_point_for_small_corner_touch():
    L = np.zeros((40, 40), np.int32)
    L[5:25, 5:15] = 1                         # big cell
    L[24:27, 14:17] = 2                       # tiny block touching one corner
    fc = contacts.frame_contacts(L)
    # the big cell engages only a small fraction of its boundary → point
    assert fc[1]["contact_class"] == "point"
    assert fc[1]["contact_fraction"] < contacts.EXTENSIVE_FRAC


def test_frame_contacts_single_and_empty():
    one = np.zeros((20, 20), np.int32)
    one[5:15, 5:15] = 1
    fc = contacts.frame_contacts(one)
    assert fc[1]["contact_class"] == "free" and fc[1]["n_contacts"] == 0
    assert contacts.frame_contacts(np.zeros((20, 20), np.int32)) == {}


def test_gap_tolerance_controls_detection():
    """A one-pixel background gap is a contact at gap≥2 but not at the strict gap=1."""
    L = np.zeros((30, 30), np.int32)
    L[5:25, 5:14] = 1
    L[5:25, 16:25] = 2                        # column 14,15 background between them
    assert contacts.frame_contacts(L, max_gap_px=1.0)[1]["n_contacts"] == 0
    assert contacts.frame_contacts(L, max_gap_px=3.0)[1]["n_contacts"] == 1


def test_contact_summary_fractions():
    """A 4-frame stack: cells touch only in the later frames."""
    L = np.zeros((4, 40, 40), np.int32)
    for t in range(4):
        L[t, 5:25, 5:15] = 1
    L[2:, 5:25, 15:25] = 2                    # cell 2 appears (touching 1) at frame 2
    s = contacts.contact_summary(L)
    # cell 1 present 4 frames, in contact for 2 of them
    assert abs(s[1]["frac_in_contact"] - 0.5) < 1e-9
    assert s[1]["frac_extensive_contact"] == 0.5
    assert s[2]["frac_in_contact"] == 1.0    # cell 2 only exists while touching
    assert s[1]["mean_n_contacts"] == 0.5


def test_contacts_flow_into_per_frame_and_per_cell_tables():
    """The contact columns reach the per-frame and per-cell exporter tables."""
    L = np.zeros((3, 40, 40), np.int32)
    L[:, 5:25, 5:15] = 1
    L[:, 5:25, 15:25] = 2
    pf = exporters.per_frame_table(L, um_per_px=0.5)
    for col in ("contact_fraction", "n_contacts", "max_contact_fraction",
                "contact_length_um", "contact_state"):
        assert col in pf.columns, col
    assert (pf["contact_state"] == "extensive").all()
    pc = exporters.per_cell_table(L, um_per_px=0.5, per_frame_df=pf)
    for col in ("mean_contact_fraction", "mean_n_contacts", "frac_in_contact",
                "frac_extensive_contact", "mean_contact_length_um"):
        assert col in pc.columns, col
    assert (pc["frac_in_contact"] == 1.0).all()


def test_contacts_disabled_omits_columns():
    L = np.zeros((2, 30, 30), np.int32)
    L[:, 5:15, 5:15] = 1
    recs = cell_metrics.per_frame_records(L, with_contacts=False)
    assert all("contact_fraction" not in r for r in recs)


def test_cell_frame_table_contact_series():
    """The per-cell-info plot exposes the contact series for a clicked cell."""
    L = np.zeros((3, 40, 40), np.int32)
    L[:, 5:25, 5:15] = 1
    L[:, 5:25, 15:25] = 2
    out = cell_metrics.cell_frame_table(
        L, 1, um_per_px=0.5, metrics={"contact_fraction", "contact_state_code"})
    assert "contact_fraction" in out["series"]
    assert "contact_state_code" in out["series"]
    frac, _ = out["series"]["contact_fraction"]
    assert np.all(frac > 0.25)               # extensive interface every frame
    code, _ = out["series"]["contact_state_code"]
    assert np.all(code == contacts.CONTACT_CODE["extensive"])
