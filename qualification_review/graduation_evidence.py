"""毕业年限按学籍报告、毕业证、报名填报依次取日期，输出明确来源和待核查原因。"""
import re
from datetime import date
from education_evidence import norm,read_education,is_highest_education
from graduation_rules import graduation_points


def parse_date(value):
    text=norm(value)
    match=re.fullmatch(r'(\d{4})[年./-](\d{1,2})(?:[月./-](\d{1,2})日?|月)?',text)
    if not match:return None
    year,month,day=int(match[1]),int(match[2]),int(match[3] or 1)
    try:date(year,month,day)
    except ValueError:return None
    return year,month,int(match[3]) if match[3] else None


def graduation_advice(fields,pages,cohort=2027,start_year=2025):
    reported=str(fields.get('最高学历毕业时间') or '').strip()
    fallback=parse_date(reported)
    records=[];warnings=[]
    labels={'graduated':'毕业日期','expected':'预计毕业日期','leaving':'离校日期','issued':'发证日期'}
    for page in pages:
        if not is_highest_education(page.get('source','')) or page.get('status')!='ok':continue
        doc=read_education(page)
        if not doc:continue
        owner=doc['fields'].get('owner',{})
        if norm(owner.get('value'))!=norm(fields.get('姓名')) or owner.get('score',0)<.9:
            warnings.append(doc['title']+'姓名未可靠匹配');continue
        if '标题识别分数不足' in doc['issues']:
            warnings.append('材料标题识别不清');continue
        keys=('graduated','expected','leaving') if doc['kind']=='chsi' else ('graduated','issued')
        candidates=[]
        for key in keys:
            fact=doc['fields'].get(key)
            if key+'存在冲突' in doc['issues']:warnings.append(doc['title']+labels[key]+'存在冲突')
            if not fact:continue
            parsed=parse_date(fact['value'])
            if not parsed or fact['score']<.9:
                warnings.append(doc['title']+labels[key]+'识别不清');continue
            state=doc['fields'].get('student_status',{}).get('value','')
            if key=='leaving' and re.search('退学|肄业|开除|结业',state):
                warnings.append('离校状态不代表毕业');continue
            candidates.append((key,parsed))
        # 毕业证常把落款日期单独放在下方；只接受底部独立日期，避开出生和入学日期。
        if doc['kind']=='diploma' and not candidates:
            lines=page.get('lines',[])
            height=page.get('image_size',[0,0])[1]
            for line in lines:
                parsed=parse_date(line['text']);box=line.get('box',[])
                if parsed and line.get('score',0)>=.9 and height and box and min(p[1] for p in box)>=height*.65:
                    candidates.append(('issued',parsed))
        if candidates:
            if len({d[1] for d in candidates})>1:warnings.append(doc['title']+'日期字段不一致')
            key,parsed=candidates[0]
            records.append((0 if doc['kind']=='chsi' else 1,parsed,doc['title'],labels[key],doc['source']))
    records.sort(key=lambda r:r[0])
    chosen=records[0] if records else None
    actual=chosen[1] if chosen else fallback
    if chosen:
        y,m,d=actual;display=f'{y}年{m}月'+(f'{d}日' if d else '')
        reason=f'依据{chosen[2]}的{chosen[3]}：{display}'
        if chosen[3]=='发证日期':reason+='（按毕业证落款/发证日期试算）'
        if fallback and fallback!=actual:warnings.append('与报名填报毕业时间'+reported+'不一致')
        if any(r[1]!=actual for r in records):warnings.append('不同材料的毕业相关日期不一致')
        reason+='；未进行在线真伪验证'
    else:reason='报名填报毕业时间：'+(reported or '未填写')+'；未取得可用的学籍报告或毕业证日期；待核查'
    value=graduation_points(*actual,cohort=cohort,start_year=start_year) if actual else None
    if actual and value is None:warnings.append('毕业年份超出本次赋分范围')
    if warnings:reason+='；'+'；'.join(dict.fromkeys(warnings))+'；待核查'
    return dict(tentative=value,approved=None,status='待核查' if not chosen or warnings else '材料信息一致（建议）',
                reason=reason,proofs=list(dict.fromkeys(r[4] for r in records)))
