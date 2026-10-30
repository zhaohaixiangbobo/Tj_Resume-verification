"""政治面貌照片门槛、原文引用和身份匹配的最小回归测试。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from party_evidence import party_advice

PHOTO='10.其他证明材料（中共党员、其他职业资格、职称等证明材料）/证明.jpg'
FIELDS={'姓名':'张示例','政治面貌':'中共党员（含预备党员）'}


def page(text):
    return {'source':PHOTO,'status':'ok','page':1,'lines':[{'text':t,'score':.99} for t in text]}


class PartyTests(unittest.TestCase):
    def test_non_party(self):
        r=party_advice(dict(FIELDS,政治面貌='共青团员'),[],[])
        self.assertEqual((r['tentative'],r['reason']),(0,'报名填写为非党员'))

    def test_no_photo(self):
        r=party_advice(FIELDS,[{'path':PHOTO.replace('.jpg','.pdf')}],[])
        self.assertEqual((r['tentative'],r['reason']),(0,'其他证明材料没有上传材料'))

    def test_member_and_probationary_quote(self):
        for role in ['中共党员','中共预备党员']:
            r=party_advice(FIELDS,[{'path':PHOTO}],[page(['姓名：张示例','政治面貌：'+role])])
            self.assertEqual(r['tentative'],5);self.assertIsNone(r['approved'])
            self.assertIn('政治面貌：'+role,r['reason']);self.assertIn('张示例',r['reason'])

    def test_wrong_owner_or_training(self):
        self.assertEqual(party_advice(FIELDS,[{'path':PHOTO}],[page(['姓名：李某','中共党员'])])['tentative'],5)
        for texts in [['姓名：张示例','入党积极分子培训合格'],['姓名：张示例','非中共党员']]:
            self.assertEqual(party_advice(FIELDS,[{'path':PHOTO}],[page(texts)])['tentative'],0)

    def test_unread_or_low_confidence(self):
        r=party_advice(FIELDS,[{'path':PHOTO}],[])
        self.assertEqual(r['tentative'],0);self.assertIn('尚未完成OCR',r['reason'])
        p=page(['姓名：张示例','中共党员']);p['lines'][0]['score']=.4
        self.assertEqual(party_advice(FIELDS,[{'path':PHOTO}],[p])['tentative'],5)

    def test_notice_keeps_excerpt_without_confirming_membership(self):
        r=party_advice(FIELDS,[{'path':PHOTO}],[page(['通知：党员转正大会','张示例同志宣读转正申请'])])
        self.assertEqual(r['tentative'],5)
        self.assertIn('张示例同志宣读转正申请',r['reason'])
        self.assertIn('尚不能据此确认',r['reason'])


if __name__=='__main__':unittest.main()
