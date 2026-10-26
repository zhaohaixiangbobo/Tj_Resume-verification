"""本地 RapidOCR 图片测试工具：离线模型校验、批量识别、原图对照和结果导出。"""
from pathlib import Path
import csv
import hashlib
import importlib.metadata
import json
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime

BASE = Path(__file__).resolve().parent
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
MODELS = {
    'Det.model_path': 'ch_PP-OCRv5_det_server.onnx',
    'Cls.model_path': 'ch_ppocr_mobile_v2.0_cls_mobile.onnx',
    'Rec.model_path': 'ch_PP-OCRv5_rec_server.onnx',
    'Rec.rec_keys_path': 'ppocrv5_dict.txt',
}
# RapidOCR 每次调用都会实例化结果可视化组件，未指定字体时它会把 FZYTK.TTF
# 下载到 rapidocr/models 下。本工具自带绘图，不需要该字体，因此指定系统字体避免联网。
FONTS = ('simfang.ttf', 'simsun.ttc', 'msyh.ttc')


def deny_network(event, args):
    """进程级网络保护，确保第三方库也无法自行连接下载服务。"""
    if event in {'socket.connect', 'socket.getaddrinfo'}:
        raise RuntimeError('测试版仅允许本地运行，请按说明手动下载完整模型。')


def collect_images(path):
    path = Path(path).expanduser().resolve()
    if path.is_file() and path.suffix.lower() in EXTENSIONS:
        return [path]
    if path.is_dir():
        # 输出目录独立存放，重复测试时排除历史标注图片。
        output = (BASE / 'outputs').resolve()
        return sorted(p for p in path.rglob('*') if p.is_file()
                      and p.suffix.lower() in EXTENSIONS and not p.is_relative_to(output))
    return []


def model_paths():
    paths = {key: str(BASE / 'models' / name) for key, name in MODELS.items()}
    missing = [str(p) for p in paths.values() if not Path(
        p).is_file() or Path(p).stat().st_size == 0]
    if missing:
        raise FileNotFoundError('请先手动下载以下模型文件：\n' + '\n'.join(missing))
    return paths


def font_path():
    """返回一个本机已有的中文字体，阻止 RapidOCR 自行下载字体文件。"""
    for name in FONTS:
        path = Path(r'C:\Windows\Fonts') / name
        if path.is_file():
            return str(path)
    raise FileNotFoundError(
        '未找到可用的系统中文字体，请在本机字体目录确认 simfang.ttf 或 msyh.ttc 存在。')


def make_engine():
    paths = model_paths()
    try:
        version = importlib.metadata.version('rapidocr')
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError('请按 README 安装 rapidocr==3.4.1。') from exc
    if version != '3.4.1':
        raise RuntimeError(f'当前 rapidocr={version}，本测试版要求 3.4.1，以保持接口和模型一致。')
    from rapidocr import RapidOCR, OCRVersion, ModelType, EngineType
    params = dict(paths)
    for stage in ('Det', 'Rec'):
        params[f'{stage}.ocr_version'] = OCRVersion.PPOCRV5
        params[f'{stage}.model_type'] = ModelType.SERVER
    for stage in ('Det', 'Cls', 'Rec'):
        params[f'{stage}.engine_type'] = EngineType.ONNXRUNTIME
    params['Cls.ocr_version'] = OCRVersion.PPOCRV4
    params['Global.font_path'] = font_path()
    # 保留低分识别行供人工对照；界面 0.90 是提示阈值，不是准确率。
    params['Global.text_score'] = 0.0
    return RapidOCR(params=params)


def normalize_result(result):
    texts = result.txts
    if texts is None:
        return []
    boxes, scores = result.boxes, result.scores
    if boxes is None or scores is None or not (len(texts) == len(boxes) == len(scores)):
        raise ValueError('OCR 返回的文字、分数和坐标数量不一致。')
    return [{'index': i + 1, 'text': str(text), 'score': float(score),
             'box': [[float(x), float(y)] for x, y in box]}
            for i, (text, score, box) in enumerate(zip(texts, scores, boxes))]


def save_result(folder, source, image, lines, elapsed, rotation):
    from PIL import ImageDraw
    key = source.stem + '_' + \
        hashlib.sha256(str(source).encode('utf-8')).hexdigest()[:10]
    target = folder / key
    target.mkdir()
    marked = image.copy()
    draw = ImageDraw.Draw(marked)
    for row in lines:
        points = [tuple(p) for p in row['box']]
        color = '#e53935' if row['score'] < 0.90 else '#00875a'
        draw.line(points + points[:1], fill=color, width=2)
        draw.text(points[0], str(row['index']), fill=color, stroke_width=1)
    marked.save(target / 'marked.png')
    data = {'source': str(source), 'elapsed_seconds': elapsed, 'rotation_ccw': rotation,
            'coordinate_space': 'EXIF校正后再按所选角度旋转的图片',
            'image_size': list(image.size), 'lines': lines}
    (target / 'result.json').write_text(json.dumps(data,
                                                   ensure_ascii=False, indent=2), encoding='utf-8')
    (target / 'text.txt').write_text('\n'.join(row['text']
                                               for row in lines), encoding='utf-8')
    with (target / 'lines.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['序号', '识别文字', '模型分数', '文字框坐标'])
        for row in lines:
            # CSV 打开时按普通文字显示，避免 OCR 文本被 Excel 当成公式。
            value = row['text']
            if value.lstrip().startswith(('=', '+', '-', '@')):
                value = "'" + value
            writer.writerow(
                [row['index'], value, row['score'], json.dumps(row['box'])])
    return target


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('RapidOCR 本地识别测试 · PP-OCRv5 server')
        self.geometry('1280x850')
        self.events = queue.Queue()
        self.results = []
        self.stop_event = threading.Event()
        self.running = False
        self.output = None
        self.path = tk.StringVar()
        self.status = tk.StringVar(value='先选择图片或人员文件夹；安装和模型下载请查看 README。')
        self.rotation = tk.StringVar(value='0')
        self.marked = tk.BooleanVar(value=True)
        self.zoom = tk.StringVar(value='适应窗口')
        top = ttk.Frame(self, padding=8)
        top.pack(fill='x')
        ttk.Entry(top, textvariable=self.path).pack(
            side='left', fill='x', expand=True)
        ttk.Button(top, text='选择图片', command=self.pick_file).pack(side='left')
        ttk.Button(top, text='选择文件夹',
                   command=self.pick_folder).pack(side='left')
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill='x')
        ttk.Label(bar, text='整图逆时针旋转：').pack(side='left')
        ttk.Combobox(bar, textvariable=self.rotation, values=[
                     '0', '90', '180', '270'], width=5, state='readonly').pack(side='left')
        self.start_button = ttk.Button(bar, text='开始识别', command=self.start)
        self.start_button.pack(side='left', padx=10)
        ttk.Button(bar, text='当前图片完成后停止',
                   command=self.stop_event.set).pack(side='left')
        ttk.Button(bar, text='打开结果文件夹', command=self.open_output).pack(
            side='left', padx=10)
        ttk.Checkbutton(bar, text='显示文字框及编号', variable=self.marked,
                        command=self.show).pack(side='left')
        zoom = ttk.Combobox(bar, textvariable=self.zoom, values=[
                            '适应窗口', '100%', '150%', '200%'], width=10, state='readonly')
        zoom.pack(side='left')
        zoom.bind('<<ComboboxSelected>>', self.show)
        panes = ttk.Panedwindow(self, orient='horizontal')
        panes.pack(fill='both', expand=True)
        self.files = tk.Listbox(panes, width=28, exportselection=False)
        panes.add(self.files, weight=1)
        self.files.bind('<<ListboxSelect>>', self.show)
        preview = ttk.Frame(panes)
        panes.add(preview, weight=4)
        self.canvas = tk.Canvas(preview, background='#e8ebef')
        xs = ttk.Scrollbar(preview, orient='horizontal',
                           command=self.canvas.xview)
        ys = ttk.Scrollbar(preview, orient='vertical',
                           command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        ys.pack(side='right', fill='y')
        xs.pack(side='bottom', fill='x')
        self.canvas.pack(fill='both', expand=True)
        text_frame = ttk.Frame(panes)
        panes.add(text_frame, weight=3)
        self.text = tk.Text(text_frame, width=45, wrap='word',
                            font=('Microsoft YaHei', 11))
        scroll = ttk.Scrollbar(text_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.text.pack(fill='both', expand=True)
        self.text.tag_configure('low', foreground='#c62828')
        ttk.Label(self, textvariable=self.status,
                  padding=8, wraplength=1200).pack(fill='x')
        self.progress = ttk.Progressbar(self)
        self.progress.pack(fill='x')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

    def pick_file(self):
        value = filedialog.askopenfilename(
            filetypes=[('图片', '*.jpg *.jpeg *.JPG *.png *.bmp *.webp')])
        if value:
            self.path.set(value)

    def pick_folder(self):
        value = filedialog.askdirectory()
        if value:
            self.path.set(value)

    def start(self):
        if self.running:
            return
        if not self.path.get().strip():
            messagebox.showinfo('选择材料', '请选择一张图片或一个人员文件夹。')
            return
        files = collect_images(self.path.get())
        if not files:
            messagebox.showinfo('没有图片', '支持 JPG、PNG、BMP、WEBP；文件夹会递归扫描。')
            return
        self.running = True
        self.start_button.configure(state='disabled')
        self.stop_event.clear()
        self.results.clear()
        self.files.delete(0, 'end')
        self.progress.configure(maximum=len(files), value=0)
        rotation = int(self.rotation.get())
        self.status.set('正在检查本地模型并初始化……')
        threading.Thread(target=self.work, args=(
            files, rotation), daemon=True).start()

    def work(self, files, rotation):
        records = []
        try:
            from PIL import Image, ImageOps
            import numpy as np
            engine = make_engine()
            folder = BASE / 'outputs' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            folder.mkdir(parents=True)
            self.events.put(('output', folder))
            start = time.perf_counter()
            for index, source in enumerate(files):
                if self.stop_event.is_set():
                    break
                self.events.put(
                    ('status', f'正在识别 {index + 1}/{len(files)}：{source.name}'))
                began = time.perf_counter()
                try:
                    with Image.open(source) as original:
                        img = ImageOps.exif_transpose(original).convert(
                            'RGB').rotate(rotation, expand=True)
                    # RapidOCR 的 ndarray 输入为 BGR，与预览图保持同一坐标系。
                    # __call__ 的 text_score 默认 0.5 会覆盖配置，这里显式传 0 保留低分行。
                    result = engine(np.asarray(
                        img)[:, :, ::-1].copy(), text_score=0.0)
                    lines = normalize_result(result)
                    elapsed = time.perf_counter() - began
                    target = save_result(
                        folder, source, img, lines, elapsed, rotation)
                    record = {'source': str(source), 'status': 'success' if lines else 'empty',
                              'line_count': len(lines), 'seconds': elapsed, 'output': str(target)}
                    self.events.put(
                        ('result', (source, target, lines, rotation)))
                except Exception as exc:
                    record = {'source': str(
                        source), 'status': 'error', 'error': str(exc)}
                records.append(record)
                (folder / 'summary.json').write_text(json.dumps(records,
                                                                ensure_ascii=False, indent=2), encoding='utf-8')
                self.events.put(
                    ('progress', (index + 1, f'已处理 {index + 1}/{len(files)}（{(index + 1)/len(files):.0%}），耗时 {time.perf_counter()-start:.1f} 秒')))
            errors = sum(r['status'] == 'error' for r in records)
            empty = sum(r['status'] == 'empty' for r in records)
            self.events.put(
                ('status', f'本次已处理 {len(records)}/{len(files)} 张，失败 {errors} 张，无文字 {empty} 张。结果：{folder}'))
        except Exception as exc:
            self.events.put(('error', str(exc)))
        finally:
            self.events.put(('done', None))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status':
                    self.status.set(value)
                elif kind == 'output':
                    self.output = value
                elif kind == 'progress':
                    self.progress['value'] = value[0]
                    self.status.set(value[1])
                elif kind == 'error':
                    self.status.set(value)
                    messagebox.showerror('识别未启动或已中断', value)
                elif kind == 'done':
                    self.running = False
                    self.start_button.configure(state='normal')
                elif kind == 'result':
                    self.results.append(value)
                    self.files.insert('end', value[0].name)
                    if len(self.results) == 1:
                        self.files.selection_set(0)
                        self.show()
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def show(self, event=None):
        selected = self.files.curselection()
        if not selected:
            return
        from PIL import Image, ImageOps, ImageTk
        source, target, lines, rotation = self.results[selected[0]]
        try:
            with Image.open(target / 'marked.png' if self.marked.get() else source) as opened:
                img = opened.convert('RGB') if self.marked.get() else ImageOps.exif_transpose(
                    opened).convert('RGB').rotate(rotation, expand=True)
            if self.zoom.get() == '适应窗口':
                img.thumbnail((max(200, self.canvas.winfo_width()-20),
                              max(200, self.canvas.winfo_height()-20)))
            else:
                scale = int(self.zoom.get().rstrip('%')) / 100
                img = img.resize((int(img.width*scale), int(img.height*scale)))
            self.photo = ImageTk.PhotoImage(img)
            self.canvas.delete('all')
            self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
            self.canvas.configure(scrollregion=(0, 0, img.width, img.height))
            self.text.delete('1.0', 'end')
            self.text.insert(
                'end', f'{source.name}\n共 {len(lines)} 行；红色表示模型分数低于 0.90，分数不等于准确率。\n\n')
            for row in lines:
                self.text.insert(
                    'end', f"[{row['index']}] {row['score']:.3f}  {row['text']}\n\n", 'low' if row['score'] < 0.9 else '')
        except Exception as exc:
            messagebox.showerror('预览失败', str(exc))

    def open_output(self):
        if self.output:
            import os
            os.startfile(self.output)

    def close(self):
        if self.running:
            self.stop_event.set()
            messagebox.showinfo('正在停止', '当前图片完成后停止，请稍后再关闭窗口。')
        else:
            self.destroy()


if __name__ == '__main__':
    sys.addaudithook(deny_network)
    App().mainloop()
