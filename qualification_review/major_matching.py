"""专业名称规范化与三级匹配：明确符合、疑似相关待复核、明确不匹配。

只消除排版差异，专业包含关系、共同前缀和英文译名用于提示复核。
法律（法学）与法律（非法学）保持独立，不由去括号操作互相转换。
"""
from dataclasses import dataclass
import re
import unicodedata

RULE_VERSION = 'major-v2-20261026'
PASS, FAIL, WAIT = '符合', '不符合', '待复核'
SEPARATORS = ',，、;；'
LEGAL = {'法学', '非法学'}

def canonical(value):
    raw = '' if value is None else str(value)
    raw = raw.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\r', '\n')
    raw = unicodedata.normalize('NFKC', raw)
    return re.sub(r'[\s\u200b\u200c\u200d\ufeff]', '', raw).casefold()

@dataclass(frozen=True)
class MajorList:
    items: tuple[str, ...]
    issue: str = ''

@dataclass(frozen=True)
class Match:
    status: str
    kind: str
    actual: str
    matched: tuple[str, ...]
    allowed: tuple[str, ...]
    reason: str

def parse_allowed(value):
    """只按括号外标点分隔专业。无分隔符的多行名单保留歧义。"""
    raw = '' if value is None else str(value)
    raw = raw.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\r', '\n')
    raw = unicodedata.normalize('NFKC', raw)
    depth = 0; parts = []; current = []; separated = False
    for ch in raw:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                return MajorList((), '岗位专业括号不配对')
        if depth == 0 and ch in SEPARATORS:
            separated = True
            if canonical(''.join(current)):
                parts.append(canonical(''.join(current)))
            current = []
        else:
            current.append(ch)
    if depth:
        return MajorList((), '岗位专业括号不配对')
    if canonical(''.join(current)):
        parts.append(canonical(''.join(current)))
    parts = tuple(dict.fromkeys(parts))
    if not parts:
        return MajorList((), '岗位专业清单为空')
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not separated and len(lines) > 1:
        return MajorList(parts, '只有换行而无专业分隔标点，无法确定是排版断行还是多个专业')
    return MajorList(parts)

def split_name(name):
    """得到专业主体及顺序括号内容；嵌套、残缺或括号后正文交人工核对。"""
    m = re.fullmatch(r'([^()]+)((?:\([^()]+\))*)', name)
    if not m:
        return None
    return m[1], tuple(re.findall(r'\(([^()]+)\)', m[2]))

def legal_qualifiers(parts):
    return {x for x in parts if x in LEGAL}

def code_note(part):
    return bool(re.fullmatch(r'(?:专业代码[:：]?)?\d{4,6}[a-z]?', part))

def common_prefix(a,b):
    count=0
    for x,y in zip(a,b):
        if x!=y:break
        count+=1
    return count

def compare_major(actual, allowed):
    result = parse_allowed(allowed)
    a = canonical(actual)
    def done(status,kind,candidates,why):
        return Match(status,kind,a,tuple(dict.fromkeys(candidates)),result.items,why)
    if not a:
        return done(WAIT,'缺少专业',(),'填报主专业为空')
    if result.issue:
        return done(WAIT,'清单解析待核对',(),result.issue)
    ap = split_name(a)
    if ap is None:
        return done(WAIT,'名称结构待核对',(),'填报专业存在残缺/嵌套括号或括号后正文')
    abase,anotes=ap
    if any(ch in abase for ch in SEPARATORS+'/'+'|'):
        return done(WAIT,'多个名称待核对',(),'填报项可能含多个专业或中英文并列名称，须指定报考主专业')
    if re.search(r'未学|未就读|不是|不属于|拟报|拟学',a):
        return done(WAIT,'表述待核对',(),'包含否定或计划性表述，需确认实际主专业')
    if any(any(ch in note for ch in SEPARATORS) for note in anotes):
        return done(WAIT,'括号多项待核对',(),'括号内含多个限定或方向，保留原文核对')
    if a in result.items:
        return done(PASS,'规范化后精确命中',(a,),'仅统一全半角、英文大小写、空白和排版换行，完整名称一致')
    parsed=[(b,split_name(b)) for b in result.items]
    if any(p is None for _,p in parsed):
        return done(WAIT,'清单结构待核对',(),'岗位专业存在嵌套括号或其他未支持结构')
    # 显式限定的冲突先记录。另有精确命中已在上方返回。
    conflicts=[];possible=[];bracket_hits=[]
    for b,(bbase,bnotes) in parsed:
        aq,bq=legal_qualifiers(anotes),legal_qualifiers(bnotes)
        if abase==bbase and aq and bq and aq.isdisjoint(bq):
            conflicts.append(b);continue
        if abase==bbase:
            # 主体相同但需求限定缺失或不同，不用主体命中覆盖限定。
            if bnotes and not (a.startswith(b+'(') and all(code_note(x) for x in anotes[len(bnotes):])):
                possible.append(b);continue
            extra=anotes[len(bnotes):]
            if extra and all(code_note(x) for x in extra):
                bracket_hits.append(b);continue
            if aq or bq or abase=='法律':
                possible.append(b);continue
            if any(re.fullmatch(r'[a-z][a-z0-9 .&/-]*',x) for x in extra):
                possible.append(b);continue
            if extra:
                bracket_hits.append(b);continue
        # 英文翻译、专业简称和大类隶属关系均不在此处猜测。
        if any('\u4e00'<=ch<='\u9fff' for ch in abase+bbase):
            if min(len(abase),len(bbase))>=2 and (abase in bbase or bbase in abase or common_prefix(abase,bbase)>=2):
                possible.append(b)
        if {abase,bbase}=={'法律','法学'}:
            possible.append(b)
    if bracket_hits:
        return done(PASS,'附加括号说明命中',bracket_hits,'完整要求名称后附研究方向/代码说明；未删除要求本身的限定。专业代码未作目录校验')
    if possible:
        return done(WAIT,'疑似相关名称',possible,
                    '仅发现主体、包含关系或至少两个相同前缀字；可能是多写“专业”、学位修饰、别名或不同专业，须核对正式专业名称及岗位要求')
    if conflicts:
        return done(FAIL,'法律限定冲突',conflicts,'法学与非法学限定不同，且未命中岗位其他允许专业')
    if re.search(r'[a-z]',abase):
        return done(WAIT,'英文或缩写待核对',(),'未精确命中英文名称；需经审核的中英文名称对应关系，不自动翻译后放行')
    return done(FAIL,'未命中',(),'完整名称及已支持的括号规则均未命中，也未发现规定的疑似名称关系')

def explain(match):
    candidates='、'.join(match.matched) or '无'
    return f'匹配类型：{match.kind}\n规范化填报：{match.actual}\n命中/候选专业：{candidates}\n{match.reason}'
