"""凭证分流与模型原文约束的最小测试，全部使用虚构人员及材料。"""
import sys
import contextlib
import uuid
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evidence_routing import route_items, file_routes
from evidence_model import validate, batches, redact, extract, verified_facts
from evidence_pipeline import build_pages, render_report


@contextlib.contextmanager
def test_folder():
    # 普通目录继承工作区ACL；测试产物集中保留在tests/_runs。
    path=Path(__file__).parent/'_runs'/('evidence_'+uuid.uuid4().hex)
    path.mkdir(parents=True)
    yield path


def route(**fields):
    return {i['code']:i for i in route_items({'最高学历':'大学本科', **fields})}


class EvidenceTests(unittest.TestCase):
    def test_grade_polarity(self):
        field='在读期间有无补考、重修、不合格课程记录？'
        self.assertEqual(route(**{field:'是'})['S06']['score'],0)
        self.assertEqual(route(**{field:'否'})['S06']['route'],'verify')
        self.assertIsNone(route(**{field:''})['S06']['score'])

    def test_award_absence_and_conflict(self):
        base={'高等教育期间是否取得奖学金':'否'}
        self.assertEqual(route(**base)['S07']['route'],'skip')
        self.assertEqual(route(**base,奖学金='国家奖学金')['S07']['route'],'manual')
        self.assertEqual(route(**base,最高奖学金档次='国家')['S07']['route'],'manual')

    def test_shared_field_is_not_universal_negative(self):
        a=route(**{'其他职业资格证书，实习实践':'其他证书：无；实习：某公司两个月'})
        self.assertEqual(a['S11']['route'],'skip')
        self.assertEqual(a['S15']['route'],'verify')
        self.assertEqual(a['S14']['route'],'verify')
        b=route(**{'其他职业资格证书，实习实践':'无','学习经历':'担任班长'})
        self.assertEqual(b['S14']['route'],'manual')

    def test_english_conflict_and_undergrad(self):
        a=route(**{'英语等级':'无','其他职业资格证书，实习实践':'雅思7分'})
        self.assertEqual(a['S10']['route'],'manual')
        self.assertEqual(a['S12']['score'],0)
        self.assertEqual(a['S13']['route'],'manual')

    def test_unknown_file_kept(self):
        self.assertEqual(file_routes('照片123.jpg'),[])
        with test_folder() as t:
            folder=Path(t); (folder/'奖学金1.jpg').write_bytes(b'fixture')
            (folder/'照片.jpg').write_bytes(b'fixture2')
            items=list(route(**{'高等教育期间是否取得奖学金':'否'}).values())
            pages,jobs,files=build_pages(folder,items,folder/'cache',8,False)
            self.assertEqual(len(pages),1)
            self.assertEqual(len(jobs),0)
            self.assertEqual(sum(f['status']=='skipped' for f in files),1)

    def test_exact_citations_and_coverage(self):
        pages=[{'page_id':'D1-P1','lines':[{'index':1,'text':'张示例 荣获三好学生'}]}]
        data={'candidate_id':'C1','pages':[{'page_id':'D1-P1','document_type':'honor',
              'item_codes':['S08'],'fields':[{'record_id':'R1','name':'owner','value':'张示例','line_ids':[1]}],'issues':[]}]}
        validate(data,'C1',pages)
        with self.assertRaises(ValueError):validate(data,'C2',pages)
        data['pages'][0]['fields'][0]['value']='李示例'
        with self.assertRaises(ValueError):validate(data,'C1',pages)
        data['pages']=[]
        with self.assertRaises(ValueError):validate(data,'C1',pages)

    def test_budget_and_redaction(self):
        pages=[{'page_id':str(i),'text':'字'*100} for i in range(3)]
        packed=list(batches(pages,400))
        self.assertEqual(len(packed),3)
        self.assertEqual([p for b in packed for p in b],pages)
        self.assertNotIn('110101200001010011',redact('证件110101200001010011，电话13800000000'))

    def test_bad_fact_is_excluded_and_flagged(self):
        pages=[{'page_id':'D1','lines':[{'index':1,'text':'张示例 2026年10月'}]}]
        result={'candidate_id':'C1','pages':[{'page_id':'D1','document_type':'certificate','item_codes':['S08'],
            'fields':[{'record_id':'R1','name':'owner','value':'张示例','line_ids':[1]},
                      {'record_id':'R1','name':'date','value':'2026-10-01','line_ids':[1]}],'issues':[]}]}
        accepted,rejected=verified_facts(result,'C1',pages)
        self.assertEqual(len(accepted['pages'][0]['fields']),1)
        self.assertEqual(len(rejected),1)
        self.assertTrue(accepted['pages'][0]['issues'])
        self.assertEqual(len(result['pages'][0]['fields']),2)

    def test_html_escapes_ocr(self):
        with test_folder() as t:
            dest=Path(t)/'report.html'
            render_report(dest,{'persons':[{'name':'<script>alert(1)</script>','candidate_id':'C',
                'items':[],'files':[],'pages':[],'model':{}}]})
            result=dest.read_text(encoding='utf-8')
            self.assertNotIn('<script>',result)
            self.assertIn('&lt;script&gt;',result)

    def test_model_cache_and_truncation(self):
        cfg={'model':'fake','base_url':'http://example.invalid/v1','input_byte_budget':24000,
             'output_tokens':1000,'timeout_seconds':1}
        pages=[{'page_id':'D1','lines':[{'index':1,'text':'虚构测试'}]}]
        result={'candidate_id':'C1','pages':[{'page_id':'D1','document_type':'unknown',
                'item_codes':[],'fields':[],'issues':['材料不足']}]}
        import json
        session=MagicMock();session.__enter__.return_value=session
        response=session.post.return_value
        response.json.return_value={'model':'fake','choices':[{'finish_reason':'stop',
              'message':{'content':json.dumps(result)}}],'usage':{'completion_tokens':10}}
        with test_folder() as folder, patch('evidence_model.requests.Session',return_value=session):
            a=extract('C1',pages,['S08'],cfg,folder)
            b=extract('C1',pages,['S08'],cfg,folder)
            self.assertEqual(a['events'][0]['status'],'extracted')
            self.assertEqual(b['events'][0]['status'],'cached')
            self.assertEqual(session.post.call_count,1)
            response.json.return_value['choices'][0]['finish_reason']='length'
            c=extract('C2',pages,['S08'],cfg,folder)
            self.assertEqual(c['events'][0]['status'],'manual')
            self.assertEqual(c['pages'],[])


if __name__=='__main__':unittest.main()
