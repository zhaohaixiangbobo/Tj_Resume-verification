"""政治面貌建议分：检查其他证明材料照片，保留本人党员信息的OCR原文片段。"""
import re
from pathlib import Path
from education_evidence import IMAGES, norm
from review import party


def is_other_proof(path):
    return any('其他证明材料' in part for part in Path(path).parts)


def party_advice(fields, manifest, pages):
    value=str(fields.get('政治面貌') or '').strip()
    base=dict(approved=None,status='待人工核验',proofs=[])
    if value and not party(value):
        return dict(base,tentative=0,approved=0,status='按明确填报不加分',reason='报名填写为非党员')
    if not value:
        return dict(base,tentative=None,reason='报名未填写政治面貌，待人工核验')
    photos={f['path'] for f in manifest if is_other_proof(f['path']) and Path(f['path']).suffix.lower() in IMAGES}
    if not photos:
        return dict(base,tentative=0,reason='其他证明材料没有上传材料')
    relevant=[p for p in pages if p.get('source') in photos]
    excerpts=[];proofs=[];supported=False;problems=[];conflict=False
    # 只从照片OCR原文取片段；积极分子、发展对象、党课证书不能等同党员证明。
    positive=re.compile(r'中共(?:正式|预备)?党员|中国共产党(?:正式|预备)?党员|政治面貌[:：]?党员')
    for page in relevant:
        if page.get('status')!='ok':continue
        lines=page.get('lines',[])
        definite=[i for i,l in enumerate(lines) if positive.search(norm(l['text']))]
        hits=[i for i,l in enumerate(lines) if re.search(r'党员|转正',norm(l['text']))]
        if not hits:continue
        owner_lines=[i for i,l in enumerate(lines) if norm(fields.get('姓名')) and norm(fields['姓名']) in norm(l['text'])]
        nearby=[i for i in hits if any(abs(i-j)<=3 for j in owner_lines)]
        hits=definite or nearby or hits[:2]
        indices=set()
        for i in hits:indices.update(range(max(0,i-2),min(len(lines),i+3)))
        indices.update(owner_lines)
        snippet=' / '.join(lines[i]['text'] for i in sorted(indices))
        excerpt=f'《{Path(page["source"]).name}》第{page.get("page",1)}页：{snippet}'
        excerpts.append(excerpt);proofs.append(page['source'])
        hittext=''.join(norm(lines[i]['text']) for i in indices)
        negative=re.search(r'非中共|不是.*党员|并非.*党员|尚未.*党员|未成为.*党员|取消.*党员|开除党籍',hittext)
        reliable=all(lines[i].get('score',0)>=.9 for i in set(definite+owner_lines))
        if negative:conflict=True;problems.append('材料含非党员或资格变更表述')
        if not owner_lines:problems.append('姓名未匹配本人')
        if not reliable:problems.append('部分关键文字OCR置信度不足')
        if not definite:problems.append('仅发现党员活动或转正相关表述，尚不能据此确认党员身份')
        if definite and owner_lines and reliable and not negative:supported=True
    supported=supported and not conflict
    # 有党员相关片段但身份、置信度或证明性质待确认时，先给满分建议并保留疑点。
    suggested=5 if excerpts and not conflict else 0
    incomplete=any(p.get('status')!='ok' for p in relevant) or photos-{p.get('source') for p in relevant}
    reason='有其他证明材料照片；'
    if excerpts:
        reason+='OCR相关片段：\n'+'\n'.join(excerpts)
        reason+='\n'+('识别到本人党员相关信息，建议5分；待人工核验' if supported else
                     '有党员相关证明，尚不能明确确认，暂建议5分；待人工核验' if suggested==5 else
                     '材料含非党员或资格变更表述，暂建议0分；待人工核验')
        if problems:reason+='；'+'；'.join(dict.fromkeys(problems))
    else:
        reason+='尚未取得可用的本人党员证明片段，暂建议0分；待人工核验'
    if incomplete:reason+='；部分照片尚未完成OCR'
    return dict(base,tentative=suggested,reason=reason,proofs=list(dict.fromkeys(proofs)) or sorted(photos))
