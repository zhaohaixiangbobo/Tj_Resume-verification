"""毕业年限日期优先级、日期误取和报名兜底的最小回归测试。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from graduation_evidence import graduation_advice
from graduation_rules import graduation_points


def page(title,label,value,owner='张示例'):
    lines=[title,'姓名：'+owner,label+'：'+value]
    return dict(page_id='P1',status='ok',source='1.最高学历证明材料/a.jpg',
                lines=[dict(index=i,text=t,score=.99) for i,t in enumerate(lines)])


class GraduationTests(unittest.TestCase):
    fields={'姓名':'张示例','最高学历毕业时间':'2027年06月15日'}

    def test_cohort_boundaries(self):
        for args,expected in [((2026,7,31),5),((2026,8,1),10),((2027,7,31),10),((2027,8,1),None)]:
            self.assertEqual(graduation_points(*args),expected)

    def test_report_priority_and_actual_score(self):
        docs=[page('毕业证书','毕业日期','2027年06月15日'),page('教育部学籍在线验证报告','离校日期','2025年06月18日')]
        r=graduation_advice(self.fields,docs)
        self.assertEqual(r['tentative'],5);self.assertIn('离校日期：2025年6月18日',r['reason'])
        self.assertIn('不一致',r['reason']);self.assertEqual(r['status'],'待核查')

    def test_expected_and_diploma(self):
        for title,label in [('教育部学籍在线验证报告','预计毕业日期'),('毕业证书','毕业日期')]:
            r=graduation_advice(self.fields,[page(title,label,'2027年06月15日')])
            self.assertEqual(r['tentative'],10);self.assertIn(label,r['reason'])

    def test_fallback_ignores_birth_update_and_wrong_owner(self):
        for docs in [[],[page('教育部学籍在线验证报告','更新日期','2025年06月01日')],
                     [page('毕业证书','出生日期','2002年06月01日')],
                     [page('教育部学籍在线验证报告','毕业日期','2025年06月01日','其他人')]]:
            r=graduation_advice(self.fields,docs)
            self.assertEqual(r['tentative'],10);self.assertIn('报名填报毕业时间',r['reason']);self.assertIn('待核查',r['reason'])

    def test_invalid_and_missing_dates(self):
        r=graduation_advice(dict(self.fields,最高学历毕业时间=''),[page('毕业证书','毕业日期','2025年02月30日')])
        self.assertIsNone(r['tentative']);self.assertIn('未填写',r['reason'])


if __name__=='__main__':unittest.main()
