"""院校名称精确匹配、QS分档和中英文数据导出；未知院校返回待核验。"""
from pathlib import Path
import csv
import json
import re
import unicodedata

ROOT = Path(__file__).resolve().parent

def normalize(name):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(name or ''))).casefold()

def qs_band(rank):
    """并列名次按公布数字分档；区间跨档时交人工核对。"""
    text = str(rank).strip().lstrip('=')
    match = re.fullmatch(r'(\d+)(?:[-–](\d+)|\+)?', text)
    if not match:
        return None
    lo, hi = int(match[1]), int(match[2] or match[1])
    if lo < 1 or hi < lo:
        return None
    def band(n):
        return next((v for end, v in [(50,40),(100,35),(150,30),(200,25)] if n <= end),20)
    return band(lo) if band(lo) == band(hi) else None

class SchoolDictionary:
    def __init__(self):
        with (ROOT/'data/domestic_schools.csv').open(encoding='utf-8-sig', newline='') as f:
            self.rows = list(csv.DictReader(f))
        self.domestic = {normalize(r['学校名称']):r for r in self.rows}
        # 更名依据见院校字典Excel的使用说明；仅列已核实对应关系。
        self.aliases = {'国防科学技术大学':'国防科技大学','第二军医大学':'海军军医大学',
                        '第四军医大学':'空军军医大学','上海体育学院':'上海体育大学'}
        self.qs = json.loads((ROOT/'data/qs_2027_bilingual.json').read_text(encoding='utf-8'))
        self.foreign = {}
        for r in self.qs:
            for name in [r['english'], r['chinese']]:
                self.foreign.setdefault(normalize(name), []).append(r)

    def lookup(self, name, overseas=False):
        if overseas:
            found = self.foreign.get(normalize(name), [])
            if len(found) == 1:
                r = found[0]
                return qs_band(r['rank']), f"QS2027 {r['rank']}名；{r['english']}；中文为整理译名"
            return None, '当前QS字典为官网前200名摘录，未命中不能判定为200名以后'
        name = self.aliases.get(str(name).strip(), name)
        r = self.domestic.get(normalize(name))
        if not r:
            return None, '院校名称未精确命中字典，请核对更名、分校、科研院所或党校'
        if r['办学层次'] == '专科':
            return None, '字典记载为专科院校，与本科及以上学历需交叉核验'
        score = {'985':40,'211':35,'其他双一流':30,'其他公办高校':25,'民办及独立学院':20}.get(r['计分层次'])
        return score, f"{r['学校名称']}：{r['计分层次']}；学校标识码{r['学校标识码']}；{r['层次来源']}"
