"""简化桌面入口测试：默认选项、筛选多选、完整页数与精简导出。"""
import json
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desktop_app
from desktop_export import export_batch


class SimpleDesktopTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        rows = [(2, {'身份证号码': 'A', '姓名': '甲', '岗位编码': '001',
                     '政治面貌': '中共预备党员', '最高学历': '硕士研究生'}),
                (3, {'身份证号码': 'B', '姓名': '乙', '岗位编码': '002'})]
        with patch.object(desktop_app, 'load_table', return_value=([], rows, {})):
            self.app = desktop_app.ReviewApp(self.root)
        self.root.update()

    def tearDown(self):
        for callback in self.root.tk.call('after', 'info'):
            self.root.after_cancel(callback)
        self.root.destroy()

    def test_defaults_and_search_selection(self):
        app = self.app
        self.assertTrue(app.ocr.get())
        self.assertFalse(app.llm.get())
        self.assertEqual(tuple(app.people['columns']), ('name', 'ident', 'political', 'degree', 'job'))
        self.assertEqual(app.people.item('A', 'values')[2:4], ('中共预备党员', '硕士研究生'))
        for query in ('预备党员', '硕士'):
            app.search.set(query)
            self.root.update()
            self.assertEqual(app.people.get_children(), ('A',))
        app.search.set('')
        self.root.update()
        app.select_all()
        app.search.set('甲')
        self.root.update()
        self.assertEqual(app.selected, {'A', 'B'})
        self.assertEqual(app.people.get_children(), ('A',))
        app.clear_selection()
        self.root.update()
        self.assertEqual(app.selected, set())
        app.select_all()
        self.assertEqual(app.selected, {'A'})

    def test_log_visible_append_and_toggle(self):
        app = self.app
        self.assertTrue(app.show_log.get())
        self.assertEqual(app.log_panel.winfo_manager(), 'pack')
        app.append_log('[OCR] 测试进度\n')
        self.assertIn('[OCR] 测试进度', app.log.get('1.0', 'end'))
        self.assertEqual(str(app.log['state']), 'disabled')
        app.show_log.set(False)
        app.toggle_log()
        self.assertEqual(app.log_panel.winfo_manager(), '')
        app.show_log.set(True)
        app.toggle_log()
        self.assertEqual(app.log_panel.winfo_manager(), 'pack')

    def test_options_and_running_controls(self):
        app = self.app
        base = desktop_app.ROOT / 'tests' / '_runs'
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            material = Path(folder) / 'A'
            material.mkdir()
            for n in range(12):
                (material / f'{n}.jpg').write_bytes(b'fixture')
            app.materials.set(folder)
            app.selected = {'A'}
            options, pages, unknown = app.build_options()
            self.assertEqual(pages, 12)
            self.assertEqual(options['max_pages'], 12)
            self.assertFalse(options['export_review'])
            self.assertFalse(options['llm'])
        app.set_running(True)
        self.assertTrue(app.start.instate(['disabled']))
        app.set_running(False)
        self.assertFalse(app.start.instate(['disabled']))

    def test_export_has_no_review_workbook(self):
        base = desktop_app.ROOT / 'tests' / '_runs'
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            export_batch({'persons': [], 'decisions': {}, 'options': {'export_review': False}}, folder)
            self.assertFalse(list(Path(folder).rglob('*.xlsx')))


if __name__ == '__main__':
    unittest.main()
