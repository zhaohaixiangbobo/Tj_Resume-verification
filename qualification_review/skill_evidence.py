"""技能证书固定字段核验：计算机、英语和法职/CPA分项建议分，保留OCR依据及疑点。"""
import re
from pathlib import Path
from datetime import date
from education_evidence import IMAGES,norm
from review import interval


def is_skill_material(path):
    return any(any(k in part for k in ('基本技能等级证书情况','其他证明材料','法律职业资格证明材料')) for part in Path(path).parts)


def bounds(line):
    box=line.get('box')
    return (min(p[0] for p in box),min(p[1] for p in box),max(p[0] for p in box),max(p[1] for p in box)) if box else None


def labeled(lines,labels,pattern,vertical=False):
    """同框或几何邻接取值；成绩表允许总分正下方数字，不串取其他分项。"""
    found=[]
    for line in lines:
        text=norm(line['text'])
        for label in labels:
            tag=norm(label)
            m=re.fullmatch(re.escape(tag)+r'[:：]?('+pattern+')',text,re.I)
            if m:found.append((m[1],[line]));continue
            if text.rstrip(':：').lower()!=tag.lower():continue
            b=bounds(line)
            if not b:continue
            candidates=[]
            for other in lines:
                value=norm(other['text']);ob=bounds(other)
                if not ob or not re.fullmatch(pattern,value,re.I):continue
                h=max(1,b[3]-b[1]);overlap=max(0,min(b[3],ob[3])-max(b[1],ob[1]))
                if ob[0]>=b[2] and overlap/min(h,max(1,ob[3]-ob[1]))>=.6:
                    candidates.append((ob[0]-b[2],value,other))
                if vertical and ob[1]>=b[3]-.15*h and ob[1]-b[3]<=4*h and b[0]<=((ob[0]+ob[2])/2)<=b[2]:
                    candidates.append((max(0,ob[1]-b[3]),value,other))
            candidates.sort(key=lambda t:t[0])
            if candidates and (len(candidates)==1 or candidates[1][0]-candidates[0][0]>3):
                found.append((candidates[0][1],[line,candidates[0][2]]))
    return found


def date_text(value):
    """中文年/月/日数字转成阿拉伯数字，仍保留原文用于输出。"""
    digits=dict(zip('零〇○一二三四五六七八九','000123456789'))
    def convert(m):
        s=m[0]
        if '十' in s:
            a,b=s.split('十');return str((int(digits[a]) if a else 1)*10+(int(digits[b]) if b else 0))
        return ''.join(digits[x] for x in s)
    return re.sub('[零〇○一二三四五六七八九十]+',convert,norm(value))


def extract_skill(page,fields,cutoff):
    lines=page.get('lines',[]);text=''.join(norm(l['text']) for l in lines)
    kind=None;code=None;points=0;details=[];problems=[];critical=[]
    if '全国计算机等级考试' in text or 'NATIONALCOMPUTERRANKEXAMINATION' in text.upper():
        kind='全国计算机等级考试';code='S09'
        levels=re.findall(r'([二三四234])级',text)
        if levels:
            levels=[{'二':2,'三':3,'四':4}.get(v,int(v) if v.isdigit() else 0) for v in levels]
            level=max(levels)
            points=1.5 if level>=3 else .5;details.append(f'{level}级')
            if len(set(levels))>1:problems.append('同页出现多个等级，需确认对应证书')
        else:problems.append('等级未明确')
        if not re.search('合格|优秀|良好|passed',text,re.I) or re.search('不合格|未通过',text):problems.append('未明确考试合格')
    else:
        english=[('CET-6',r'大学英语六级|CET[-－]?6',425,710,['总分','总成绩','TotalScore']),
                 ('TEM-4',r'专业英语四级|英语专业四级|TEM[-－]?4',60,100,['总分','成绩','总成绩','Score']),
                 ('TEM-8',r'专业英语八级|英语专业八级|TEM[-－]?8',60,100,['总分','成绩','总成绩','Score']),
                 ('IELTS',r'IELTS|雅思',6.5,9,['OverallBandScore','Overall','总分']),
                 ('TOEFL',r'TOEFL|托福',90,120,['TotalScore','Total','总分'])]
        matches=[x for x in english if re.search(x[1],text,re.I)]
        if matches:
            kind,_,threshold,maximum,labels=matches[0];code='S10'
            if len(matches)>1:problems.append('同页多种英语考试，需分开核对')
            scores=labeled(lines,labels,r'\d{1,3}(?:\.\d+)?',vertical=True)
            values={float(v) for v,_ in scores}
            if len(values)==1 and 0<=next(iter(values))<=maximum:
                actual=next(iter(values));points=.5 if actual>=threshold else 0
                details.append(f'总分{actual:g}，要求≥{threshold:g}')
                critical.extend(l for _,ls in scores for l in ls)
            else:problems.append('未提取唯一有效总分，不能采用听力、阅读等分项')
        elif '法律职业资格证书' in text or ('法律职业资格考试合格' in text and '特颁此证' in text):
            kind='法律职业资格证书';code='S11';points=1
            if '法律职业资格证书' not in text:problems.append('完整证书标题未识别清楚')
        elif '注册会计师' in text and re.search('全科合格证(?:书)?',text):
            kind='注册会计师全科合格证';code='S11';points=1
        elif '注册会计师' in text and re.search('专业阶段|单科',text):
            kind='CPA专业阶段/单科材料';code='S11';details.append('不属于全科合格证，0分')
        elif re.search('会计专业技术资格|会计从业资格',text):
            kind='会计职称/从业资格';code='S11';details.append('不属于法职或CPA全科合格证，0分')
        elif '计算机技术与软件专业技术资格' in text:
            kind='软考';code='S09';details.append('不属于全国计算机等级考试，0分')
    if not code:return None
    owner=norm(fields.get('姓名',''))
    owners=labeled(lines,['姓名','名','持证人','Name'],r'[\u4e00-\u9fff·A-Za-z]+')
    if owners:
        details.append('姓名：'+'、'.join(dict.fromkeys(v for v,_ in owners)))
        critical.extend(l for _,ls in owners for l in ls)
        if any(norm(v)!=owner for v,_ in owners):problems.append('证书姓名与报名不一致')
    elif owner and any(norm(l['text'])==owner for l in lines):
        details.append('姓名：'+fields['姓名']);critical.extend(l for l in lines if norm(l['text'])==owner)
    else:problems.append('本人姓名未可靠提取')
    ids=labeled(lines,['身份证号','身份证件号','身份证号码','证件号码'],r'\d{17}[\dXx]')
    critical.extend(l for _,ls in ids for l in ls)
    expected=norm(fields.get('身份证号码','')).upper()
    if ids and expected and any(v.upper()!=expected for v,_ in ids):problems.append('证件号码与报名不一致')
    numbers=labeled(lines,['证书编号','证书号码','成绩报告单编号'],r'[A-Za-z0-9-]{5,35}')
    if numbers:details.append('编号：'+'、'.join(dict.fromkeys(v for v,_ in numbers)))
    if kind in {'法律职业资格证书','注册会计师全科合格证'} and not numbers:problems.append('证书编号未明确')
    dates=[]
    for i,line in enumerate(lines):
        raw=date_text(line['text'])
        if re.search('出生|身份证|证件号码|证书编|学号',raw):continue
        if i and re.fullmatch('出生(?:日期|年月)?[:：]?',norm(lines[i-1]['text'])):continue
        box=bounds(line);height=page.get('image_size',[0,0])[1]
        bottom=bool(box and height and box[1]>=height*.65)
        if not re.search('考试时间|参加|发证|颁发|颁证|领证|日期|TestDate|Date',raw,re.I) and not bottom:continue
        for m in re.finditer(r'20\d{2}[年./-]\d{1,2}(?:[月./-]\d{1,2}日?|月)?',raw):
            span=interval(m[0])
            if span:dates.append((m[0],span,line))
    if dates:
        details.append('考试/颁发日期：'+'、'.join(dict.fromkeys(x[0] for x in dates)))
        if any(span[1]>date.fromisoformat(cutoff) for _,span,_ in dates):problems.append('日期超过或跨越截止日'+cutoff)
        critical.extend(l for _,_,l in dates)
    elif points:problems.append('考试或颁发日期未明确，需核对截止日')
    if re.search('作废|撤销|样本|样张|未取得|申请表',text):problems.append('材料存在状态或样本提示')
    if any(l.get('score',0)<.9 for l in critical):problems.append('关键字段OCR置信度不足')
    quotes=' / '.join(l['text'] for l in lines if l in critical or re.search('等级|合格|[二三四]级|资格|全科|专业阶段|总分|编号',norm(l['text'])))[:900]
    value=points if not problems else 0
    reason=f'《{Path(page["source"]).name}》第{page.get("page",1)}页；{kind}；'+'；'.join(details)+f'；本证预计{value:g}分'
    if problems:reason+='；'+'；'.join(dict.fromkeys(problems))
    reason+='\nOCR关键原文：'+quotes
    return dict(code=code,value=value,reason=reason,source=page['source'],kind=kind)


def skill_advice(fields,manifest,pages,cutoff):
    photos={f['path'] for f in manifest if is_skill_material(f['path']) and Path(f['path']).suffix.lower() in IMAGES}
    facts=[f for p in pages if p.get('source') in photos and p.get('status')=='ok' for f in [extract_skill(p,fields,cutoff)] if f]
    result={}
    for code,name in [('S09','全国计算机等级'),('S10','英语水平'),('S11','法职或CPA全科合格证')]:
        matches=[f for f in facts if f['code']==code]
        if not photos:reason='相关证书目录没有上传图片，无佐证材料不予计分'
        elif not matches:reason='未从相关图片识别到'+name+'的可用凭证，暂预计0分，待复核'
        else:reason='\n'.join(f['reason'] for f in matches)+'\n本项取最高一次，不累计；待复核，未进行在线真伪验证'
        result[code]=dict(tentative=max((f['value'] for f in matches),default=0),approved=0 if not photos else None,
                          status='无材料' if not photos else '待复核',reason=reason,proofs=list(dict.fromkeys(f['source'] for f in matches)))
    return result
