"""毕业年限赋分窗口：招聘届别前一年8月1日至当年7月31日为当年应届。"""
import calendar
from datetime import date


def graduation_points(year, month, day=None, cohort=2027, start_year=2025):
    lo=date(year,month,day or 1)
    hi=date(year,month,day or calendar.monthrange(year,month)[1])
    current_start=date(cohort-1,8,1);current_end=date(cohort,7,31)
    if current_start<=lo and hi<=current_end:return 10
    if date(start_year,1,1)<=lo and hi<current_start:return 5
    return None
