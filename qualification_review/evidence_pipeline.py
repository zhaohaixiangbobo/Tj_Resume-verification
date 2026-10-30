"""X项目凭证试运行：填报分流、离线OCR缓存、可选Qwen提取、本地可追溯报告。

默认仅登记和分流；--ocr识别，--llm将脱敏OCR发送到已配置的内网模型。
所有非零分保留业务审核，本版不将模型提取结果直接替换原有试算分。
"""
from __future__ import annotations
import argparse
import hashlib
import html
import importlib.metadata
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from review import load_table, text
from evidence_routing import route_items, file_routes, VERSION

ROOT = Path(__file__).resolve().parent
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def save(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    tmp.replace(path)


def ocr_worker(request_path):
    """独立子进程禁止网络，模型初始化一次；逐页保存，失败页也有记录。"""
    sys.path.insert(0, str(ROOT.parent / 'rapidocr_test'))
    import app as rapid
    sys.addaudithook(rapid.deny_network)
    import numpy as np
    from PIL import Image, ImageOps
    req = json.loads(Path(request_path).read_text(encoding='utf-8'))
    engine = None
    for n, job in enumerate(req['jobs'], 1):
        if req.get('cancel_file') and Path(req['cancel_file']).exists():
            print('OCR已按请求停止，已完成页面缓存保留',flush=True)
            break
        started = time.perf_counter()
        result = {'status':'error', 'lines':[]}
        try:
            if engine is None:
                engine = rapid.make_engine()
            with Image.open(job['image']) as source:
                frame = ImageOps.exif_transpose(source).convert('RGB')
            output = engine(np.asarray(frame)[:, :, ::-1].copy())
            result = {'status':'ok', 'lines':rapid.normalize_result(output),
                      'image_size':list(frame.size), 'coordinate_space':'EXIF校正后的图像像素',
                      'elapsed_seconds':round(time.perf_counter()-started,3)}
            if not result['lines']:
                result['status'] = 'unreadable'
            # 生成带行号的标记图，方便逐条查看模型引用。
            from PIL import ImageDraw
            marked = frame.copy(); draw = ImageDraw.Draw(marked)
            for line in result['lines']:
                points = [tuple(x) for x in line['box']]
                draw.line(points + points[:1], fill='red' if line['score'] < .9 else 'green', width=2)
                draw.text(points[0], str(line['index']), fill='red')
            marked.save(job['marked'])
            result['marked'] = job['marked']
        except Exception as exc:
            result['error'] = f'{type(exc).__name__}: {exc}'
        save(Path(job['result']), result)
        print(f'  [OCR] {n}/{len(req["jobs"])}页 {result["status"]} {time.perf_counter()-started:.1f}秒', flush=True)


def build_pages(folder, items, cache, max_pages, do_ocr, selected_files=None, education_mode=None):
    """清单完整登记；超过页数预算的页面明确延期，文件名只在明确栏目上分流。"""
    pages, files, jobs = [], [], []
    active = {i['code'] for i in items if i['route'] != 'skip'}
    if selected_files is None and not folder.is_dir():
        return [], [], [{'status':'missing', 'reason':'人员材料目录不存在'}]
    model_key = 'inventory'
    if do_ocr:
        model_dir = ROOT.parent / 'rapidocr_test' / 'models'
        names = ['ch_PP-OCRv5_det_server.onnx', 'ch_PP-OCRv5_rec_server.onnx',
                 'ch_ppocr_mobile_v2.0_cls_mobile.onnx', 'ppocrv5_dict.txt']
        model_key = hashlib.sha256(json.dumps([
            [(name, digest(model_dir/name)) for name in names],
            importlib.metadata.version('rapidocr'), importlib.metadata.version('onnxruntime'),
            digest(ROOT.parent/'rapidocr_test/app.py'), digest(Path(__file__)),
            'exif-rgb-bgr-v1-pdf150dpi'], sort_keys=True).encode()).hexdigest()
    used = 0
    paths=sorted(Path(p).resolve() for p in selected_files) if selected_files is not None else sorted(p for p in folder.rglob('*') if p.is_file())
    for seq, path in enumerate(paths, 1):
        sha = digest(path)
        doc_id = f'D{seq:04}'
        codes = file_routes(path.name)
        file = {'doc_id':doc_id, 'path':str(path), 'sha256':sha, 'possible_items':codes}
        files.append(file)
        from education_evidence import is_transcript,is_highest_education
        if education_mode=='overseas' and is_highest_education(path):
            file.update(status='skipped',reason='境外最高学历材料仅检查照片是否存在，待人工核验')
            continue
        if is_transcript(path):
            file.update(status='skipped',reason='成绩材料仅检查照片是否存在，不进行OCR或模型核验')
            continue
        if codes and not active.intersection(codes):
            file.update(status='skipped', reason='对应项目均已按明确填报跳过，节省OCR')
            continue
        suffix = path.suffix.lower()
        if suffix not in IMAGE_SUFFIXES | {'.pdf'}:
            file.update(status='unsupported', reason='此格式需人工打开或转换；已登记未遗漏')
            continue
        pdf = None
        try:
            if suffix == '.pdf':
                import fitz
                pdf = fitz.open(path); count = len(pdf)
                if pdf.needs_pass or count == 0:
                    raise ValueError('加密或空PDF需要人工处理')
            else:
                count = 1
            file.update(status='registered', page_count=count)
            for page_num in range(1, count+1):
                key = hashlib.sha256(f'{sha}|{page_num}|{model_key}'.encode()).hexdigest()
                target = cache / 'ocr' / (key + '.json')
                marked = target.with_suffix('.png')
                page = {'page_id':f'{doc_id}-P{page_num:03}', 'doc_id':doc_id,
                        'source':str(path), 'page':page_num, 'sha256':sha,
                        'possible_items':codes, 'status':'planned', 'lines':[]}
                pages.append(page)
                if not do_ocr:
                    continue
                if target.exists():
                    stored = json.loads(target.read_text(encoding='utf-8'))
                    if stored.get('status') == 'ok':
                        page.update(stored, cache_hit=True)
                        continue
                if used >= max_pages and not (education_mode=='domestic' and is_highest_education(path)):
                    page.update(status='deferred', reason='达到本次OCR页数上限，下次可使用缓存继续')
                    continue
                used += 1
                target.parent.mkdir(parents=True, exist_ok=True)
                image_path = path
                if pdf:
                    image_path = cache/'rendered'/f'{sha}-{page_num}.png'
                    image_path.parent.mkdir(parents=True, exist_ok=True)
                    if not image_path.exists():
                        pdf[page_num-1].get_pixmap(dpi=150, alpha=False).save(image_path)
                job = {'image':str(image_path), 'result':str(target), 'marked':str(marked)}
                jobs.append(job)
                page['_result'] = str(target)
        except Exception as exc:
            file.update(status='error', reason=f'{type(exc).__name__}: {exc}')
        finally:
            if pdf is not None:
                pdf.close()
    return pages, jobs, files


def render_report(path, run):
    esc = lambda x: html.escape(str(x))
    blocks = ['<!doctype html><meta charset="utf-8"><title>凭证核验试运行</title>',
              '<style>body{font:16px sans-serif;margin:28px;line-height:1.6}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:8px;text-align:left}pre{white-space:pre-wrap}details{margin:12px 0}</style>',
              '<h1>X项目凭证核验试运行</h1><p>填报分流、原始凭证和模型提取分开保留。非零分仍须业务确认；此报告不代表资格通过或最终分数。</p>']
    for person in run['persons']:
        blocks.append(f'<h2>{esc(person["name"])} · {esc(person["candidate_id"])}</h2><table><tr><th>项目</th><th>分流</th><th>分数</th><th>依据</th></tr>')
        for item in person['items']:
            blocks.append('<tr>'+''.join(f'<td>{esc(v)}</td>' for v in [item['code']+' '+item['name'],
                {'skip':'跳过凭证','verify':'查验凭证','manual':'人工复核'}[item['route']],
                item['score'] if item['score'] is not None else '待核验',item['reason']])+'</tr>')
        blocks.append('</table><h3>原始材料清单</h3>')
        for file in person['files']:
            blocks.append(f'<p><a href="{esc(Path(file["path"]).as_uri())}">{esc(Path(file["path"]).name)}</a>：{esc(file["status"])} {esc(file.get("reason",""))}</p>' if 'path' in file else f'<p>{esc(file)}</p>')
        for page in person['pages']:
            blocks.append(f'<details><summary>{esc(page["page_id"])} · {esc(page["status"])} · {len(page["lines"])}行</summary>')
            if page.get('marked'):
                blocks.append(f'<a href="{esc(Path(page["marked"]).as_uri())}">打开OCR文字框与行号标记图</a>')
            blocks.append('<pre>'+esc('\n'.join(f'{x["index"]}: {x["text"]}' for x in page['lines']))+'</pre></details>')
        blocks.append('<h3>模型事实与处理记录（供业务核对）</h3><pre>'+esc(json.dumps(person['model'],ensure_ascii=False,indent=2))+'</pre>')
    Path(path).write_text('\n'.join(blocks),encoding='utf-8')


def run(args):
    started = time.perf_counter()
    config = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
    source = (args.input or ROOT.parent/config['personnel_file']).resolve()
    sheet, records, columns = load_table(source, config['personnel_sheet'])
    materials = (args.materials or source.parent).resolve()
    if args.candidate:
        records = [(r,p) for r,p in records if text(p.get('身份证号码')).upper() == args.candidate.upper()]
        if len(records) != 1:
            raise ValueError('指定证件号需在人员表中唯一匹配')
    records = records[:args.limit] if args.limit else records
    identities = [text(p.get('身份证号码')).upper() for _,p in records]
    if any(not i or '/' in i or '\\' in i or i in {'.','..'} for i in identities) or len(set(identities)) != len(identities):
        raise ValueError('人员证件号缺失、重复或不能安全绑定文件夹')
    out = (args.output or ROOT/'outputs'/('evidence_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))).resolve()
    out.mkdir(parents=True, exist_ok=False)
    cache = ROOT/'cache/evidence'
    model_cfg = json.loads((ROOT/'evidence_config.json').read_text(encoding='utf-8'))
    report = {'version':VERSION, 'created_at':datetime.now().isoformat(), 'cutoff':config['cutoff'],
              'source_sha256':digest(source), 'source':str(source.resolve()),
              'scope':'凭证分流与事实提取试运行，非零分均待业务确认', 'persons':[]}
    for n, (row, person) in enumerate(records, 1):
        ident = text(person['身份证号码']).upper()
        cid = hashlib.sha256(ident.encode()).hexdigest()[:16]
        print(f'[{n}/{len(records)}] 人员{cid} 分流与材料登记，已耗时{time.perf_counter()-started:.1f}秒',flush=True)
        items = route_items(person)
        for item in items:
            item['source_cells'] = [f'{sheet}!{columns[k]}{row}' for k in item['sources'] if k in columns]
        folder = materials/ident
        pages, jobs, files = build_pages(folder, items, cache, args.max_pages, args.ocr)
        if jobs:
            request_path = out/f'{cid}_ocr_jobs.json'
            save(request_path, {'jobs':jobs})
            proc = subprocess.run([sys.executable, str(Path(__file__)), '--worker', str(request_path)])
            for page in pages:
                if '_result' in page:
                    target = Path(page.pop('_result'))
                    if target.exists():
                        page.update(json.loads(target.read_text(encoding='utf-8')),cache_hit=False)
                    else:
                        page.update(status='error', reason=f'OCR子进程退出码{proc.returncode}，该页未完成')
        result = {'enabled':False, 'pages':[], 'events':[]}
        from fixed_certificates import route_pages
        fixed=route_pages(pages,text(person['姓名']),config['cutoff'],person)
        ready=fixed.pop('model_pages')
        print(f'  [本地规则] {fixed["local_count"]}页免模型，{fixed["manual_count"]}页直接复核，{len(ready)}页保留原流程',flush=True)
        if args.llm:
            from evidence_model import extract
            active = [i['code'] for i in items if i['route'] != 'skip' and i['code'] != 'S13']
            result = extract(cid, ready, active, model_cfg, cache/'model') if ready and active else result
            result['enabled'] = True
        result['fixed']=fixed
        # 记录模型提取页与评分项目的关联；仅事实提取完成不代表凭证充分。
        for item in items:
            item['evidence'] = [p['page_id'] for p in result['pages'] if item['code'] in p['item_codes']]
        report['persons'].append({'candidate_id':cid,'name':text(person['姓名']), 'source_row':row,
                                  'items':items,'files':files,'pages':pages,'model':result})
        report['elapsed_seconds'] = round(time.perf_counter()-started,3)
        save(out/'凭证核验结果.json',report)
        render_report(out/'凭证核验报告.html',report)
    print(f'完成：{out}；{len(records)}人，{time.perf_counter()-started:.1f}秒',flush=True)
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--input', type=Path)
    p.add_argument('--materials', type=Path, help='包含证件号子目录的材料根目录')
    p.add_argument('--candidate', help='精确匹配指定人员证件号，仅用于本地绑定')
    p.add_argument('--limit', type=int, default=0, help='限制人员数，0表示全部')
    p.add_argument('--max-pages', type=int, default=8, help='每人本次新增OCR页数上限，已有缓存不占额度')
    p.add_argument('--ocr', action='store_true')
    p.add_argument('--llm', action='store_true', help='调用已配置内网模型，需同时--ocr')
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    if args.worker:
        ocr_worker(args.worker)
    else:
        if args.limit < 0 or args.max_pages < 1 or (args.llm and not args.ocr):
            p.error('limit需非负、max-pages需正数；--llm需同时--ocr')
        run(args)
