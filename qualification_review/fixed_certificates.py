"""固定证书的本地字段提取和模型分流；所有事实保留OCR行号，疑点转人工或模型。"""
import re
import unicodedata
from collections import defaultdict
from datetime import date

VERSION='fixed-certificates-v1'
TITLES=[
    ('legal',r'(?:中华人民共和国)?法律职业资格证书(?:[ABC]类)?'),
    ('cpa_all',r'(?:中华人民共和国)?注册会计师全国统一考试全科合格证(?:书)?'),
    ('cpa_subject',r'注册会计师全国统一考试(?:专业阶段考试合格证(?:书)?|单科成绩单)'),
    ('accounting',r'(?:中华人民共和国)?(?:会计专业技术资格证书|会计专业技术资格|会计从业资格证书)'),
    ('diploma',r'(?:普通高等学校|普通高等教育|中华人民共和国)?毕业证书'),
]
LABELS={
    'owner':r'(?:姓名|学生姓名|持证人)[:：]?([\u4e00-\u9fff·]{2,20})',
    'number':r'(?:证书编号|证书号码|证书号)[:：]?([A-Za-z0-9-]{5,35})',
    'issuer':r'(?:发证机关|发证单位|颁发单位|发证机构)[:：]?([\u4e00-\u9fff（）()·]{3,60})',
    'school':r'(?:学校名称|毕业院校|学校)[:：]?([\u4e00-\u9fff（）()·]{3,60})',
    'major':r'(?:所学专业|专业名称|专业)[:：]?([\u4e00-\u9fff（）()·]{2,40})',
    'degree':r'(?:学历层次|培养层次|学历|层次)[:：]?(大学本科|本科|硕士研究生|博士研究生|硕士|博士|大专|专科)',
    'form':r'(?:学习形式|学习方式)[:：]?(非全日制|全日制|函授|业余|脱产)',
    'level':r'(?:资格级别|资格等级|级别|等级)[:：]?(初级|中级|高级|[ABC]类)',
    'date':r'(?:发证日期|颁发日期|签发日期|毕业日期|毕业时间|批准日期)[:：]?(\d{4}[年./-]\d{1,2}[月./-]\d{1,2}日?)',
}
CODES={'legal':['S11'],'cpa_all':['S11'],'cpa_subject':['S11'],'accounting':['S11'],
       'diploma':['S01','S02','S03','S05','S12']}


def compact(value):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(value or '')))


def parse_date(value):
    parts=re.findall(r'\d+',value)
    if len(parts)!=3:raise ValueError('日期不完整')
    return date(*map(int,parts))


def extract_page(page, expected_name, cutoff):
    from education_evidence import read_education, norm
    education=read_education(page)
    if education and education['kind']=='chsi':
        issues=list(education['issues'])
        owner=education['fields'].get('owner')
        if not owner or norm(owner['value'])!=norm(expected_name):issues.append('姓名与考生不一致')
        return {'page_id':page['page_id'],'document_type':'chsi','item_codes':['S01','S02','S03'],
            'fields':[{'name':k,**v,'ocr_score':v['score']} for k,v in education['fields'].items()],
            'issues':issues,'status':'local_complete' if not issues else 'fallback',
            'recommendations':{},'engine':VERSION}
    result={'page_id':page['page_id'],'document_type':'unknown','item_codes':[],
            'fields':[],'issues':[],'status':'fallback','recommendations':{},'engine':VERSION}
    lines=page.get('lines',[])
    hits=[]
    for line in lines:
        value=compact(line['text'])
        for kind,pattern in TITLES:
            if re.fullmatch(pattern,value):hits.append((kind,line))
    if len(hits)!=1:
        result['issues']=['未命中唯一固定证书标题，保留原流程']
        return result
    kind,title=hits[0];result.update(document_type=kind,item_codes=CODES[kind])
    facts=defaultdict(list)
    for line in lines:
        # 标签和值只在同一OCR行提取，避免邻列错配；未解决版式交给原流程。
        raw=line['text'];normalized=unicodedata.normalize('NFKC',raw)
        normalized=re.sub(r'\s*([:：])\s*',r'\1',normalized)
        for field,pattern in LABELS.items():
            for match in re.finditer(r'(?:^|[;；，,\s])'+pattern,normalized):
                value=match[1]
                if field in {'owner','issuer','school','major'}:
                    value=re.split(r'性别|证书编号|出生日期|身份证|专业|学制|学历|发证日期',value)[0]
                if value:
                    fact={'name':field,'value':value,'line_ids':[line['index']], 'quote':raw,
                          'ocr_score':line.get('score'), 'box':line.get('box')}
                    facts[field].append(fact);result['fields'].append(fact)
    required=['owner','number','date']+(['school','major','degree','form'] if kind=='diploma' else ['issuer'])
    if kind=='accounting':required+=['level']
    values={k:{compact(f['value']) for f in v} for k,v in facts.items()}
    for field in required:
        if field not in values:result['issues'].append('缺少字段：'+field)
        elif len(values[field])!=1:result['issues'].append('字段冲突：'+field)
    if values.get('owner') and values['owner']!={compact(expected_name)}:
        result['issues'].append('姓名与考生不一致');result['status']='manual'
    important=[title]+[{'score':f['ocr_score']} for f in result['fields'] if f['name'] in required]
    if any(x.get('score') is None or x['score']<.9 for x in important):
        result['issues'].append('关键字段OCR分数不足，需复核（分数不代表准确率）')
    if len(values.get('date',[]))==1:
        try:
            when=parse_date(next(iter(values['date'])))
            if when>date.fromisoformat(cutoff):
                result['issues'].append('证书日期超过核验截止日');result['status']='manual'
        except ValueError:result['issues'].append('日期无效，需复核')
    full='\n'.join(x['text'] for x in lines)
    if re.search(r'样本|样张|模板|作废|撤销|待领取|申请表|成绩单|补充说明|另附|奖学金|实习|学生干部',full):
        result['issues'].append('存在状态或其他事项文字，需完整判读')
    if not result['issues']:
        result['status']='local_complete'
        if kind in {'legal','cpa_all'}:result['recommendations']={'S11':1}
        elif kind in {'accounting','cpa_subject'}:
            result['note']='本证不属于已确认的法律资格/CPA全科加分证书；不据此断定本人没有其他证书'
    return result


def route_pages(pages, expected_name, cutoff='2026-10-31', expected_fields=None):
    """整个原始文件有缺页、冲突或未识别页时保留全文件判读，禁止静默丢弃背面。"""
    facts=[extract_page(p,expected_name,cutoff) for p in pages if p.get('status')=='ok']
    for fact in facts:
        if fact['document_type']=='diploma' and expected_fields:
            mapping={'school':'最高学历毕业院校','major':'最高学历所学专业','degree':'最高学历','form':'最高学历学习形式'}
            norm=lambda v:compact(v).replace('大学本科','本科').replace('硕士研究生','硕士').replace('博士研究生','博士')
            for field,column in mapping.items():
                expected=expected_fields.get(column)
                extracted=[x['value'] for x in fact['fields'] if x['name']==field]
                if expected and extracted and any(norm(x)!=norm(expected) for x in extracted):
                    fact['status']='manual';fact['issues'].append(column+'与填报不一致，可能为其他学历阶段材料，需核对')
    factmap={f['page_id']:f for f in facts}
    groups=defaultdict(list)
    for p in pages:groups[p.get('doc_id',p['page_id'])].append(p)
    local_ids=set();manual_ids=set()
    for members in groups.values():
        extracted=[factmap.get(p['page_id']) for p in members]
        if any(f and f['status']=='manual' for f in extracted):
            manual_ids.update(p['page_id'] for p in members)
            continue
        if all(f and f['status']=='local_complete' for f in extracted):
            identities={(f['document_type'],tuple(sorted((x['name'],compact(x['value'])) for x in f['fields'] if x['name'] in {'owner','number','date'}))) for f in extracted}
            if len(identities)==1:local_ids.update(p['page_id'] for p in members)
            else:
                for f in extracted:f['issues'].append('同一文件多页证书字段不一致，需完整判读')
    # 同类证书跨文件冲突也不自动消解，不挑选较有利的一个结果。
    bykind=defaultdict(list)
    for f in facts:
        if f['page_id'] in local_ids:bykind[f['document_type']].append(f)
    for fs in bykind.values():
        numbers={x['value'] for f in fs for x in f['fields'] if x['name']=='number'}
        if len(numbers)>1:
            for f in fs:
                manual_ids.add(f['page_id']);local_ids.discard(f['page_id']);f['issues'].append('同类多证书编号不同，需人工核对')
    for f in facts:
        f['route']='local' if f['page_id'] in local_ids else 'manual' if f['page_id'] in manual_ids else 'model'
        if f['route']!='local':f['recommendations']={}
    model_pages=[p for p in pages if p.get('status')=='ok' and p['page_id'] not in local_ids|manual_ids]
    return {'version':VERSION,'pages':facts,'model_pages':model_pages,'local_count':len(local_ids),
            'manual_count':len(manual_ids),'model_count':len(model_pages)}
