"""表彰照片核验的荣誉范围、机关级别、日期和不累计规则测试。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from honor_evidence import honor_advice

FIELDS={'姓名':'张示例','最高学历':'大学本科','最高学历毕业院校':'燕山大学',
        '学习经历':'燕山大学 2023-09 2027-06 本科 软件工程 全日制 无'}


def run(items,overseas=False,fields=None):
    pages=[];manifest=[]
    for i,text in enumerate(items):
        path=f'4.表彰奖励证明材料/{i}.jpg';manifest.append({'path':path})
        pages.append(dict(source=path,status='ok',page=1,lines=[{'text':t,'score':.99} for t in text.split('\n')]))
    return honor_advice(fields or FIELDS,manifest,pages,overseas,'2026-10-31')


class HonorTests(unittest.TestCase):
    def test_absent(self):
        r=run([]);self.assertEqual(r['tentative'],0);self.assertEqual(r['approved'],0)

    def test_allowed_titles(self):
        for name in ['优秀毕业生','三好学生','优秀学生干部','优秀共产党员','优秀团员','优秀团干部','优秀共青团员']:
            r=run([f'张示例\n{name}\n燕山大学\n2026年10月31日'])
            self.assertEqual(r['tentative'],1);self.assertEqual(r['status'],'待复核');self.assertIn(name,r['reason'])

    def test_issuer_and_maximum(self):
        for issuer,value in [('教育部',5),('河北省教育厅',3),('燕山大学学生工作处',1)]:
            r=run([f'张示例\n三好学生\n{issuer}\n2026年10月31日'])
            self.assertEqual(r['tentative'],value)
        r=run(['张示例\n三好学生\n燕山大学\n2026年10月31日','张示例\n优秀学生干部\n河北省教育厅\n2026年10月31日'])
        self.assertEqual(r['tentative'],3)

    def test_dates_and_stage(self):
        for when in ['2026年11月1日','2023年08月31日','2027年7月1日','2025-2026学年']:
            self.assertEqual(run([f'张示例\n三好学生\n燕山大学\n{when}'])['tentative'],0)

    def test_exclusions(self):
        for title in ['竞赛一等奖','优秀志愿者','优秀学生','拟授予三好学生']:
            self.assertEqual(run([f'张示例\n{title}\n教育部\n2026年10月1日'])['tentative'],0)
        self.assertEqual(run(['张示例\n三好学生\n教育部\n2026年10月1日'],True)['tentative'],0)

    def test_national_word_is_not_issuer_level(self):
        self.assertEqual(run(['张示例\n全国三好学生\n燕山大学\n2026年10月1日'])['tentative'],1)
        self.assertEqual(run(['张示例\n三好学生\n某社会评奖机构\n2026年10月1日'])['tentative'],0)

    def test_identity_and_birth_date(self):
        self.assertEqual(run(['李某\n三好学生\n教育部\n2026年10月1日'])['tentative'],0)
        self.assertEqual(run(['张示例出生于2002年09月\n三好学生\n教育部\n2026年10月1日'])['tentative'],5)


if __name__=='__main__':unittest.main()
