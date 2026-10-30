"""手动接口小样本诊断：仅发送虚构材料，检查完整Schema和原文引用，最长等待30秒。"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evidence_model import extract

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    cfg=json.loads((root/'evidence_config.json').read_text(encoding='utf-8'))
    cfg.update(timeout_seconds=30,output_tokens=1200)
    result=extract('SYNTHETIC_TEST',[{'page_id':'D001-P001','lines':[
        {'index':1,'text':'虚构测试材料：张示例'},
        {'index':2,'text':'某示例大学 2026年10月 优秀学生干部'}]}],['S08'],cfg,
        root/'tests/_runs/model_probe')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    sys.exit(0 if result['pages'] else 1)
