"""学信网报告/毕业证的基础字段核对，以及成绩材料仅检查照片存在的业务规则。"""
import re
from pathlib import Path
import unicodedata

LABELS={'owner':['姓名','学生姓名'],'school':['学校名称','毕业院校'],
        'degree':['层次','学历层次','学历'],'form':['学习形式','学习方式'],'major':['专业','专业名称'],
        'graduated':['毕业日期','毕业时间'],'expected':['预计毕业日期','预计毕业时间','预毕业日期','预毕业时间'],
        'leaving':['离校日期','离校时间'],'issued':['发证日期','颁发日期'],'student_status':['学籍状态']}
IMAGES={'.jpg','.jpeg','.png','.bmp','.webp','.tif','.tiff'}


def norm(value):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(value or ''))).replace('普通全日制','全日制').replace('大学本科','本科').replace('硕士研究生','硕士').replace('博士研究生','博士')


def is_transcript(path):
    return any('最高学历在校成绩单或证明材料' in part or '最高学历在校成绩' in part for part in Path(path).parts)


def is_highest_education(path):
    return any('最高学历证明材料' in part for part in Path(path).parts)


def grade_advice(fields,manifest):
    key=next((k for k in fields if k.startswith('在读期间有无')),'')
    value=str(fields.get(key,'')).strip()
    photos=[f['path'] for f in manifest if is_transcript(f['path']) and Path(f['path']).suffix.lower() in IMAGES]
    if value=='是':return dict(tentative=0,approved=0,status='按填报不加分',reason='报名系统自填有重修',proofs=[])
    if value=='否':return dict(tentative=2 if photos else 0,approved=None,status='待核验',
        reason='有最高学历成绩单，待核验' if photos else '无最高学历成绩单，待核验',proofs=photos)
    return dict(tentative=None,approved=None,status='待核验',reason='报名系统未明确填写是否有重修，待核验',proofs=photos)


def read_education(page):
    """标签和值同框或几何同一行；不使用单纯OCR相邻序号猜测表格关系。"""
    lines=page.get('lines',[]);kind=None;title=None
    for line in lines:
        t=norm(line['text'])
        if t in {'教育部学籍在线验证报告','教育部学历证书电子注册备案表'}:kind='chsi';title=line;break
        if re.fullmatch(r'(?:普通高等学校|普通高等教育|中华人民共和国)?毕业证书',t):kind='diploma';title=line
    if not kind:return None
    found={};issues=[]
    all_labels={x for labels in LABELS.values() for x in labels}
    def bounds(line):
        b=line.get('box')
        return (min(p[0] for p in b),min(p[1] for p in b),max(p[0] for p in b),max(p[1] for p in b)) if b else None
    for field,labels in LABELS.items():
        values=[]
        for line in lines:
            t=unicodedata.normalize('NFKC',line['text']).strip()
            for label in labels:
                match=re.fullmatch(re.escape(label)+r'\s*[:：]\s*(\S.*?)',t)
                if match:values.append({'value':match[1],'line_ids':[line['index']],'quote':line['text'],'score':line.get('score',0)})
            if norm(t).rstrip(':：') not in labels:continue
            box=bounds(line)
            if box is None:continue
            candidates=[]
            for other in lines:
                ob=bounds(other)
                if ob is None or ob[0]<box[2] or norm(other['text']).rstrip(':：') in all_labels:continue
                overlap=max(0,min(box[3],ob[3])-max(box[1],ob[1]))
                if overlap/max(1,min(box[3]-box[1],ob[3]-ob[1]))>=.65:
                    candidates.append((ob[0]-box[2],other))
            candidates.sort(key=lambda v:v[0])
            if candidates and (len(candidates)==1 or candidates[1][0]-candidates[0][0]>5):
                other=candidates[0][1]
                values.append({'value':other['text'],'line_ids':[line['index'],other['index']],
                    'quote':line['text']+'\n'+other['text'],'score':min(line.get('score',0),other.get('score',0))})
        if values:
            if len({norm(v['value']) for v in values})==1:found[field]=values[0]
            else:issues.append(field+'存在冲突')
    # 毕业证正文常写“学生 姓名 性别男/女”，使用明确语法提取，避免只支持表格标签。
    if kind=='diploma' and 'owner' not in found:
        for line in lines:
            match=re.match(r'^(?:学生)?([\u4e00-\u9fff·]{2,12}?)性别[男女]',norm(line['text']))
            if match:
                found['owner']={'value':match[1],'line_ids':[line['index']],'quote':line['text'],'score':line.get('score',0)}
                break
    if title.get('score',0)<.9:issues.append('标题识别分数不足')
    for name in ('owner','school','degree','form'):
        if name not in found:issues.append('缺少'+name)
        elif found[name]['score']<.9:issues.append(name+'识别分数不足')
    return {'page_id':page['page_id'],'kind':kind,'fields':found,'issues':issues,
            'source':page.get('source',''),'title':title['text']}


def education_advice(pages,fields):
    parsed=[x for p in pages if p.get('status')=='ok' for x in [read_education(p)] if x]
    result={}
    # 优先同一类型的全部材料核对，存在冲突时不通过较有利的一份覆盖。
    for code,field,column in [('S01','school','最高学历毕业院校'),('S02','degree','最高学历'),('S03','form','最高学历学习形式')]:
        chsi=[x for x in parsed if x['kind']=='chsi']
        selected=chsi+[x for x in parsed if x['kind']=='diploma']
        if not selected:continue
        supported=[];problems=[]
        if any(p.get('status')!='ok' for p in pages):problems.append('部分最高学历材料尚未完成识别')
        for doc in selected:
            owner=doc['fields'].get('owner');actual=doc['fields'].get(field)
            problems.extend(x for x in doc['issues'] if x.startswith(('标题','owner',field,'缺少owner')))
            if not owner or norm(owner['value'])!=norm(fields.get('姓名')):problems.append('姓名未能与考生匹配')
            if actual and norm(actual['value'])!=norm(fields.get(column)):problems.append(column+'与填报不一致')
            supported.append(doc['source'])
        preferred=next((d for d in selected if field in d['fields']),None)
        if preferred is None:problems.append(column+'未能从材料提取，待人工核验')
        title=(preferred or selected[0])['title']
        result[code]={'status':'材料信息一致（建议）' if not problems else '材料信息待核验',
            'reason':f'依据{title}核对{column}，与报名填报一致；未进行在线真伪验证' if not problems else f'{title}：'+'；'.join(dict.fromkeys(problems)),
            'proofs':list(dict.fromkeys(supported)),'matched':not problems}
    return result


def education_score_advice(score, fields, manifest, category, checks):
    """三个项目独立给建议分；材料存在与字段核对分开记录，保留人工确认边界。"""
    code=score['code']
    photos=[f['path'] for f in manifest if is_highest_education(f['path']) and Path(f['path']).suffix.lower() in IMAGES]
    presence='有佐证照片' if photos else '无佐证照片'
    pending='国外高校待人工核验' if category.get('overseas') else '待人工核验'
    result=dict(approved=None,status='待人工核验',proofs=photos)
    if code=='S01':
        from school_lookup import SchoolDictionary
        points,note=SchoolDictionary().lookup(fields.get('最高学历毕业院校',''),category.get('overseas',False))
        result['tentative']=points if points is not None else 20
        if points is None:
            result['reason']='院校库无填写院校；'+presence+'，'+pending
            if checks.get(code) and not checks[code]['matched']:
                result['reason']+='；'+checks[code]['reason']
            return result
        tier=({40:'QS1–50',35:'QS51–100',30:'QS101–150',25:'QS151–200',20:'QS200+'} if category.get('overseas') else
              {40:'985院校',35:'211院校',30:'其他双一流院校',25:'其他公办高校',20:'普通民办、独立学院或其他院校'})[points]
        prefix=tier+'；'
    else:prefix=''
    if category.get('overseas'):
        result['reason']=prefix+'依据报名填报试算；'+presence+'，'+pending
        return result
    check=checks.get(code)
    if check:
        result.update(status=check['status'],proofs=check['proofs'],reason=prefix+check['reason']+'；'+presence)
        if not check['matched']:result['reason']+='，待人工核验'
        if code=='S03' and '未能从材料提取' in check['reason']:
            result['reason']+='；依据报名填报学习形式试算'
    else:
        result['reason']=prefix+'依据报名填报试算；未取得可用的学籍报告或毕业证核对结果；'+presence+'，待人工核验'
    return result
