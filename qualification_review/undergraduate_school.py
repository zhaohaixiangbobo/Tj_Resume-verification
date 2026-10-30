"""管理岗本科院校附加分仅使用本人填报；境外院校按本科毕业年份的QS版本匹配。"""
import json
import re
from school_lookup import ROOT,normalize,qs_band


def undergraduate_score(periods,schools):
    under=[p for p in periods if p['degree']=='本科']
    if len(under)!=1:return 0,'本科院校层次未体现（本科经历未唯一确定）',True
    school=under[0]['school'];key=normalize(school)
    equivalent={'中国科学院':(3,'参照211院校'),'中国社会科学院':(3,'参照211院校'),
                '中央党校':(3,'参照211院校'),'中共中央党校':(3,'参照211院校'),
                '中共中央党校（国家行政学院）':(3,'参照211院校')}
    if school in equivalent:
        value,label=equivalent[school];return value,'本科'+label,False
    # 仅按本人填报中的明确机关层级标识参照赋分，不用模糊包含关系推断机构级别。
    if re.search(r'国家级.*科学院',school):return 3,'本科国家级科学院（参照211院校）',False
    if re.search(r'省部级.*(?:科学院|研究院)',school) or re.fullmatch(r'(?:中共)?[\u4e00-\u9fff]{2,8}省委党校',school):
        return 1,'本科省部级科研院所/省委党校（参照其他公办高校）',False
    raw,_=schools.lookup(school)
    if raw is not None:
        label={40:'985院校',35:'211院校',30:'其他双一流院校',25:'其他公办高校',20:'普通民办、独立学院或其他院校'}[raw]
        return (raw-20)/5,'本科'+label,False
    domestic=schools.domestic.get(key)
    if domestic:
        if '合作' in str(domestic.get('备注','')) or '合作' in str(domestic.get('办学性质','')):
            return 0,'本科中外合作办学院校（参照QS200+；未据填报确认同时取得境外学位及留服认证）',False
        return 0,'本科院校层次未体现（计分层次待核查）',True
    year=under[0]['end'].year
    data=ROOT/'data'/f'qs_{year}_bilingual.json'
    if data.exists():
        rows=json.loads(data.read_text(encoding='utf-8'))
        matches=[r for r in rows if key in {normalize(x) for x in [r['english'],r.get('chinese','')]+r.get('aliases',[])}]
        if len(matches)==1:
            raw=qs_band(matches[0]['rank'])
            if raw is not None:
                label={40:'QS1–50',35:'QS51–100',30:'QS101–150',25:'QS151–200',20:'QS200+'}[raw]
                return (raw-20)/5,f'本科{label}（QS{year}）',False
    return 0,f'本科院校层次未体现（院校未匹配或缺本科毕业当年QS{year}资料），暂0分，待核查',True
