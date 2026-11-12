"""Web interface for cellscope_analysis (FastAPI app + static front end).

- app.py        FastAPI routes under /api, the /demo files, STATIC_ENDPOINTS for the static export
- api_data.py   demo listing, Python reference tables, comparison and metric docs (calls maskviewer.analysis)
- demo_data.py  the SYNTHETIC demo results set (simulated cells, CellScope layout via io.writer)
- static/       the ES-module front end, incl. the JS readers (npz.js, tiff.js) and analysis ports (*_engine.js)
"""
