"""资格审查与院校字典的最小边界测试；均使用合成记录。"""
import sys
import unittest
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from review import within,major_matches,party,awards,student_score,internship,degree_status,PASS,FAIL,WAIT
from school_lookup import SchoolDictionary,qs_band

class CoreTests(unittest.TestCase):
    def test_degree_exact(self):
        self.assertEqual(degree_status('硕士','本科'),FAIL)
        self.assertEqual(degree_status('本科','硕士'),FAIL)
        self.assertEqual(degree_status('博士','硕士'),FAIL)
        self.assertEqual(degree_status('硕士','硕士'),PASS)
    def test_age_boundary(self):
        self.assertEqual(within('2008-10-31',date(1900,1,1),date(2008,10,31)),PASS)
        self.assertEqual(within('2008-11-01',date(1900,1,1),date(2008,10,31)),FAIL)
    def test_graduation_boundary(self):
        self.assertEqual(within('2027年07月',date(2025,1,1),date(2027,7,31)),PASS)
        self.assertEqual(within('2027年08月',date(2025,1,1),date(2027,7,31)),FAIL)
        self.assertEqual(within('不详',date(2025,1,1),date(2027,7,31)),WAIT)
    def test_major(self):
        self.assertTrue(major_matches('法学（030101K）','法学、计算机科学与技术'))
        self.assertFalse(major_matches('会计专业硕士','会计'))
        self.assertFalse(major_matches('法学理论','法学'))
        self.assertFalse(major_matches('法律（非法学）','法律（法学）'))
        self.assertTrue(major_matches('计算机科学与技术','软件工程,计算机科学\n与技术,人工智能'))
        self.assertTrue(major_matches('应用统计','数学,应用统\n计,统计学'))
    def test_party(self):
        self.assertTrue(party('中共预备党员'))
        self.assertFalse(party('非中共党员'))
    def test_dictionary(self):
        s=SchoolDictionary()
        for name,score in [('北京大学',40),('北京邮电大学',35),('天津工业大学',30),('燕山大学',25),('北京科技大学天津学院',20)]:
            self.assertEqual(s.lookup(name)[0],score)
        self.assertIsNone(s.lookup('北京大学某学院')[0])
        self.assertIsNone(s.lookup('Unknown University',True)[0])
        self.assertEqual(len(s.qs),200)
    def test_qs_boundaries(self):
        for rank,score in [('=50',40),('51',35),('=100',35),('101',30),('150',30),('151',25),('200',25),('201',20)]:
            self.assertEqual(qs_band(rank),score)
        self.assertIsNone(qs_band('151-250'))
    def test_awards_periods(self):
        p=[{'start':date(2025,9,1),'end':date(2027,6,30),'school':'甲大学'}]
        value,pending,_=awards('2022年11月国家励志奖学金\n2026年9月甲大学一等奖学金，校级\n2026年11月国家奖学金','scholarship',p,40,True,date(2026,10,31))
        self.assertEqual(value,2);self.assertFalse(pending)
    def test_business_incentive(self):
        p=[{'start':date(2023,9,1),'end':date(2027,6,30),'school':'甲大学'}]
        self.assertEqual(awards('2026年10月国家励志奖学金','scholarship',p,25,False,date(2026,10,31))[0],4)
        self.assertEqual(awards('2026年10月未获得国家奖学金','scholarship',p,25,False,date(2026,10,31))[0],0)
    def test_roles_and_internship(self):
        p=[{'start':date(2023,9,1),'end':date(2027,6,30),'degree':'本科','role':'副班长','raw':'副班长'}]
        self.assertEqual(student_score(p,False,date(2026,10,31))[0],1)
        self.assertEqual(internship('2025.08–2025.10 软件开发实习',p,date(2026,10,31))[0],2)
        self.assertIsNone(internship('2028.08–2028.10 软件开发实习',p,date(2026,10,31))[0])

if __name__=='__main__':unittest.main()
