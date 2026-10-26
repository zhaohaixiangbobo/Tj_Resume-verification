"""验证图片收集、结果一致性、导出及离线保护，不加载 OCR 模型。"""
import json
from pathlib import Path
import sys
from contextlib import contextmanager
import shutil
import uuid
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


@contextmanager
def test_folder():
    # 使用继承工作区权限的目录，兼容 Windows 受限运行账户。
    root = Path(__file__).resolve().parent
    folder = root / ('case_' + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        if folder.resolve().parent == root:
            shutil.rmtree(folder)


class CoreTests(unittest.TestCase):
    def test_collect_chinese_and_uppercase(self):
        with test_folder() as folder:
            root = Path(folder)
            (root / '学历').mkdir()
            image = root / '学历' / '材料.JPG'
            image.touch()
            (root / '说明.txt').touch()
            self.assertEqual(app.collect_images(root), [image])
            self.assertEqual(app.collect_images(image), [image])

    def test_empty_result(self):
        self.assertEqual(app.normalize_result(SimpleNamespace(txts=None)), [])

    def test_inconsistent_result(self):
        with self.assertRaises(ValueError):
            app.normalize_result(SimpleNamespace(txts=['学历'], boxes=[], scores=[.9]))

    def test_export_and_preserve_source(self):
        from PIL import Image
        result = SimpleNamespace(txts=['本科', '=1+1'], scores=[.98, .7],
                                 boxes=[[[0, 0], [50, 0], [50, 20], [0, 20]]] * 2)
        lines = app.normalize_result(result)
        with test_folder() as folder:
            root = Path(folder)
            source = root / '证书.jpg'
            image = Image.new('RGB', (80, 40), 'white')
            image.save(source)
            original = source.read_bytes()
            target = app.save_result(root, source, image, lines, .1, 0)
            saved = json.loads((target / 'result.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['lines'][0]['text'], '本科')
            self.assertIn("'=1+1", (target / 'lines.csv').read_text(encoding='utf-8-sig'))
            self.assertTrue((target / 'marked.png').exists())
            self.assertEqual(original, source.read_bytes())

    def test_network_guard(self):
        with self.assertRaises(RuntimeError):
            app.deny_network('socket.connect', ())
        app.deny_network('open', ())


if __name__ == '__main__':
    unittest.main()
