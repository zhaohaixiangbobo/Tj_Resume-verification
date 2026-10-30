"""学籍凭证优先级、成绩照片存在规则及成绩跳过OCR的必要测试。"""
import sys
import unittest
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from education_evidence import education_advice,education_score_advice,grade_advice
from evidence_pipeline import build_pages


def page(title='教育部学籍在线验证报告',school='示例大学'):
    values=[title,'姓名：张示例','学校名称：'+school,'层次：本科','学习形式：普通全日制']
    return {'page_id':'P1','status':'ok','source':'example.jpg','lines':[{'index':i+1,'text':v,'score':.99} for i,v in enumerate(values)]}


class EducationTests(unittest.TestCase):
    def test_priority_and_fallback(self):
        fields={'姓名':'张示例','最高学历毕业院校':'示例大学','最高学历':'大学本科','最高学历学习形式':'全日制'}
        for pages in [[page()],[page('毕业证书')]]:
            r=education_advice(pages,fields)
            self.assertTrue(all(r[x]['matched'] for x in ('S01','S02','S03')))
        self.assertFalse(education_advice([page(school='其他学校'),page('毕业证书')],fields)['S01']['matched'])
        self.assertFalse(education_advice([page(),page('毕业证书','其他学校')],fields)['S01']['matched'])
        self.assertEqual(education_advice([],fields),{})

    def test_independent_fields_and_photo_reasons(self):
        fields={'姓名':'张示例','最高学历毕业院校':'不存在的测试学校','最高学历':'大学本科','最高学历学习形式':'全日制'}
        manifest=[{'path':'1.最高学历证明材料/a.jpg'}]
        for overseas in (False,True):
            for files in ([],manifest):
                results={code:education_score_advice({'code':code},fields,files,{'overseas':overseas},{}) for code in ('S01','S02','S03')}
                self.assertEqual(results['S01']['tentative'],20)
                self.assertIn('院校库无填写院校',results['S01']['reason'])
                self.assertNotIn('tentative',results['S02'])
                self.assertNotIn('tentative',results['S03'])
                for result in results.values():self.assertIn('有佐证照片' if files else '无佐证照片',result['reason'])
                if overseas:
                    for result in results.values():self.assertIn('国外高校待人工核验',result['reason'])
        diploma=page('毕业证书');diploma['lines']=diploma['lines'][:-1]
        checks=education_advice([diploma],dict(fields,最高学历毕业院校='示例大学'))
        self.assertTrue(checks['S01']['matched']);self.assertTrue(checks['S02']['matched'])
        self.assertFalse(checks['S03']['matched'])
        diploma['lines'][1]['text']='吴亚飞性别男，2002年12月23日生'
        checks=education_advice([diploma],dict(fields,姓名='吴亚飞',最高学历毕业院校='示例大学'))
        self.assertTrue(checks['S01']['matched'])

    def test_overseas_education_never_queued(self):
        root=Path(__file__).parent/'_runs'/('overseas_'+uuid.uuid4().hex)
        folder=root/'1.最高学历证明材料';folder.mkdir(parents=True)
        (folder/'photo.jpg').write_bytes(b'not decoded fixture')
        pages,jobs,files=build_pages(root,[{'code':'S01','route':'verify'}],root/'cache',8,False,education_mode='overseas')
        self.assertEqual(pages,[]);self.assertEqual(jobs,[])
        self.assertIn('境外',files[0]['reason'])

    def test_grade_exact_branches(self):
        field='在读期间有无补考、重修、不合格课程记录等'
        files=[{'path':'2.最高学历在校成绩单或证明材料/a.JPG'}]
        yes=grade_advice({field:'是'},files)
        self.assertEqual((yes['tentative'],yes['reason']),(0,'报名系统自填有重修'))
        have=grade_advice({field:'否'},files)
        self.assertEqual((have['tentative'],have['status'],have['reason']),(2,'待核验','有最高学历成绩单，待核验'))
        absent=grade_advice({field:'否'},[{'path':'其他目录/a.jpg'}])
        self.assertEqual((absent['tentative'],absent['reason']),(0,'无最高学历成绩单，待核验'))
        self.assertIsNone(grade_advice({field:''},files)['tentative'])

    def test_transcript_never_queued(self):
        root=Path(__file__).parent/'_runs'/('transcript_'+uuid.uuid4().hex)
        folder=root/'2.最高学历在校成绩单或证明材料';folder.mkdir(parents=True)
        (folder/'photo.JPG').write_bytes(b'not decoded fixture')
        pages,jobs,files=build_pages(root,[{'code':'S06','route':'verify'}],root/'cache',8,False)
        self.assertEqual(pages,[]);self.assertEqual(jobs,[])
        self.assertEqual(files[0]['status'],'skipped')


if __name__=='__main__':unittest.main()
