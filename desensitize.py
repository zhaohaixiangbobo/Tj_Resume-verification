"""资格审查材料脱敏：另存副本，替换表格中的姓名与身份证号，并同步重命名身份证号文件夹。

原始目录和原始表格保持不变；图片内容不做像素级处理。
映射表单独保存在工作区根目录，含真实信息，不能随脱敏材料外发。
"""
from pathlib import Path
import csv
import random
import re
import shutil
import sys

import openpyxl

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / '2026-10-21-2026-10-21资格审查信息 （21日1006导出）'
TARGET = SOURCE.with_name(SOURCE.name + '-脱敏')
ID_PATTERN = re.compile(r'(?<![0-9A-Za-z])[0-9]{17}[0-9Xx](?![0-9A-Za-z])')
NAME_COLUMNS = ('姓名', '紧急联系人姓名')
MEMBER_COLUMN = '家庭主要成员'
WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
CHECK_CODES = '10X98765432'
SURNAMES = '王李张刘陈杨赵黄周吴徐孙马朱胡郭何林高罗郑梁谢宋唐许韩冯邓曹彭曾肖田董潘袁蔡蒋余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤'
GIVEN = ('伟', '芳', '娜', '敏', '静', '磊', '军', '洋', '勇', '艳', '杰', '涛', '明', '超',
         '秀兰', '霞', '平', '刚', '桂英', '文轩', '雨桐', '子涵', '欣怡', '浩然', '梓萱',
         '一诺', '思远', '嘉懿', '晨曦', '若彤', '志强', '建华', '晓东', '文博', '雅静')
rng = random.Random(20261026)


def check_digit(body):
    """按 GB 11643 计算身份证第 18 位校验码。"""
    return CHECK_CODES[sum(int(n) * w for n, w in zip(body, WEIGHTS)) % 11]


def fake_id(real, used):
    """保留前 6 位地区码和出生日期，随机顺序码并重算校验位，保证 18 位格式一致。"""
    while True:
        body = real[:14] + f'{rng.randrange(1000):03d}'
        candidate = body + check_digit(body)
        if candidate != real and candidate not in used:
            used.add(candidate)
            return candidate


def fake_name(used):
    while True:
        candidate = rng.choice(SURNAMES) + rng.choice(GIVEN)
        if candidate not in used:
            used.add(candidate)
            return candidate


def cell_text(value):
    return value if isinstance(value, str) else ''


def main():
    if not SOURCE.is_dir():
        sys.exit(f'未找到原始目录：{SOURCE}')
    if TARGET.exists():
        sys.exit(f'脱敏目录已存在，请先确认后删除或改名：{TARGET}')
    book_path = next(SOURCE.glob('*.xlsx'))
    wb = openpyxl.load_workbook(book_path)

    real_ids = {p.name for p in SOURCE.iterdir() if p.is_dir() and ID_PATTERN.fullmatch(p.name)}
    real_names = set()
    member_names = set()
    for ws in wb.worksheets:
        headers = {cell.value: cell.column for cell in ws[1] if cell.value}
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                real_ids.update(ID_PATTERN.findall(cell_text(cell.value)))
        for title in NAME_COLUMNS:
            if title in headers:
                for row in ws.iter_rows(min_row=2, min_col=headers[title], max_col=headers[title]):
                    name = cell_text(row[0].value).strip()
                    if name:
                        real_names.add(name)
        if MEMBER_COLUMN in headers:
            for row in ws.iter_rows(min_row=2, min_col=headers[MEMBER_COLUMN], max_col=headers[MEMBER_COLUMN]):
                for line in cell_text(row[0].value).splitlines():
                    # 家庭成员行格式：姓名 关系 身份证号 出生年月 ……
                    if ID_PATTERN.search(line):
                        name = line.split()[0].strip() if line.split() else ''
                        if re.fullmatch(r'[一-龥·]{2,6}', name):
                            member_names.add(name)
    real_names |= member_names

    used_ids = set(real_ids)
    id_map = {real: fake_id(real, used_ids) for real in sorted(real_ids)}
    used_names = set(real_names)
    name_map = {real: fake_name(used_names) for real in sorted(real_names, key=len, reverse=True)}

    def scrub(text):
        text = ID_PATTERN.sub(lambda m: id_map.get(m.group(0), m.group(0)), text)
        for real, fake in name_map.items():
            text = text.replace(real, fake)
        return text

    changed = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    new_value = scrub(cell.value)
                    if new_value != cell.value:
                        cell.value = new_value
                        changed += 1

    print(f'身份证号 {len(id_map)} 个，姓名 {len(name_map)} 个，修改单元格 {changed} 个')
    shutil.copytree(SOURCE, TARGET)
    renamed = 0
    for folder in sorted(TARGET.iterdir()):
        if folder.is_dir() and folder.name in id_map:
            folder.rename(folder.with_name(id_map[folder.name]))
            renamed += 1
    wb.save(TARGET / book_path.name)
    wb.close()
    print(f'已复制材料并重命名 {renamed} 个文件夹：{TARGET}')

    mapping_path = ROOT / '脱敏映射表（含真实信息请勿外发）.csv'
    with mapping_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['类型', '原始值', '脱敏值'])
        writer.writerows(('身份证号', k, v) for k, v in id_map.items())
        writer.writerows(('姓名', k, v) for k, v in name_map.items())
    print(f'映射表：{mapping_path}')

    # 复核：脱敏表格中不得再出现任何原始身份证号或姓名，文件夹名必须一一对应。
    check = openpyxl.load_workbook(TARGET / book_path.name, read_only=True)
    leftovers = []
    for ws in check.worksheets:
        for row in ws.iter_rows(values_only=True):
            for value in row:
                text = cell_text(value)
                leftovers += [i for i in real_ids if i in text]
                leftovers += [n for n in real_names if n in text]
    check.close()
    folder_ids = {p.name for p in TARGET.iterdir() if p.is_dir()}
    assert not leftovers, f'仍有未脱敏内容：{leftovers[:5]}'
    assert folder_ids == {id_map[i] for i in folder_ids & set(real_ids)} | (folder_ids - set(real_ids))
    assert not (folder_ids & set(real_ids)), '仍存在原始身份证号文件夹'
    assert len(folder_ids) == len([p for p in SOURCE.iterdir() if p.is_dir()])
    print('复核通过：表格与文件夹中均无原始身份证号、姓名，文件夹数量一致。')


if __name__ == '__main__':
    main()
