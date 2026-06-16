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
    # the toggle propagates through the exporter table too (comparison gating path)
    pf_off = exporters.per_frame_table(L, with_contacts=False)
    assert "contact_fraction" not in pf_off.columns
    pf_on = exporters.per_frame_table(L, with_contacts=True)
    assert "contact_fraction" in pf_on.columns


def test_contact_episodes_counts_runs_and_gaps():
    # frames 0..6 contiguous: in-contact pattern T T F T T T F → 2 episodes (len 2, 3)
    n, durs = contacts.contact_episodes(
        [0, 1, 2, 3, 4, 5, 6], [1, 1, 0, 1, 1, 1, 0])
    assert n == 2 and durs == [2, 3]
    # a frame gap (5→8) breaks an otherwise-continuous in-contact run
    n2, durs2 = contacts.contact_episodes([4, 5, 8, 9], [1, 1, 1, 1])
    assert n2 == 2 and durs2 == [2, 2]
    assert contacts.contact_episodes([0, 1, 2], [0, 0, 0]) == (0, [])


def test_frame_interfaces_returns_contacting_pixels():
    ys, xs, codes = contacts.frame_interfaces(_two_touching())
    assert ys.size == xs.size == codes.size and ys.size > 0
    assert set(codes.tolist()) <= {1, 2}                 # point / extensive codes
    # an isolated pair yields no interface pixels
    L = np.zeros((40, 40), np.int32)
    L[2:8, 2:8] = 1
    L[30:38, 30:38] = 2
    iy, ix, ic = contacts.frame_interfaces(L)
    assert iy.size == 0


def test_contact_summary_event_dynamics():
    L = np.zeros((6, 40, 40), np.int32)
    for t in range(6):
        L[t, 5:25, 5:15] = 1                 # cell 1 present all 6 frames
    L[2:4, 5:25, 15:25] = 2                  # cell 2 touches only frames 2,3
    s = contacts.contact_summary(L, dt_min=2.0)
    assert s[1]["n_contact_events"] == 1                 # one contiguous episode
    assert s[1]["mean_contact_duration"] == 2 * 2.0      # 2 frames × 2 min
    assert s[1]["contact_event_rate"] == 1 / (6 * 2.0)


def test_contact_event_columns_in_per_cell_table():
    L = np.zeros((4, 40, 40), np.int32)
    L[:, 5:25, 5:15] = 1
    L[1:3, 5:25, 15:25] = 2                  # cell 1 in contact frames 1,2
    pc = exporters.per_cell_table(L, um_per_px=0.5, dt_min=1.0)
    for col in ("n_contact_events", "mean_contact_duration_min", "contact_events_per_min"):
        assert col in pc.columns, col
    r1 = pc[pc["cell_id"] == 1].iloc[0]
    assert r1["n_contact_events"] == 1 and r1["mean_contact_duration_min"] == 2.0


def test_contact_pairs_which_when_degree():
    """One record per cell pair that touches — which cells, when, and the degree."""
    L = np.zeros((6, 40, 40), np.int32)
    for t in range(6):
        L[t, 5:25, 5:15] = 1                 # cell 1 present all frames
    L[2:5, 5:25, 15:25] = 2                  # cell 2 touches cell 1 on frames 2,3,4
    pairs = contacts.contact_pairs(L, dt_min=3.0)
    assert len(pairs) == 1
    p = pairs[0]
    assert (p["cell_a"], p["cell_b"]) == (1, 2)                  # which cells
    assert (p["first_frame"], p["last_frame"]) == (2, 4)        # when
    assert p["n_frames_in_contact"] == 3 and p["n_episodes"] == 1
    assert p["mean_episode_min"] == 3 * 3.0                     # 3 frames × 3 min
    assert p["max_contact_fraction"] > 0.25                     # degree (extensive)


def test_contact_pairs_separate_partners_and_none():
    L = np.zeros((4, 60, 60), np.int32)
    L[:, 5:25, 5:15] = 1
    L[:2, 5:25, 15:25] = 2                   # cell 2 touches 1 on frames 0,1
    L[2:, 25:32, 5:15] = 3                   # cell 3 touches 1 (below) on frames 2,3
    pairs = {(p["cell_a"], p["cell_b"]): p for p in contacts.contact_pairs(L)}
    assert set(pairs) == {(1, 2), (1, 3)}
    assert pairs[(1, 2)]["last_frame"] == 1 and pairs[(1, 3)]["first_frame"] == 2
    # an all-isolated stack yields no pairs
    iso = np.zeros((3, 40, 40), np.int32)
    iso[:, 2:8, 2:8] = 1
    iso[:, 30:38, 30:38] = 2
    assert contacts.contact_pairs(iso) == []


def test_contact_pairs_table_export():
    L = np.zeros((3, 40, 40), np.int32)
    L[:, 5:25, 5:15] = 1
    L[:, 5:25, 15:25] = 2
    df = exporters.contact_pairs_table(L, um_per_px=0.5, dt_min=1.0)
    assert list(df.columns[:5]) == ["cell_a", "cell_b", "first_frame",
                                    "last_frame", "n_frames_in_contact"]
    assert len(df) == 1 and df.iloc[0]["cell_a"] == 1 and df.iloc[0]["cell_b"] == 2
    # export_all writes the contact_pairs.csv when requested
    import tempfile, pandas as pd
    with tempfile.TemporaryDirectory() as d:
        paths = exporters.export_all(L, 0.5, 1.0, out_dir=d, which=("contact_pairs",))
        assert "contact_pairs" in paths and paths["contact_pairs"].endswith("contact_pairs.csv")


def test_contact_pairs_table_empty_keeps_header():
    """A recording with no touching cells (e.g. a single-cell crop) still produces a
    header-carrying table whose CSV is readable (no headerless 1-byte file)."""
    import tempfile, pandas as pd
    L = np.zeros((3, 30, 30), np.int32)
    L[:, 5:15, 5:15] = 1                     # one cell → zero pairs
    df = exporters.contact_pairs_table(L, um_per_px=0.5, dt_min=1.0)
    assert len(df) == 0
    assert "cell_a" in df.columns and "mean_episode_min" in df.columns
    assert "mean_episode_frames" in exporters.contact_pairs_table(L).columns   # no-dt variant
    with tempfile.TemporaryDirectory() as d:
        p = exporters.export_all(L, 0.5, 1.0, out_dir=d, which=("contact_pairs",))["contact_pairs"]
        back = pd.read_csv(p)                # must round-trip, not EmptyDataError
        assert len(back) == 0 and len(back.columns) == 9


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


def test_cil_speed_free_vs_contact_and_alignment():
    """A cell that moves fast while free then stops on contact reads
    speed_ratio_contact < 1; an isolated cell has only speed_free."""
    from maskviewer.analysis import cil
    L = np.zeros((8, 60, 80), np.int32)
    L[:, 20:35, 50:60] = 2                              # stationary block (cell 2)
    # cell 1 block moves right (big steps) frames 0-4, then stops adjacent to cell 2
    x0 = [5, 13, 21, 30, 38, 38, 38, 38]                # right edge col 49, adjacent to 50
    for t in range(8):
        L[t, 20:35, x0[t]:x0[t] + 12] = 1
    out = cil.contact_locomotion(L, scale=1.0, dt_min=1.0)
    assert out[1]["n_contact_onsets"] >= 1
    assert np.isfinite(out[1]["speed_free"]) and np.isfinite(out[1]["speed_contact"])
    assert out[1]["speed_contact"] < out[1]["speed_free"]    # stopped on contact
    assert out[1]["speed_ratio_contact"] < 1.0
    assert out[1]["delta_speed_onset"] < 0                   # slows as contact forms
    # a lone cell → contact metrics NaN, 0 onsets
    lone = np.zeros((5, 60, 60), np.int32)
    lone[:, 10:20, 10:20] = 1
    o2 = cil.contact_locomotion(lone)
    assert o2[1]["n_contact_onsets"] == 0 and np.isnan(o2[1]["speed_ratio_contact"])


def test_cil_table_and_alignment_range():
    from maskviewer.analysis import cil
    L = np.zeros((6, 60, 60), np.int32)
    L[:, 10:24, 10:24] = 1
    L[:, 10:24, 24:38] = 2                               # two touching cells
    df = cil.contact_locomotion_table(L, um_per_px=0.5, dt_min=1.0)
    assert list(df.columns)[0] == "cell_id" and "velocity_alignment" in df.columns
    al = df["velocity_alignment"].dropna()
    assert ((al >= -1.001) & (al <= 1.001)).all()
