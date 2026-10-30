"""界面与Excel共用人工审核入口：验证材料、允许档位、指纹，保留修改历史。"""
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import openpyxl
from desktop_workflow import key, validate_decision
from evidence_pipeline import save
from desktop_export import HEADERS


def apply_decisions(report, decisions, path):
    current=json.loads(Path(path).read_text(encoding='utf-8')).get('decisions',{}) if Path(path).exists() else {}
    people={(p['pid'],p['job']):p for p in report['persons']}
    updated=deepcopy(current)
    seen=set()
    for identity,code,decision in decisions:
        k=key(identity[0],identity[1],code)
        if k in seen:raise ValueError('同一项目重复审核：'+k)
        seen.add(k)
        if identity not in people:raise ValueError('审核人员不属于当前批次')
        person=people[identity]
        if code not in {x['code'] for x in person['qualification']+person['scores']}:
            raise ValueError('当前人员没有该审核项目，明确不符合者不能直接赋分')
        validate_decision(decision,person,code)
        if decision.get('stage') not in {'初审','复审'}:raise ValueError('审核阶段应为初审或复审')
        previous=current.get(k)
        # 导出的未改动审核记录再次导入时保持幂等。
        fields=['conclusion','score','reason','reviewer','proofs','proof_checked','stage','degree_date','certification_date','fingerprint']
        if previous and all(previous.get(f)==decision.get(f) for f in fields):continue
        history=deepcopy(previous.get('history',[])) if previous else []
        if previous:history.append({k:v for k,v in previous.items() if k!='history'})
        if decision['stage']=='复审':
            prior=[x for x in history if x.get('stage')=='初审' and x.get('fingerprint')==person['fingerprint']]
            if not prior:raise ValueError('请先完成本版材料的初审，再进行复审')
            if prior[-1]['reviewer']==decision['reviewer']:raise ValueError('初审和复审应由不同人员完成')
        decision=deepcopy(decision);decision.update(reviewed_at=datetime.now().isoformat(timespec='seconds'),history=history)
        updated[k]=decision
    # 全部验证通过后一次性保存；任一行错误不会部分导入。
    save(Path(path),{'decisions':updated})
    return len(seen)


def import_reviews(report, workbook, destination):
    book=openpyxl.load_workbook(workbook,data_only=False)
    if '复核录入' not in book:raise ValueError('请选择含复核录入Sheet的工作簿')
    sheet=book['复核录入']
    headers=[c.value for c in sheet[1]]
    if headers!=HEADERS:raise ValueError('复核表表头发生变化，请使用当前程序导出的表')
    decisions=[]
    for row in sheet.iter_rows(min_row=2):
        values=[c.value for c in row];r=dict(zip(headers,values))
        if not r['复核结论'] and r['复核得分'] is None:continue
        if any(c.data_type=='f' for c in row):raise ValueError(f'第{row[0].row}行含公式，请填明确值')
        def strval(name):return str(r[name] or '').strip()
        d={'fingerprint':strval('输入指纹'),'conclusion':strval('复核结论'),'score':r['复核得分'],
           'reason':strval('复核依据'),'reviewer':strval('审核人'),
           'proofs':[str(Path(x.strip()).resolve()) for x in strval('证明材料路径（每行一个）').splitlines() if x.strip()],
           'proof_checked':strval('已核对原图')=='是','stage':strval('审核阶段') or '初审',
           'degree_date':strval('境外学位取得日期'),'certification_date':strval('境外认证完成日期')}
        decisions.append(((strval('人员编号'),strval('岗位编码')),strval('项目编号'),d))
    return apply_decisions(report,decisions,destination)
