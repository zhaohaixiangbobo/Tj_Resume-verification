"""本科院校仅依填报计分及毕业年度QS资料边界测试。"""
import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from undergraduate_school import undergraduate_score
from school_lookup import SchoolDictionary


class UndergraduateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.schools=SchoolDictionary()

    def score(self,name,year=2024):
        return undergraduate_score([{'degree':'本科','school':name,'end':date(year,6,30)}],self.schools)

    def test_domestic_tiers(self):
        for name,points,label in [('北京大学',4,'985院校'),('北京交通大学',3,'211院校'),('燕山大学',1,'其他公办高校')]:
            score,reason,pending=self.score(name)
            self.assertEqual(score,points);self.assertEqual(reason,'本科'+label);self.assertFalse(pending)

    def test_missing(self):
        self.assertEqual(undergraduate_score([],self.schools)[0],0)
        self.assertEqual(self.score('不存在的测试院校')[0],0)

    def test_qs_year(self):
        self.assertEqual(self.score('University of Cambridge',2027)[0],4)
        result=self.score('University of Cambridge',2024)
        self.assertEqual(result[0],0);self.assertTrue(result[2]);self.assertIn('QS2024',result[1])

    def test_equivalent(self):
        self.assertEqual(self.score('中央党校')[0],3)
        self.assertEqual(self.score('中共河北省委党校')[0],1)


if __name__=='__main__':unittest.main()
