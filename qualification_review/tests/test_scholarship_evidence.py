"""奖学金照片评分、截止日、最高学历阶段与缺材料规则测试。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scholarship_evidence import scholarship_advice

PATH='3.奖学金证明材料/奖学金.jpg'
FIELDS={'姓名':'张示例','最高学历':'大学本科','最高学历毕业院校':'燕山大学',
        '学习经历':'燕山大学 2023-09 2027-06 本科 软件工程 全日制 无'}


def run(text,photos=True):
    pages=[dict(source=PATH,page=1,status='ok',lines=[{'text':t,'score':.99} for t in text.split('\n')])]
    return scholarship_advice(FIELDS,[{'path':PATH}] if photos else [],pages,False,False,'2026-10-31')


class ScholarshipTests(unittest.TestCase):
    def test_missing(self):
        r=run('',False);self.assertEqual(r['tentative'],0);self.assertEqual(r['approved'],0)

    def test_national_and_school(self):
        for name,score in [('国家奖学金',5),('国家励志奖学金',4),('燕山大学校级一等奖学金',.5)]:
            r=run('张示例\n'+name+'\n2026年10月31日')
            self.assertEqual(r['tentative'],score);self.assertEqual(r['status'],'待复核');self.assertIn(name,r['reason'])

    def test_cutoff_and_stage(self):
        for when in ['2026年11月1日','2022年10月1日']:
            r=run('张示例\n国家奖学金\n'+when);self.assertEqual(r['tentative'],0)

    def test_academic_year_is_not_award_date(self):
        r=run('张示例\n2025-2026学年国家奖学金')
        self.assertEqual(r['tentative'],0);self.assertIn('取得日期',r['reason'])

    def test_birth_date_and_collage(self):
        r=run('张示例出生于2002年09月\n国家奖学金\n2026年10月31日')
        self.assertEqual(r['tentative'],5)
        r=run('张示例\n奖学金证书\n国家奖学金\n2026年10月31日\n奖学金证书\n2022年10月1日')
        self.assertEqual(r['tentative'],0);self.assertIn('多份证明',r['reason'])


if __name__=='__main__':unittest.main()
