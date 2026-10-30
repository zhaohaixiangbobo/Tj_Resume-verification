"""技能证书门槛、固定表格总分位置及错误证书类型回归测试。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from skill_evidence import extract_skill,skill_advice,date_text

FIELDS={'姓名':'张示例','身份证号码':'130427200209210023'}
SOURCE='5.基本技能等级证书情况/a.jpg'


def page(*items):
    return dict(source=SOURCE,status='ok',page=1,lines=[{'text':s,'score':.99} for s in items])


def check(*items):
    return extract_skill(page(*items,'姓名：张示例','考试时间：2026年10月'),FIELDS,'2026-10-31')


class SkillTests(unittest.TestCase):
    def test_computer(self):
        for level,value in [('二',.5),('三',1.5),('四',1.5)]:
            self.assertEqual(check('全国计算机等级考试',level+'级合格证书')['value'],value)
        self.assertEqual(check('计算机技术与软件专业技术资格','高级资格')['value'],0)

    def test_english_thresholds(self):
        for title,threshold,label in [('大学英语六级考试',425,'总分'),('英语专业四级',60,'成绩'),('英语专业八级',60,'成绩'),('IELTS',6.5,'Overall Band Score'),('TOEFL',90,'Total Score')]:
            self.assertEqual(check(title,f'{label}：{threshold}')['value'],.5)
            self.assertEqual(check(title,f'{label}：{threshold-1}')['value'],0)

    def test_vertical_total(self):
        p=page('大学英语六级考试','姓名：张示例','考试时间：2026年10月')
        for text,box in [('总分',[[10,10],[30,10],[30,30],[10,30]]),('459',[[10,29],[30,29],[30,49],[10,49]]),('164',[[40,29],[60,29],[60,49],[40,49]])]:
            p['lines'].append(dict(text=text,score=.99,box=box))
        self.assertEqual(extract_skill(p,FIELDS,'2026-10-31')['value'],.5)

    def test_other_certificates(self):
        for title,value in [('法律职业资格证书',1),('注册会计师全国统一考试全科合格证',1),('注册会计师全国统一考试专业阶段考试合格证',0),('会计专业技术资格证书',0)]:
            self.assertEqual(check(title,'证书编号：A123456789')['value'],value)

    def test_identity_date_and_low_confidence(self):
        p=page('法律职业资格证书','姓名：其他人','证书编号：A123456789','颁证日期：2026年10月1日')
        self.assertEqual(extract_skill(p,FIELDS,'2026-10-31')['value'],0)
        p['lines'][1]['text']='姓名：张示例';p['lines'][-1]['text']='颁证日期：2026年11月1日'
        self.assertEqual(extract_skill(p,FIELDS,'2026-10-31')['value'],0)
        p['lines'][-1]['text']='颁证日期：2026年10月1日';p['lines'][1]['score']=.4
        self.assertEqual(extract_skill(p,FIELDS,'2026-10-31')['value'],0)

    def test_no_proof_and_maximum(self):
        r=skill_advice(FIELDS,[],[],'2026-10-31')
        self.assertTrue(all(s['tentative']==0 for s in r.values()))
        pages=[page('全国计算机等级考试',level+'级合格证书','姓名：张示例','考试时间：2026年10月') for level in ('二','三')]
        r=skill_advice(FIELDS,[{'path':SOURCE}],pages,'2026-10-31')
        self.assertEqual(r['S09']['tentative'],1.5)

    def test_chinese_date(self):
        self.assertEqual(date_text('颁证日期：二〇二六年十月二十一日'),'颁证日期:2026年10月21日')


if __name__=='__main__':unittest.main()
