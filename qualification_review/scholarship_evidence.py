"""奖学金照片OCR提供名称、级别、日期和本人信息；按现有标准试算，照片结果均待复核。"""
import re
from pathlib import Path
from datetime import date
from education_evidence import IMAGES,norm
from review import awards,education,degree,interval
from school_lookup import SchoolDictionary


def is_scholarship(path):
    return any('奖学金证明材料' in part for part in Path(path).parts)


def scholarship_advice(fields,manifest,pages,master,overseas,cutoff):
    photos={f['path'] for f in manifest if is_scholarship(f['path']) and Path(f['path']).suffix.lower() in IMAGES}
    if not photos:return dict(tentative=0,approved=0,status='无材料',reason='奖学金证明材料没有上传图片',proofs=[])
    periods=[p for p in education(fields.get('学习经历','')) if p['degree']==degree(fields.get('最高学历'))]
    school_score,_=SchoolDictionary().lookup(fields.get('最高学历毕业院校',''),overseas)
    best=0;notes=[];seen=set()
    deadline=date.fromisoformat(cutoff)
    for page in pages:
        if page.get('source') not in photos:continue
        seen.add(page['source'])
        if page.get('status')!='ok':
            notes.append(Path(page['source']).name+'：OCR尚未成功，暂建议0分');continue
        lines=page.get('lines',[]);text=' '.join(l['text'] for l in lines)
        compact=norm(text)
        keys=[i for i,l in enumerate(lines) if re.search(r'奖学金|20\d{2}|学年',l['text']) or norm(fields.get('姓名','')) in norm(l['text'])]
        selected=set()
        for i in keys:selected.update(range(max(0,i-1),min(len(lines),i+2)))
        snippet=(' / '.join(lines[i]['text'] for i in sorted(selected)) or text)[:900]
        prefix=f'《{Path(page["source"]).name}》第{page.get("page",1)}页；OCR片段：{snippet}'
        if overseas:
            notes.append(prefix+'；境外奖学金按现有标准不加分');continue
        if not norm(fields.get('姓名')) or norm(fields.get('姓名')) not in compact:
            notes.append(prefix+'；本人姓名未匹配，暂建议0分');continue
        titles=sum(norm(l['text']) in {'奖学金证书','奖学证书','荣誉证书','获奖证明','证明'} for l in lines)
        if titles>1:
            notes.append(prefix+'；同图含多份证明，奖项、日期与学历阶段尚未唯一对应，暂建议0分；请分项复核');continue
        dates=[]
        for line in lines:
            raw=norm(line['text'])
            if re.search('出生|身份证|学号|入学',raw):continue
            for m in re.finditer(r'20\d{2}[年./-]\d{1,2}(?:[月./-]\d{1,2}日?|月)?',raw):
                span=interval(m[0])
                if span:dates.append((m[0],span))
        # 截止日看实际获奖/颁发日期，学年本身不能证明证书已在截止日前取得。
        if not dates:
            notes.append(prefix+'；未提取到明确获奖或颁发年月，暂建议0分；需核对取得日期');continue
        school_years=re.findall(r'(20\d{2})[—–~至-](20\d{2})学年',compact)
        if len(periods)==1 and any(int(end)<periods[0]['start'].year or int(start)>periods[0]['end'].year for start,end in school_years):
            notes.append(prefix+'；获奖学年不属于最高学历在读阶段，暂建议0分');continue
        values=[];detail=[]
        for when,span in dates:
            value,_,why=awards(when+' '+compact,'scholarship',periods,school_score,master,deadline,False)
            values.append(value)
            detail.append(why.replace(when+' '+compact,when).replace('\n取最高一项，不累计。',''))
        # 同一张图片有多个日期且推导得分不同，不挑选有利日期，交业务确认。
        value=values[0] if len(set(values))==1 else 0
        best=max(best,value)
        explanation='；日期存在多种解释，暂建议0分' if len(set(values))>1 else f'；按图片信息预计{value:g}分'
        notes.append(prefix+explanation+'；'+'；'.join(dict.fromkeys(detail)))
    if photos-seen:notes.append('部分奖学金照片尚未OCR，不能依据填报明细代替图片核验')
    notes.append('截至'+cutoff+'；只取最高一项，不累计；待复核（本人、级别、日期及最高学历阶段）')
    return dict(tentative=best,approved=None,status='待复核',reason='\n'.join(notes),proofs=sorted(photos))
