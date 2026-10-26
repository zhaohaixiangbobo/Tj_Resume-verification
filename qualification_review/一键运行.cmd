@echo off
chcp 65001 >nul
rem 使用指定Python解释器运行资格审查并在结束后保留窗口。
"D:\3-anaconda\envs\py312\python.exe" "%~dp0review.py" %*
if errorlevel 1 echo 运行失败，请查看上方错误提示。
pause
