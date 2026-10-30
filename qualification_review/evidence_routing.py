"""凭证核验分流：依据明确填报决定跳过、查验或人工审核，空白保持未知。"""
import re
from review import text, degree, SCORE_NAMES, MAX_MASTER, MAX_BACHELOR

VERSION = 'evidence-routing-v1'
ABSENT = {'否', '无', '未取得', '未获得', '没有'}


def clean(value):
    return re.sub(r'\s+', '', text(value)).rstrip('。；;')


def route_items(person):
    """生成独立项目决定；共享自由文本只接受明确的整栏“无”或逐项否定。"""
    master = degree(person.get('最高学历')) == '硕士'
    limits = MAX_MASTER if master else MAX_BACHELOR
    extra_key = next((k for k in person if k.startswith(('其他职业资格证书', '法律职业资格证书'))), '')
    extra = clean(person.get(extra_key))
    grade_key = next((k for k in person if k.startswith('在读期间有无')), '')
    items = []
    for i in range(6, 16):
        item = dict(code=f'S{i:02}', name=SCORE_NAMES[i-1], maximum=limits[i-1],
                    route='verify', score=None, reason='需原始凭证支持；空白按未知处理',
                    sources=[], raw={}, evidence=[])
        if i == 6:
            item['sources'] = [grade_key] if grade_key else []
            value = clean(person.get(grade_key))
            if value == '是':
                item.update(route='skip', score=0, reason='明确填报有补考、重修或不合格记录，按本次确认口径不加分，跳过成绩凭证')
            elif value == '否':
                item['reason'] = '填报无补考重修等记录，需完整成绩材料或学校证明支持'
        elif i in (7, 8):
            flag, level, detail = (('高等教育期间是否取得奖学金','最高奖学金档次','奖学金') if i == 7
                                   else ('高等教育期间是否获得表彰奖励','最高表彰奖励档次','表彰奖励'))
            item['sources'] = [flag, level, detail]
            absent = clean(person.get(flag)) in ABSENT
            positive = any(clean(person.get(k)) not in ABSENT | {''} for k in (level, detail))
            if absent and positive:
                item.update(route='manual', reason='是否获奖填否，但档次或明细有内容，填报冲突需复核')
            elif absent:
                item.update(route='skip', score=0, reason='独立是否获奖字段明确填否且明细无冲突，跳过凭证')
        elif i in (9, 10):
            field = '计算机等级' if i == 9 else '英语等级'
            pattern = r'计算机|NCRE|软考' if i == 9 else r'英语|六级|专四|专八|雅思|托福|IELTS|TOEFL'
            item['sources'] = [field, extra_key] if extra_key else [field]
            if clean(person.get(field)) in ABSENT:
                if re.search(pattern, extra, re.I):
                    item.update(route='manual', reason='等级字段填无，但补充说明涉及该项目，需核对冲突')
                else:
                    item.update(route='skip', score=0, reason='独立等级字段明确填无，跳过该项凭证')
        elif i == 12:
            item['sources'] = ['学习经历', '最高学历']
            if not master and degree(person.get('最高学历')) == '本科':
                item.update(route='skip', score=0, reason='本科业务岗无本科学校附加分')
            else:
                item['reason'] = '需本科毕业材料与院校字典交叉核验；最高学历未知时人工确认适用标准'
        elif i == 13:
            # 人岗匹配度按本人填报性别直接定分，无需凭证；性别缺失或非男女取值才交人工。
            item['sources'] = ['性别']
            sex = clean(person.get('性别'))
            if sex == '男':
                item.update(route='skip', score=limits[12], reason=f'人岗匹配度按本人填报性别定分：男计本项满分{limits[12]}分，无需凭证')
            elif sex == '女':
                item.update(route='skip', score=0, reason='人岗匹配度按本人填报性别定分：女计0分，无需凭证')
            else:
                item.update(route='manual', reason='性别空白或非男女取值，人岗匹配度需业务部门人工确认')
        else:
            item['sources'] = [extra_key] if extra_key else []
            # 学生工作、实习还可能出现在经历栏，不能只凭AX否定覆盖AG。
            if i in (14, 15):
                item['sources'].append('学习经历')
            labels = {11: r'(?:其他职业资格证书|其他证书)',
                      14: r'(?:学生工作|学生干部经历)',
                      15: r'(?:科研成果|科研)' if master else r'(?:实习实践|实习)'}
            explicitly_absent = extra in ABSENT or bool(re.search(
                rf'(?:^|[;；。]){labels[i]}[:：](?:无|否)(?=$|[;；。])', extra))
            history = text(person.get('学习经历'))
            conflict = (i == 14 and bool(re.search(r'班长|团支|学生会|研究生会|党支部|班委|干事|部长', history))) or (
                i == 15 and bool(re.search(r'实习|专利|论文|科研|竞赛', history)))
            if explicitly_absent and not conflict:
                item.update(route='skip', score=0, reason='该项目明确填无，跳过凭证；保留填报依据')
            elif explicitly_absent:
                item.update(route='manual', reason='补充说明填无，但学习经历有相关内容，需人工复核')
        item['raw'] = {k: text(person.get(k)) for k in item['sources']}
        items.append(item)
    return items


def file_routes(filename):
    """只用清楚的上传栏目名称分流，未知文件始终纳入查验。"""
    groups = [('在校成绩', ['S06']), ('奖学金', ['S07']), ('表彰奖励', ['S08']),
              ('基本技能等级', ['S09', 'S10']), ('职业资格', ['S11']),
              ('学生工作', ['S14']), ('科研成果', ['S15']), ('实习实践', ['S15'])]
    for word, codes in groups:
        if word in filename:
            return codes
    return []
