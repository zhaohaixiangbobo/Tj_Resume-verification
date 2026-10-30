"""管理岗学生工作及科研材料OCR建议分；限定经历阶段，保留关键原文，全部交业务复核。"""
import re
from pathlib import Path
from datetime import date
from education_evidence import IMAGES,norm
from review import education,interval
from skill_evidence import date_text


def is_management_material(path,code,master=True):
    word='学生工作' if code=='S14' else '科研成果' if master else '实习实践经历'
    return any(word in part for part in Path(path).parts)


def student_role(text,master=True):
    if re.search(r'拟任|计划担任|未担任|候选',text):return 0,'任职尚未确认'
    organization=r'(?:学生会|研究生会)' if master else r'学生会'
    high=re.search(r'(?<!副)班长|团支书|团支部书记|学生党支部(?:副)?书记|'+organization+r'.{0,12}(?:副部长|部长|副主席|主席)',text)
    if high:return (2 if master else 3),high[0]
    low=re.search(organization+r'.{0,12}干事|支部委员|班级委员|班委|副班长|学习委员|生活委员|宣传委员|组织委员|纪律委员|文体委员|学委',text)
    return (1,low[0]) if low else (0,'未明确识别到标准中的职务')


def research_type(lines,name):
    text=''.join(norm(l['text']) for l in lines);who=re.escape(norm(name))
    if re.search('软件著作权|计算机软件著作权登记',text):return 0,'软件著作权不属于本项要求的发明/实用新型授权专利'
    if re.search(r'accepted.*paper|camera-ready|录用通知',text,re.I):return 0,'论文录用/终稿提交材料不能证明已经公开发表及核心期刊级别'
    if re.search(r'课程作业|课程论文|校内普通结项|未发表|未授权|拟申请',text):return 0,'属于排除项或成果取得状态未确认'
    first_author=any(re.match(r'(?:第一作者[:：]?|作者[:：])'+who+r'(?:$|[,，、;；\d])',norm(l['text'])) for l in lines)
    first_inventor=any(re.match(r'(?:第一发明人[:：]?|发明人[:：])'+who+r'(?:$|[,，、;；\d])',norm(l['text'])) for l in lines)
    if re.search('发明专利|实用新型',text):
        if first_inventor and re.search('授权公告|授权日期|专利证书|授予专利权',text):return 1,'第一发明人、发明/实用新型专利授权信息'
        return 0,'专利需明确第一发明人及已授权状态，申请或受理不等于授权'
    if re.search('竞赛|大赛',text):
        if re.search('省级|省部级|国家级',text) and re.search('一等奖|二等奖|三等奖|金奖|银奖|铜奖|获奖',text) and re.search('学科|科研|科技|数学|计算机|物理|化学|电子|程序设计',text):
            return 1,'省级及以上学科/科研类竞赛获奖信息'
        return 0,'竞赛类别、级别或获奖情况未明确'
    if re.search('论文|期刊|journal',text,re.I):
        if first_author and re.search(r'核心期刊|CSSCI|CSCD|SCI(?:收录|期刊|检索)|SSCI|北大核心',text,re.I) and re.search('公开发表|发表日期|出版日期|已发表|Published',text,re.I) and not re.search('录用通知|待发表|拟发表',text):
            return 1,'第一作者、公开发表及核心期刊以上级别信息'
        return 0,'论文需核对第一作者、已公开发表及核心期刊以上级别；录用不能替代发表'
    return 0,'未识别到满足标准的论文、竞赛获奖或授权专利；著作/标准不直接计分'


def management_advice(code,fields,manifest,pages,cutoff,master=True):
    label='学生工作' if code=='S14' else '科研成果' if master else '实习实践经历'
    photos={f['path'] for f in manifest if is_management_material(f['path'],code,master) and Path(f['path']).suffix.lower() in IMAGES}
    if not photos:return dict(tentative=0,approved=0,status='无材料',reason=label+'没有上传图片，无佐证材料不予计分',proofs=[],key_info='无佐证图片')
    stages=({'本科','硕士'} if code=='S14' else {'硕士'}) if master else {'本科'}
    periods=[p for p in education(fields.get('学习经历','')) if p['degree'] in stages]
    deadline=date.fromisoformat(cutoff);best=0;notes=[];seen=set();key_info=[]
    for page in pages:
        if page.get('source') not in photos:continue
        seen.add(page['source'])
        if page.get('status')!='ok':notes.append(Path(page['source']).name+'：尚未完成OCR，暂预计0分');continue
        lines=page.get('lines',[]);text=''.join(norm(l['text']) for l in lines);name=norm(fields.get('姓名',''))
        issues=[]
        if not name or name not in text:issues.append('本人姓名未匹配')
        if code=='S14':
            # 名单型图片仅以本人邻近行识别职务，避免把其他人的职务算给本人。
            if '名单' in text:
                indices={j for i,l in enumerate(lines) if name and name in norm(l['text']) for j in range(max(0,i-1),min(len(lines),i+2))}
                role_text=''.join(norm(lines[j]['text']) for j in sorted(indices))
            else:role_text=text
            value,fact=student_role(role_text,master)
        elif master:value,fact=research_type(lines,fields.get('姓名',''))
        else:
            internship=re.search(r'实习|社会实践|实践活动',text)
            pending=re.search(r'拟实习|计划参加|拟参加|未参加|尚未|录用通知|实习邀请',text)
            value=2 if internship and not pending else 0
            fact='实习/社会实践经历' if value else '尚未确认实际参加实习实践'
        organization=[]
        for line in lines:
            raw=norm(line['text'])
            m=re.match(r'(?:实习单位|实践单位|任职单位|单位名称|实践内容|实习岗位)[:：](.{1,70})',raw)
            if m:organization.append(m[0])
            elif re.fullmatch(r'[\u4e00-\u9fffA-Za-z（）()·]{3,50}(?:有限公司|学校|学院|大学|委员会)',raw):organization.append(raw)
        dates=[]
        for line in lines:
            raw=date_text(re.sub(r'(?<=[零〇一二三四五六七八九])O(?=[零〇一二三四五六七八九])','〇',line['text']))
            if re.search('出生|身份证|学号|入学',raw):continue
            if code=='S15' and master and re.search('申请日|受理日|优先权日',raw):continue
            for m in re.finditer(r'20\d{2}[年./-]\d{1,2}(?:[月./-]\d{1,2}日?|月)?',raw):
                span=interval(m[0])
                if span:dates.append((m[0],span))
        if not dates:issues.append('任职/实践/成果取得日期未明确，不能用报名自述代替')
        if not master and code=='S15' and re.search(r'至\d{1,2}月',text):issues.append('实践结束日期省略年份，需核对完整起止时间')
        if not periods:issues.append('相应在读起止时间未能解析')
        for when,(lo,hi) in dates:
            if hi>deadline:issues.append(when+'超过或跨越统计截止日')
            if not any(p['start']<=lo and hi<=p['end'] for p in periods):issues.append(when+'不完全处于规定在读期间')
        if (code=='S14' or not master) and len(dates)>1:
            lo=min(d[1][0] for d in dates);hi=max(d[1][1] for d in dates)
            if not any(p['start']<=lo and hi<=p['end'] for p in periods):issues.append('任职/实践区间跨越在读阶段，需核对实际起止时间')
        if sum(norm(l['text']) in {'荣誉证书','聘书','任职证明','专利证书'} for l in lines)>1:issues.append('同图多份材料，人物/职务/成果/日期对应关系需复核')
        if issues:value=0
        best=max(best,value)
        reason=f'识别信息：{fact}'
        if organization:reason+='；'+'；'.join(dict.fromkeys(organization[:3]))
        if dates:reason+='；日期：'+'、'.join(dict.fromkeys(d[0] for d in dates))
        key_info.append(reason)
        reason+=f'；本材料预计{value}分'
        if issues:reason+='；'+'；'.join(dict.fromkeys(issues))
        notes.append(reason)
    if photos-seen:notes.append('部分图片尚未OCR，暂不依据报名信息加分')
    scope=('统计本科及硕士在读期间，最高2分' if code=='S14' else '仅限硕士在读期间，任一条件满足预计1分') if master else ('仅限本科在读期间，最高3分' if code=='S14' else '仅限本科在读期间，实习实践预计2分')
    notes.append(scope+f'；截止{cutoff}；不累计；待复核')
    return dict(tentative=best,approved=None,status='待复核',reason='\n'.join(dict.fromkeys(notes)),proofs=sorted(photos),key_info='\n'.join(dict.fromkeys(key_info)) or '暂无可识别关键信息')
