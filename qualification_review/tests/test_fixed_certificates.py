"""固定证书快速通道最小测试：虚构OCR文本、完整/冲突/缺失及模型零调用。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fixed_certificates import route_pages
from desktop_workflow import evidence_for_person


def page(title='法律职业资格证书',page_id='D1-P1',doc_id='D1',extras=None):
    texts=[title,'姓名：张示例','证书编号：A202612345','发证机关：司法部','发证日期：2026年09月01日']
    texts+=extras or []
    return {'page_id':page_id,'doc_id':doc_id,'status':'ok','source':'synthetic.jpg',
            'lines':[{'index':n+1,'text':t,'score':.99,'box':[[0,0],[10,0],[10,10],[0,10]]} for n,t in enumerate(texts)]}


class FixedTests(unittest.TestCase):
    def test_legal_local(self):
        result=route_pages([page()],'张示例')
        self.assertEqual(result['local_count'],1);self.assertEqual(result['model_pages'],[])
        self.assertEqual(result['pages'][0]['recommendations'],{'S11':1})

    def test_accounting_types(self):
        for title,extra,score in [
            ('注册会计师全国统一考试全科合格证书',[],1),
            ('注册会计师全国统一考试专业阶段考试合格证书',[],None),
            ('会计专业技术资格证书',['级别：初级'],None),
            ('会计专业技术资格证书',['级别：中级'],None)]:
            result=route_pages([page(title,extras=extra)],'张示例')
            self.assertEqual(result['local_count'],1)
            self.assertEqual(result['pages'][0]['recommendations'].get('S11'),score)

    def test_diploma_and_mismatch(self):
        p=page('普通高等学校毕业证书',extras=['学校名称：示例大学','专业：软件工程','学历层次：大学本科','学习形式：全日制'])
        self.assertEqual(route_pages([p],'张示例')['local_count'],1)
        r=route_pages([p],'张示例',expected_fields={'最高学历':'硕士'})
        self.assertEqual(r['manual_count'],1);self.assertEqual(r['local_count'],0)

    def test_missing_or_unclear_falls_back(self):
        p=page();p['lines']=[x for x in p['lines'] if '发证日期' not in x['text']]
        self.assertEqual(route_pages([p],'张示例')['model_count'],1)
        p=page();p['lines'][1]['score']=.5
        self.assertEqual(route_pages([p],'张示例')['model_count'],1)
        p=page();p['lines'][4]['text']='发证日期：2026年02月30日'
        self.assertEqual(route_pages([p],'张示例')['model_count'],1)

    def test_wrong_owner_and_late_date_manual(self):
        self.assertEqual(route_pages([page()],'李示例')['manual_count'],1)
        p=page();p['lines'][4]['text']='发证日期：2026年11月01日'
        self.assertEqual(route_pages([p],'张示例')['manual_count'],1)

    def test_multipage_and_multiple_documents(self):
        p=page();back=page(page_id='D1-P2');back['status']='deferred'
        r=route_pages([p,back],'张示例')
        self.assertEqual(r['local_count'],0);self.assertEqual(r['model_count'],1)
        other=page(page_id='D2-P1',doc_id='D2');other['lines'][2]['text']='证书编号：B999999999'
        r=route_pages([p,other],'张示例')
        self.assertEqual(r['local_count'],0);self.assertEqual(r['manual_count'],2)

    def test_mixed_content_kept(self):
        for extra in ['该证书作废','另附实习证明','毕业证书']:
            self.assertEqual(route_pages([page(extras=[extra])],'张示例')['local_count'],0)

    def test_model_not_called_for_complete_certificate(self):
        person={'name':'张示例','pid':'virtual','fields':{'最高学历':'本科'},'folder':'.','selected_files':None,
                'base_qualification':{'Q12':'待复核'}}
        with patch('desktop_workflow.build_pages',return_value=([page()],[],[])),patch('evidence_model.extract') as model:
            result=evidence_for_person(person,{'ocr':True,'llm':True},Path('.'),Path('qualification_review/tests/no_cancel_marker'))
            model.assert_not_called();self.assertEqual(result['fixed']['local_count'],1)


if __name__=='__main__':unittest.main()
