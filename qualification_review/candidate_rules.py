"""考生类别的明确映射及材料清单；境外认证截止日由配置统一控制。"""
import unicodedata

CATEGORIES = [
    '国内院校暂未毕业人员', '国内院校已毕业人员',
    '暂未取得教留服国(境)外学历认证书的留学归国人员',
    '已取得教留服国(境)外学历认证书的留学归国人员',
]


def candidate_category(raw):
    name=unicodedata.normalize('NFKC',str(raw or '')).strip()
    aliases={'国内暂未毕业':CATEGORIES[0], '国内已毕业':CATEGORIES[1]}
    name=aliases.get(name,name)
    index=CATEGORIES.index(name) if name in CATEGORIES else -1
    evidence=[
        '需学籍、预计毕业及学位材料；在毕业期限内取得学历学位的承诺，先给建议预审结论',
        '需毕业证、学位证及取得日期；另核验未落实工作单位',
        '需境外学位及取得日期；尚未认证列待复核，最迟2027-07-31补交认证材料',
        '需境外学位及留服认证书，核对认证对应学校、学历、学位与完成日期',
    ]
    return {'name':name,'domestic':index in (0,1),'overseas':index in (2,3),
            'certified':index==3,'graduated':index in (1,2,3),
            'evidence':evidence[index] if index>=0 else '考生类别未知，请按四类明确填写后核验'}
