"""本科学生工作及实习实践图片门槛、分值和简洁输出测试。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from management_evidence import management_advice

FIELDS={'姓名':'张示例','学习经历':'示例大学 2021-09 2025-06 本科 软件工程 全日制 无'}


def run(code,text='',photo=True):
    path=('8.学生工作' if code=='S14' else '7.实习实践经历')+'/a.jpg'
    return management_advice(code,FIELDS,[{'path':path}] if photo else [],
        [dict(source=path,status='ok',page=1,lines=[{'text':x,'score':.99} for x in text.split('\n')])],
        '2026-10-31',False)


class BachelorTests(unittest.TestCase):
    def test_no_photos(self):
        for code in ('S14','S15'):
            r=run(code,photo=False);self.assertEqual(r['tentative'],0);self.assertEqual(r['key_info'],'无佐证图片')

    def test_student_scores(self):
        for role,score in [('班长',3),('院学生会副部长',3),('学习委员',1),('副班长',1),('研究生会主席',0)]:
            self.assertEqual(run('S14',f'张示例担任{role}\n2023年10月1日')['tentative'],score)

    def test_internship(self):
        r=run('S15','张示例实习证明\n实习单位：示例科技有限公司\n实习岗位：开发助理\n2023年7月1日至2023年8月31日\n这是一大段不相关的工作描述')
        self.assertEqual(r['tentative'],2);self.assertEqual(r['status'],'待复核')
        self.assertIn('示例科技有限公司',r['reason']);self.assertNotIn('不相关的工作描述',r['reason']);self.assertNotIn('OCR片段',r['reason'])

    def test_period_and_identity(self):
        for text in ['张示例实习证明\n2026年7月1日至2026年8月31日','其他人实习证明\n2023年7月1日至2023年8月31日','张示例拟参加社会实践\n2023年7月1日至2023年8月31日']:
            self.assertEqual(run('S15',text)['tentative'],0)

    def test_incomplete_date(self):
        self.assertEqual(run('S15','张示例实习证明')['tentative'],0)
        self.assertEqual(run('S15','张示例实习证明\n2023年7月1日至8月31日')['tentative'],0)


if __name__=='__main__':unittest.main()
