"""从缓存的教育部官方名单生成院校字典；保存来源和互斥计分层次。"""
from pathlib import Path
import csv
import re
from collections import Counter
import xlrd
from lxml import html

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'data' / 'raw'
MOE = 'https://www.moe.gov.cn/'
SOURCE_985 = MOE + 'srcsite/A22/s7065/200612/t20061206_128833.html'
SOURCE_211 = MOE + 'srcsite/A22/s7065/200512/t20051223_82762.html'
SOURCE_DOUBLE = MOE + 'srcsite/A22/s7065/202202/t20220211_598710.html'
SOURCE_ALL = MOE + 'jyb_xxgk/s5743/s5744/202606/t20260618_1441074.html'
ALIASES = {'国防科学技术大学': '国防科技大学', '第二军医大学': '海军军医大学',
           '第四军医大学': '空军军医大学', '上海体育学院': '上海体育大学'}

def official_names(index):
    tree = html.fromstring((RAW / f'source_{index}.html').read_text(encoding='utf-8'))
    return {re.sub(r'\s+', '', td.text_content()) for td in tree.xpath('//table')[-1].xpath('.//td')}

def build():
    original_211, original_985 = official_names(0), official_names(1)
    assert len(original_211) == 112 and len(original_985) == 39, '官方名单结构变化，请复核'
    n211 = {ALIASES.get(x, x) for x in original_211}
    # 教育部官方答复说明地矿油两地办学的211建设按一校对待；分别对应现行学校标识码。
    n211 -= {'中国地质大学', '中国石油大学'}
    n211 |= {'中国地质大学（北京）', '中国地质大学（武汉）', '中国石油大学（北京）',
             '中国石油大学（华东）', '中国矿业大学（北京）'}
    n985 = {ALIASES.get(x, x) for x in original_985}
    nd = {ALIASES.get(x.strip(), x.strip()) for x in re.findall(
        r'^([^\n：]+)：', (RAW / '双一流_2022.txt').read_text(encoding='utf-8'), re.M)}
    assert len(nd) == 147
    book = xlrd.open_workbook(str(RAW / '教育部_普通高校_2026.xls'))
    sheet = book.sheet_by_index(0)
    rows = []
    for i in range(sheet.nrows):
        if sheet.cell_type(i, 0) != xlrd.XL_CELL_NUMBER:
            continue
        _, name, code, authority, city, degree, remark = sheet.row_values(i)
        nature = '民办' if remark == '民办' else ('公办' if not remark else '特殊办学性质待核验')
        # 专科保留在基础名录中，但不纳入本科及以上计分范围。
        tier = ('985' if name in n985 else '211' if name in n211 else
                '其他双一流' if name in nd else '其他公办高校' if nature == '公办' else
                '民办及独立学院' if nature == '民办' else '待核验')
        rows.append([name, str(int(code)), authority, city, degree, nature, tier,
                     int(name in n985), int(name in n211), int(name in nd), remark,
                     SOURCE_ALL, f'{sheet.name}!B{i+1}:G{i+1}', '2026-06-17',
                     SOURCE_985 if name in n985 else SOURCE_211 if name in n211 else SOURCE_DOUBLE if name in nd else SOURCE_ALL])
    assert len(rows) == 2952
    # 历史学校仍保留名录记录，防止旧学历名称无法匹配；不应按北京师范大学本部层次识别。
    for row in rows:
        if row[0] == '北京师范大学珠海分校':
            row[10] = '民办；2021年停止招生、2024年终止办学，历史名录保留'
    present = {r[0] for r in rows}
    for name in sorted(nd - present):
        assert name in {'国防科技大学', '海军军医大学', '空军军医大学'}, name
        rows.append([name, '', '军队院校', '', '本科', '军队院校',
                     '985' if name in n985 else '211', int(name in n985), int(name in n211), 1,
                     '教育部普通高校名单范围外补充；依据双一流名单', SOURCE_DOUBLE, '附件1',
                     '2022-02-09', SOURCE_985 if name in n985 else SOURCE_211])
    headers = ['学校名称', '学校标识码', '主管部门', '所在地', '办学层次', '办学性质', '计分层次',
               '985标记', '211标记', '双一流标记', '备注', '名录来源', '来源位置', '名录日期', '层次来源']
    with (ROOT / 'data' / 'domestic_schools.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f); w.writerow(headers); w.writerows(rows)
    print(f'普通高校2952所，军队补充3所。本科院校层次：{Counter(r[6] for r in rows if r[4] != "专科")}')
    return headers, rows

if __name__ == '__main__':
    build()
