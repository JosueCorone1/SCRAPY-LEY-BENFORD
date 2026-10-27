"""Tkinter smoke test in a hidden window; no Instagram connection."""
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('RUN_GUI_TESTS') != '1', reason='Set RUN_GUI_TESTS=1 with a desktop/Tk runtime')


def test_gui_tables_tooltips_two_datasets_and_three_charts():
    import tkinter as tk
    import gui
    root = tk.Tk()
    root.withdraw()
    try:
        app = gui.ExporterWindow(root)
        app.load_demo()
        root.update_idletasks()
        assert len(app.mode_notebook.tabs()) == 2
        assert len(app.followers_tree.get_children()) == 1000
        assert len(app.following_tree.get_children()) == 1000
        assert 'Seguidores: 100' in app.followers_tooltip.details['user_0']
        assert 'Seguidos: 1,000' in app.followers_tooltip.details['user_0']
        for dataset in gui.DATASETS:
            app.dataset.set(dataset)
            app._analyze_benford()
            assert '1000/1000' in app.benford_summary.get()
            assert 'gl = 8' in app.benford_summary.get()
            assert 'Compatible con Benford' in app.benford_verdict.get()
            assert 'Bot o humano: no determinable' in app.benford_summary.get()
        assert len(app.axes) == 3
        app.canvas.draw()
        assert '75.0/100' in app.summary.get('1.0', 'end')
        app._set_busy(True)
        assert str(app.start_button['state']) == 'disabled'
        app.cancel_event.set()
        app._set_busy(False)
        assert str(app.start_button['state']) == 'normal'
        if os.environ.get('QA_OUTPUT_DIR'):
            output = Path(os.environ['QA_OUTPUT_DIR'])
            output.mkdir(parents=True, exist_ok=True)
            app.figure.savefig(output / 'benford_demo.png', dpi=170)
        app.benford_data['collection']['following']['complete'] = False
        app._analyze_benford()
        assert 'muestra incompleta' in app.benford_verdict.get()
        assert 'se rechaza' not in app.benford_summary.get()
        from tests.test_gemini import answer
        gemini_report = {'personality_analysis': {'provider': 'gemini', 'model': 'synthetic-model',
            'status': 'complete', 'result': answer()}}
        app._show_result(gemini_report, 'synthetic.json')
        assert 'estimación 60/100' in app.summary.get('1.0', 'end')
        assert 'Me gusta aprender' in app.summary.get('1.0', 'end')
        gemini_report['personality_analysis'].update(result=None, status='not_configured', error='Configura GEMINI_API_KEY')
        app._show_result(gemini_report, 'synthetic.json')
        assert 'Configura GEMINI_API_KEY' in app.summary.get('1.0', 'end')
        assert 'incidencias' in app.status.get()
    finally:
        root.destroy()
