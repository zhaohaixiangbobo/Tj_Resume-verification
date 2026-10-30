"""管理岗学生工作及科研照片分数、最高阶段和截止日期边界的必要测试。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from management_evidence import management_advice

FIELDS={'姓名':'张示例','学习经历':'示例大学 2019-09 2023-06 本科 法学 全日制 无\n示例大学 2024-09 2027-06 硕士 法学 全日制 无'}


def run(code,text,photo=True):
    path=('8.学生工作' if code=='S14' else '9.科研成果（发表论文、文章、专利、著作、标准）')+'/a.jpg'
    return management_advice(code,FIELDS,[{'path':path}] if photo else [],[dict(source=path,status='ok',page=1,lines=[{'text':x,'score':.99} for x in text.split('\n')])],'2026-10-31')


class ManagementTests(unittest.TestCase):
    def test_absence(self):
        for code in ['S14','S15']:self.assertEqual(run(code,'',False)['approved'],0)

    def test_roles(self):
        for role,value in [('班长',2),('副班长',1),('院学生会副部长',2),('研究生会干事',1),('学生党支部副书记',2),('普通学生',0)]:
            r=run('S14',f'张示例担任{role}\n2022年10月1日')
            self.assertEqual(r['tentative'],value);self.assertEqual(r['status'],'待复核')

    def test_research_categories(self):
        for text in ['论文\n第一作者：张示例\nCSSCI核心期刊\n公开发表日期：2025年10月1日',
                     '实用新型专利证书\n第一发明人：张示例\n授权公告日：2025年10月1日',
                     '张示例\n省级数学学科竞赛一等奖\n获奖日期：2025年10月1日']:
            self.assertEqual(run('S15',text)['tentative'],1)

    def test_master_stage_and_cutoff(self):
        for when in ['2022年10月1日','2026年11月1日']:
            self.assertEqual(run('S15',f'实用新型专利证书\n第一发明人：张示例\n授权公告日：{when}')['tentative'],0)
        self.assertEqual(run('S14','张示例担任班长\n2023年09月1日')['tentative'],0)

    def test_research_exclusions(self):
        for text in ['张示例课程论文\n核心期刊\n公开发表日期：2025年10月1日',
                     '张示例论文\n第二作者：张示例\nCSSCI核心期刊\n公开发表日期：2025年10月1日',
                     '发明专利申请\n第一发明人：张示例\n申请日：2025年10月1日']:
            self.assertEqual(run('S15',text)['tentative'],0)
        r=run('S15','张示例\nYour accepted short paper. Submit camera-ready.\n2025年10月1日')
        self.assertIn('不能证明已经公开发表',r['reason'])
        self.assertIn('软件著作权不属于',run('S15','张示例\n软件著作权登记\n2025年10月1日')['reason'])

    def test_unread_date_and_identity(self):
        self.assertEqual(run('S14','张示例担任班长')['tentative'],0)
        self.assertEqual(run('S14','李某担任班长\n2025年10月1日')['tentative'],0)


if __name__=='__main__':unittest.main()
