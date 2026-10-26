"""专业三级匹配的业务边界测试，覆盖括号限定、修饰词和排版断行。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from major_matching import compare_major,parse_allowed,PASS,WAIT,FAIL

class MajorMatchingTests(unittest.TestCase):
    def test_three_way_matching(self):
        cases=[
            ('网络工程','网络工程',PASS),
            ('网络工程专业','网络工程',WAIT),
            ('会计专业硕士','会计学、会计',WAIT),
            ('会计学','会计',WAIT),
            ('专业硕士会计','会计',WAIT),
            ('马克思主义理论','马克思主义哲学',WAIT),
            ('法学理论','法学',WAIT),
            ('会计','财务管理',FAIL),
            ('酒店管理','工商管理,财务管理',FAIL),
            ('软件工程','财务管理,市场营销',FAIL),
            ('Accounting','会计',WAIT),
            ('会计（MPAcc）','会计',WAIT),
            ('Computer Science','computer science',PASS),
            ('网络\u200b工程专业','网络工程',WAIT),
            ('','网络工程',WAIT),
            ('软件工程、会计','软件工程',WAIT),
            ('未学习会计','会计',WAIT),
        ]
        for actual,allowed,status in cases:
            with self.subTest(actual=actual,allowed=allowed):
                self.assertEqual(compare_major(actual,allowed).status,status)
    def test_legal_qualifiers(self):
        cases=[
            ('法律（非法学）','法律（法学）',FAIL),
            ('法律（法学）','法律（非法学）',FAIL),
            ('法律(非法学)','法律（法学）,法律（非法学）',PASS),
            ('法律（法学）','法律,法律（法学）,法律（非法学）',PASS),
            ('法律','法律（法学）',WAIT),
            ('法律（非法学）','法律',WAIT),
            ('法律（非法学）','法律,法律（法学）',WAIT),
            ('法律（非法学）','法学',WAIT),
            ('法律（法学、非法学）','法律',WAIT),
            ('法律（法学）（035102）','法律（法学）',PASS),
        ]
        for actual,allowed,status in cases:
            with self.subTest(actual=actual,allowed=allowed):
                self.assertEqual(compare_major(actual,allowed).status,status)
    def test_brackets_and_codes(self):
        for actual,allowed,status in [
            ('法学（030101K）','法学',PASS),
            ('计算机科学与技术（软件方向）','计算机科学与技术',PASS),
            ('计算机科学与技术（软件方向）','计算机科学与技术（网络方向）',WAIT),
            ('法学（030101K','法学',WAIT),
            ('法学(方向(民法))','法学',WAIT),
            ('会计','会计（财务方向）',WAIT),
        ]:
            with self.subTest(actual=actual):
                self.assertEqual(compare_major(actual,allowed).status,status)
    def test_list_delimiters_and_newlines(self):
        raw='计算机科学\\n与技术，\n软件工程；法律（法学、非法学）'
        parsed=parse_allowed(raw)
        self.assertFalse(parsed.issue)
        self.assertEqual(parsed.items,('计算机科学与技术','软件工程','法律(法学、非法学)'))
        self.assertEqual(compare_major('计算机科学与技术','软件工程,计算机科学\n与技术').status,PASS)
        self.assertEqual(compare_major('应用统\n计','数学、应用统计').status,PASS)
        self.assertEqual(compare_major('软件工程','软件工程\n会计').status,WAIT)
        self.assertEqual(compare_major('法学','法学,法律（非法学').status,WAIT)
    def test_current_job_lists(self):
        import openpyxl
        path=Path(__file__).resolve().parents[2]/'3.天津市烟草专卖局（公司）招聘岗位计划表.xlsx'
        s=openpyxl.load_workbook(path,data_only=True).worksheets[0]
        count=0
        for row in s.iter_rows(min_row=2,values_only=True):
            if not row[3]:continue
            count+=1
            for cell in [row[6],row[7]]:
                if cell:
                    parsed=parse_allowed(cell)
                    self.assertFalse(parsed.issue, (row[3],parsed.issue))
                    self.assertTrue(all('\\n' not in x and '\n' not in x for x in parsed.items))
                    for item in parsed.items:
                        self.assertEqual(compare_major(item,cell).status,PASS,(row[3],item))
        self.assertEqual(count,26)

if __name__=='__main__':unittest.main()
