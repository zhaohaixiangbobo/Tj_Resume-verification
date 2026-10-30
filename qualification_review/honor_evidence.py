"""表彰照片核验：限定荣誉、颁发机关、最高学历在读时间，取最高预计分并保留原文。"""
import re
from pathlib import Path
from datetime import date
from education_evidence import IMAGES,norm
from review import education,degree,interval

HONORS=re.compile(r'优秀毕业生|三好学生|优秀学生干部|优秀共产党员|优秀(?:共青)?团员|优秀(?:共青)?团干部')


def is_honor(path):
    return any('表彰奖励证明材料' in part for part in Path(path).parts)


def issuer_level(lines,school):
    """依据机关名称而非奖项中的“全国/省级”等宣传文字判断；不明机关交人工。"""
    found=[]
    for line in lines:
        raw=norm(line['text']).strip('。；;')
        value=re.sub(r'^(?:颁发机关|颁发单位|发证机关|授予单位|颁奖单位)[:：]','',raw)
        if re.fullmatch(r'(?:中华人民共和国)?教育部|共青团中央|中国共产主义青年团中央|中华全国学生联合会|中共中央组织部',value):
            found.append((5,'国家级',line['text']))
        elif re.fullmatch(r'(?:共青团|中国共产主义青年团).+(?:省|自治区|市)委员会',value):
            # 直辖市按省级，普通地级市机关不据此认定省部级。
            if '省' in value or '自治区' in value or any(x in value for x in ['北京市','上海市','天津市','重庆市']):
                found.append((3,'省部级',line['text']))
        elif re.fullmatch(r'.+(?:省教育厅|自治区教育厅|省委教育工作委员会)',value) or value in {'北京市教育委员会','天津市教育委员会','上海市教育委员会','重庆市教育委员会'}:
            found.append((3,'省部级',line['text']))
        elif school and (value==norm(school) or re.fullmatch(re.escape(norm(school))+r'(?:学生工作处|学生工作部|党委|团委|委员会|.+学院)',value)):
            found.append((1,'校级/院系级',line['text']))
    return max(found,key=lambda x:x[0]) if found else None


def honor_advice(fields,manifest,pages,overseas,cutoff):
    photos={f['path'] for f in manifest if is_honor(f['path']) and Path(f['path']).suffix.lower() in IMAGES}
    if not photos:return dict(tentative=0,approved=0,status='无材料',reason='表彰奖励证明材料没有上传图片，不予计分',proofs=[])
    periods=[p for p in education(fields.get('学习经历','')) if p['degree']==degree(fields.get('最高学历'))]
    deadline=date.fromisoformat(cutoff);notes=[];seen=set();best=0
    for page in pages:
        if page.get('source') not in photos:continue
        seen.add(page['source'])
        if page.get('status')!='ok':
            notes.append(Path(page['source']).name+'：图片未完成OCR，暂预计0分');continue
        lines=page.get('lines',[]);text=''.join(norm(l['text']) for l in lines)
        honors=list(dict.fromkeys(HONORS.findall(text)))
        issuer=issuer_level(lines,fields.get('最高学历毕业院校',''))
        keys=[i for i,l in enumerate(lines) if HONORS.search(norm(l['text'])) or re.search(r'20\d{2}|学年|颁发|授予|教育厅|委员会',l['text']) or (fields.get('姓名') and norm(fields['姓名']) in norm(l['text']))]
        indices=set()
        for i in keys:indices.update(range(max(0,i-1),min(len(lines),i+2)))
        snippet=(' / '.join(lines[i]['text'] for i in sorted(indices)) or ' / '.join(l['text'] for l in lines))[:900]
        prefix=f'《{Path(page["source"]).name}》第{page.get("page",1)}页；OCR片段：{snippet}'
        problems=[];dates=[]
        if overseas:problems.append('国（境）外表彰不赋分')
        if not honors:problems.append('未识别到规定范围内的荣誉名称')
        if re.search(r'拟授予|拟推荐|候选人|提名|拟表彰',text):problems.append('材料仅为拟表彰或候选信息')
        if not fields.get('姓名') or norm(fields['姓名']) not in text:problems.append('姓名未匹配本人')
        if sum(norm(l['text']) in {'荣誉证书','获奖证明','表彰证书'} for l in lines)>1:
            problems.append('同图多份证书，荣誉、日期与机关尚未唯一对应')
        for line in lines:
            raw=norm(line['text'])
            if re.search(r'出生|身份证|学号|入学',raw):continue
            for m in re.finditer(r'20\d{2}[年./-]\d{1,2}(?:[月./-]\d{1,2}日?|月)?',raw):
                span=interval(m[0])
                if span:dates.append((m[0],span))
        if not dates:problems.append('缺少明确获奖或颁发日期，获奖学年不能代替取得日期')
        if len(periods)!=1:problems.append('最高学历在读起止时间未唯一确定')
        else:
            period=periods[0]
            for when,(lo,hi) in dates:
                if lo<period['start'] or hi>period['end']:problems.append(when+'不完全处于最高学历在读期间')
                if hi>deadline:problems.append(when+'超出统计截止日或跨越截止日')
            for start,end in re.findall(r'(20\d{2})[—–~至-](20\d{2})学年',text):
                if int(end)<period['start'].year or int(start)>period['end'].year:problems.append('获奖学年不属于最高学历在读阶段')
        if not issuer:problems.append('颁发机关级别未明确，不能仅凭荣誉中的全国或省级字样认定')
        value=issuer[0] if issuer and not problems else 0
        best=max(best,value)
        facts='；荣誉：'+('、'.join(honors) or '未明确')
        if issuer:facts+=f'；颁发机关：{issuer[2]}，按{issuer[1]}预计{issuer[0]}分'
        if dates:facts+='；日期：'+'、'.join(dict.fromkeys(d[0] for d in dates))
        notes.append(prefix+facts+f'；本证预计{value}分'+('；'+'；'.join(dict.fromkeys(problems)) if problems else ''))
    if photos-seen:notes.append('部分表彰奖励图片尚未OCR，暂不依据填报信息加分')
    notes.append(f'截止日期{cutoff}；仅最高学历在读期间取得的规定荣誉；按最高一项，不累计；待复核')
    return dict(tentative=best,approved=None,status='待复核',reason='\n'.join(notes),proofs=sorted(photos))
