"""桌面与命令行共用的批次流程：先资格、再凭证、按岗位导出、带指纹人工复核。"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from collections import Counter
from review import run as review_run, text, FAIL, WAIT, PASS, NA
from evidence_routing import route_items
from evidence_pipeline import build_pages, digest, save, ROOT
from candidate_rules import candidate_category

VERSION='desktop-workflow-v1'
PROOF_TYPES={'.jpg','.jpeg','.png','.bmp','.webp','.pdf'}


def fingerprint(person, manifest, files):
    sources={p.name:digest(p) for p in [ROOT/'review.py',ROOT/'candidate_rules.py',ROOT/'evidence_routing.py',ROOT/'fixed_certificates.py',ROOT/'education_evidence.py',ROOT/'party_evidence.py',ROOT/'graduation_evidence.py',ROOT/'graduation_rules.py',ROOT/'scholarship_evidence.py',ROOT/'honor_evidence.py',ROOT/'skill_evidence.py',ROOT/'undergraduate_school.py',ROOT/'management_evidence.py',Path(__file__)]}
    return hashlib.sha256(json.dumps([VERSION,person,manifest,files,sources],ensure_ascii=False,
        sort_keys=True,default=str).encode('utf-8')).hexdigest()


def key(pid,job,code):
    return '|'.join((pid,job,code))


def allowed_scores(code, master):
    from review import MAX_MASTER, MAX_BACHELOR
    maximum=(MAX_MASTER if master else MAX_BACHELOR)[int(code[1:])-1]
    return {'S01':{20,25,30,35,40},'S07':{0,.5,1,2,3,5}|({4} if not master else set()),
            'S08':{0,1,3,5},'S09':{0,.5,1.5},'S12':{0,1,2,3,4} if master else {0},
            'S14':{0,1,maximum}}.get(code,{0,maximum})


def validate_decision(decision, person, code):
    """拒绝旧材料的审核、缺依据的通过及没有原图的正向证明。"""
    if code not in {f'Q{i:02}' for i in range(15)}|{f'S{i:02}' for i in range(1,16)}:
        raise ValueError('未知核验项目')
    if decision.get('fingerprint')!=person['fingerprint']:
        raise ValueError('填报、规则或材料已变化，旧审核需要重新确认')
    if not text(decision.get('reviewer')) or not text(decision.get('reason')):
        raise ValueError('每条审核须填写审核人和具体依据')
    selected=decision.get('proofs',[])
    if not isinstance(selected,list):raise ValueError('材料路径须为列表')
    known={f['path']:f['sha256'] for f in person['material_manifest']}
    for path in selected:
        if path not in known or not Path(path).is_file() or digest(path)!=known[path]:
            raise ValueError('引用材料不属于本人员或材料内容已变')
    positive=False
    if code.startswith('Q'):
        conclusion=decision.get('conclusion')
        if conclusion not in {PASS,FAIL,WAIT,NA}:raise ValueError('资格结论值不正确')
        if conclusion==NA and code in {'Q00','Q01','Q02','Q04','Q05','Q06','Q07','Q09','Q10','Q13'}:
            raise ValueError('必核资格项目不能设为不适用')
        if conclusion==NA and code in {'Q11','Q12'} and person.get('base_qualification',{}).get(code)!=NA:
            raise ValueError('岗位明确要求的党员或法律资格不能设为不适用')
        positive=conclusion==PASS
    else:
        value=decision.get('score')
        if isinstance(value,bool) or not isinstance(value,(int,float)) or value not in allowed_scores(code,person['master']):
            raise ValueError('得分不在该项目允许档位内')
        positive=value>0
    # 本科院校按本人填报、人岗匹配按本人填报性别定分；其余正向材料项目要求照片证明。
    proof_required=positive and ((code.startswith('S') and code not in {'S12','S13'}) or code in {'Q05','Q06','Q11','Q12'})
    if proof_required:
        if not any(Path(p).suffix.lower() in PROOF_TYPES for p in selected):
            raise ValueError('该正向结论必须关联照片或扫描证明材料')
        if decision.get('proof_checked') is not True:
            raise ValueError('请先查看原图并勾选已核对材料内容与本人归属')
    category=candidate_category(person['fields'].get('考生类别'))
    if code=='Q06' and positive and category['overseas']:
        try:
            award=date.fromisoformat(decision.get('degree_date',''))
            certification=date.fromisoformat(decision.get('certification_date',''))
        except (TypeError,ValueError):raise ValueError('境外学历认证通过须填写学位取得日期及认证完成日期（YYYY-MM-DD）')
        if not date(2025,1,1)<=award<=date(2027,7,31) or certification>date(2027,7,31):
            raise ValueError('境外学位须在2025-01-01至2027-07-31取得，认证最迟2027-07-31完成')
        if certification<award:raise ValueError('认证完成时间早于学位取得时间，请核对')


def load_decisions(path):
    if not path:return {}
    return json.loads(Path(path).read_text(encoding='utf-8')).get('decisions',{})


def evidence_for_person(person, options, out, cancel):
    routes=route_items(person['fields'])
    # 法律资格与党员属于资格要求，即使X项目分流跳过，也应继续查验对应材料。
    active=[dict(i) for i in routes]
    for item in active:
        if item['code'] in {'S14','S15'}:item['route']='verify'
    # 奖学金以实际上传照片为准，即使报名填否，也检查照片中的奖项。
    next(i for i in active if i['code']=='S07')['route']='verify'
    next(i for i in active if i['code']=='S08')['route']='verify'
    for item in active:
        if item['code'] in {'S09','S10','S11'}:item['route']='verify'
    for code in ('S04','S11'):
        if code=='S04':active.append({'code':code,'route':'verify'})
        elif person['base_qualification'].get('Q12')!=NA:
            next(i for i in active if i['code']==code)['route']='verify'
    from education_evidence import is_highest_education
    from party_evidence import is_other_proof
    from scholarship_evidence import is_scholarship
    selected_files=person['selected_files']
    if options.get('ocr_scope')=='education_party':
        selected_files=[f['path'] for f in person['material_manifest'] if is_highest_education(f['path']) or is_other_proof(f['path'])]
    elif options.get('ocr_scope')=='education_party_scholarship':
        selected_files=[f['path'] for f in person['material_manifest'] if is_highest_education(f['path']) or is_other_proof(f['path']) or is_scholarship(f['path'])]
    elif options.get('ocr_scope')=='skills':
        from skill_evidence import is_skill_material
        selected_files=[f['path'] for f in person['material_manifest'] if is_skill_material(f['path'])]
    elif options.get('ocr_scope')=='management':
        from management_evidence import is_management_material
        selected_files=[f['path'] for f in person['material_manifest'] if any(is_management_material(f['path'],c,person['master']) for c in ('S14','S15'))]
    pages,jobs,files=build_pages(Path(person['folder']),active,ROOT/'cache/evidence',
        int(options.get('max_pages',8)),bool(options.get('ocr')),selected_files,
        education_mode='overseas' if person.get('category',candidate_category(person['fields'].get('考生类别'))).get('overseas') else 'domestic')
    if jobs:
        request=out/'内部记录'/f'{person["pid"]}_ocr_jobs.json'
        save(request,{'jobs':jobs,'cancel_file':str(cancel)})
        subprocess.run([sys.executable,str(ROOT/'evidence_pipeline.py'),'--worker',str(request)],check=False)
        for page in pages:
            if '_result' in page:
                result=Path(page.pop('_result'))
                if result.exists():page.update(json.loads(result.read_text(encoding='utf-8')))
                else:page.update(status='cancelled' if cancel.exists() else 'error',reason='该页尚未处理完成')
    from fixed_certificates import route_pages
    fixed=route_pages(pages,person['name'],options.get('cutoff','2026-10-31'),person['fields'])
    ready=fixed.pop('model_pages')
    from education_evidence import is_highest_education
    # 最高学历目录统一由固定字段规则处理；识别不全交人工，不再请求大模型。
    from honor_evidence import is_honor
    from skill_evidence import is_skill_material,extract_skill
    ready=[p for p in ready if not is_highest_education(p.get('source','')) and not is_honor(p.get('source',''))
           and not (is_skill_material(p.get('source','')) and extract_skill(p,person['fields'],options.get('cutoff','2026-10-31')))]
    fixed['model_count']=len(ready)
    from management_evidence import is_management_material
    ready=[p for p in ready if not any(is_management_material(p.get('source',''),c,person.get('master',False)) for c in ('S14','S15'))]
    fixed['model_count']=len(ready)
    print(f'  [本地规则] {fixed["local_count"]}页免模型，{fixed["manual_count"]}页直接复核，{fixed["model_count"]}页保留原流程',flush=True)
    model={'pages':[],'events':[]}
    if options.get('llm') and not cancel.exists():
        from evidence_model import extract
        cfg=json.loads((ROOT/'evidence_config.json').read_text(encoding='utf-8'))
        cfg.update(options.get('model_config',{}))
        if ready:model=extract(person['pid'],ready,[i['code'] for i in active if i['route']!='skip'],cfg,ROOT/'cache/evidence/model')
    return {'pages':pages,'files':files,'model':model,'fixed':fixed}


def run_batch(options):
    source=Path(options['input']).resolve()
    materials=Path(options.get('materials') or source.parent).resolve()
    chosen=set(options.get('selected_ids',[])) or None
    out=Path(options['output']).resolve()
    out.mkdir(parents=True,exist_ok=False)
    cancel=Path(options.get('cancel_file') or out/'取消请求')
    started=datetime.now()
    print('[1/4] 核验资格与填报试算',flush=True)
    base=review_run(ROOT/'config.json',person_path=source,selected_ids=chosen,data_only=True)
    options=dict(options);options['cutoff']=base['config']['cutoff']
    if not base['persons']:raise ValueError('没有匹配的人员，请检查选择及报名表')
    counts=Counter(text(p['身份证号码']).upper() for _,p in base['persons'])
    if any(not i or n!=1 or '/' in i or '\\' in i or i in {'.','..'} for i,n in counts.items()):
        raise ValueError('本批次人员身份证号缺失、重复或含非法路径字符，请先处理')
    old=load_decisions(options.get('review_file'))
    people=[]; overrides={};applied={};stale=[]
    for row,p in base['persons']:
        ident=text(p['身份证号码']).upper();pid=hashlib.sha256(ident.encode()).hexdigest()[:16];job=text(p['岗位编码'])
        folder=Path(options.get('folders',{}).get(ident,materials/ident)).resolve()
        selected=options.get('files',{}).get(ident)
        paths=sorted({str(Path(f).resolve()) for f in selected}) if selected is not None else sorted(str(f.resolve()) for f in folder.rglob('*') if f.is_file()) if folder.is_dir() else []
        manifest=[{'path':f,'sha256':digest(f)} for f in paths]
        j=base['jobs'].get(job,(None,{}))[1]
        master='硕士' in text(j.get('学历要求',p['最高学历']))
        person={'pid':pid,'job':job,'name':text(p['姓名']),'ident':ident,'fields':p,'master':master,
                'category':candidate_category(p.get('考生类别')),'unit':text(p.get('招聘单位') or p.get('用人单位')),
                'job_name':text(p.get('岗位名称')),'folder':str(folder),'selected_files':paths if selected is not None else None,
                'material_manifest':manifest,'fingerprint':fingerprint(p,base['manifest'],manifest),'source_row':row,
                'base_qualification':{d[3]:d[5] for d in base['details'] if d[0]==pid and d[2]==job and d[3].startswith('Q')}}
        for k,decision in old.items():
            if not k.startswith(pid+'|'+job+'|'):continue
            code=k.rsplit('|',1)[-1]
            try:validate_decision(decision,person,code)
            except ValueError as exc:stale.append({'key':k,'reason':str(exc)});continue
            applied[k]=decision
            if code.startswith('Q'):overrides[(pid,job,code)]=decision
        people.append(person)
    if overrides:
        base=review_run(ROOT/'config.json',person_path=source,selected_ids=chosen,data_only=True,qualification_overrides=overrides)
    report={'version':VERSION,'created_at':started.isoformat(),'options':options,'manifest':base['manifest'],
            'persons':[],'decisions':applied,'stale_reviews':stale,'cancelled':False}
    for n,person in enumerate(people,1):
        if cancel.exists():report['cancelled']=True;break
        rows=[r for r in base['details'] if r[0]==person['pid'] and r[2]==person['job']]
        quals=[{'code':r[3],'name':r[4],'status':r[5],'reason':r[8],'raw':r[9],'source':r[10]} for r in rows if r[3].startswith('Q')]
        conclusion=FAIL if any(q['status']==FAIL for q in quals) else WAIT if any(q['status']==WAIT for q in quals) else PASS
        person.update(qualification=quals,conclusion=conclusion,scores=[],evidence={'pages':[],'files':[],'model':{'pages':[],'events':[]}})
        print(f'[2/4] {n}/{len(people)} 人员{person["pid"]}，资格{conclusion}',flush=True)
        if conclusion!=FAIL:
            routes={x['code']:x for x in route_items(person['fields'])}
            person['evidence']=evidence_for_person(person,options,out,cancel)
            from education_evidence import education_advice,education_score_advice,grade_advice,is_highest_education
            education=education_advice([p for p in person['evidence']['pages'] if is_highest_education(p.get('source',''))],person['fields'])
            from skill_evidence import skill_advice
            skills=skill_advice(person['fields'],person['material_manifest'],person['evidence']['pages'],options['cutoff'])
            for r in rows:
                if not r[3].startswith('S'):continue
                code=r[3];route=routes.get(code)
                score={'code':code,'name':r[4],'tentative':r[6],'approved':None,'maximum':r[7],
                       'reason':r[8],'raw':r[9],'source':r[10],'status':'待材料复核','proofs':[]}
                local=[f for f in person['evidence']['fixed']['pages'] if f['route']=='local' and code in f.get('recommendations',{})]
                if local:
                    score.update(tentative=max(f['recommendations'][code] for f in local),status='本地规则建议，待原图确认')
                    pageids={f['page_id'] for f in local}
                    score['proofs']=list(dict.fromkeys(p['source'] for p in person['evidence']['pages'] if p['page_id'] in pageids))
                    score['reason']+='\n固定证书字段经本地规则提取，姓名及日期检查通过，未调用大模型；原图仍须人工确认。'
                if code=='S13':
                    # 人岗匹配度按本人填报性别直接定分，不需要凭证也不计入待核验项；性别缺失时仍留待人工确认。
                    score.update(approved=r[6],proofs=[],
                        status='按本人填报性别定分' if r[6] is not None else '性别空白，待人工确认')
                elif route and route['route']=='skip':
                    if local:
                        score.update(tentative=None,approved=None,status='填报与证书冲突，待复核',reason='填报明确无此项目，但固定证书规则识别到相关材料；请核对是否申请加分。')
                    else:
                        score.update(tentative=0,approved=0,status='明确填报不加分',reason=route['reason'])
                elif r[6]==0 and code in {'S04','S03'}:
                    score.update(approved=0,status='按明确填报不加分')
                if code in {'S01','S02','S03'}:
                    score.update(education_score_advice(score,person['fields'],person['material_manifest'],person['category'],education))
                if code=='S06':score.update(grade_advice(person['fields'],person['material_manifest']))
                if code=='S07':
                    from scholarship_evidence import scholarship_advice
                    score.update(scholarship_advice(person['fields'],person['material_manifest'],person['evidence']['pages'],
                        person['master'],person['category'].get('overseas',False),options['cutoff']))
                if code=='S08':
                    from honor_evidence import honor_advice
                    score.update(honor_advice(person['fields'],person['material_manifest'],person['evidence']['pages'],
                        person['category'].get('overseas',False),options['cutoff']))
                if code=='S05':
                    from graduation_evidence import graduation_advice
                    score.update(graduation_advice(person['fields'],person['evidence']['pages'],
                        int(base['config']['cohort']),int(base['config']['graduation_start'][:4])))
                if code=='S04':
                    from party_evidence import party_advice
                    score.update(party_advice(person['fields'],person['material_manifest'],person['evidence']['pages']))
                if code in skills:score.update(skills[code])
                if code in {'S14','S15'}:
                    from management_evidence import management_advice
                    score.update(management_advice(code,person['fields'],person['material_manifest'],person['evidence']['pages'],options['cutoff'],person['master']))
                if code=='S12' and person['master']:
                    score.update(status='待核查' if r[5]==WAIT else '按本人填报',proofs=[],source='本人填报')
                decision=applied.get(key(person['pid'],person['job'],code))
                if decision:
                    score.update(approved=decision['score'],status='人工建议分',reason=r[8]+'\n人工审核：'+decision['reason'],proofs=decision['proofs'])
                if code=='S11' and score['approved'] is None:
                    score['reason']+='\n正向分必须查看本人相关照片/扫描证明；当前尚未完成人工材料确认。'
                person['scores'].append(score)
        report['persons'].append(person)
        save(out/'内部记录'/'批次结果.json',report)
    report['cancelled']=report['cancelled'] or cancel.exists()
    completed={p['pid'] for p in report['persons']}
    for person in people:
        if person['pid'] not in completed:
            person.update(conclusion='未处理',qualification=[],scores=[],evidence={'pages':[],'files':[],'model':{'pages':[],'events':[]}})
            report['persons'].append(person)
    report['elapsed_seconds']=(datetime.now()-started).total_seconds()
    print('[3/4] 按岗位输出赋分表与批次汇总',flush=True)
    from desktop_export import export_batch
    export_batch(report,out)
    save(out/'内部记录'/'批次结果.json',report)
    if options.get('export_review',True):
        save(out/'内部记录'/'人工审核.json',{'decisions':applied})
    print(f'[4/4] 完成：{out}；共{len(report["persons"])}人；取消状态{report["cancelled"]}',flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--request',type=Path,required=True)
    args=p.parse_args();run_batch(json.loads(args.request.read_text(encoding='utf-8')))
