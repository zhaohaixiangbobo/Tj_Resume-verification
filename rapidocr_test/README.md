# RapidOCR 本地图片测试版

用于查看资格审查图片的 OCR 效果。支持单张图片、文件夹递归扫描、原图/文字框切换、放大、整图旋转、逐行分数，以及 TXT、CSV、JSON 和标注图导出。仅识别图片文字；尚未接入 Qwen、表格结构恢复或资格判断。

## 1. 手动安装

本机检查时已有 onnxruntime、Pillow、OpenCV 和 tkinter，缺少 rapidocr。请由你在 PowerShell 执行以下命令；程序本身不会安装依赖。

```powershell
Set-Location -LiteralPath 'D:\8-烟草\2025开发工作\2027年度资格审查\rapidocr_test'
& 'D:\3-anaconda\envs\py312\python.exe' -m pip install -r requirements.txt
```

固定 rapidocr 3.4.1 是为了让接口、配置与模型文件保持一致；本版采用 PP-OCRv5 server 检测与识别模型，ONNX Runtime CPU 推理。server 是模型规格，在本机运行，无需搭建服务器。安装命令会按依赖情况安装或调整包版本。

## 2. 手动下载 4 个文件

将以下文件保留原名，全部放进本目录的 `models` 文件夹。打开链接后保存实际文件，避免保存为 HTML 网页。模型较大，下载速度取决于网络。

| 文件                                 | 官方下载链接                                                                                                                                   |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| ch_PP-OCRv5_det_server.onnx          | [下载检测模型](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/det/ch_PP-OCRv5_det_server.onnx)                |
| ch_PP-OCRv5_rec_server.onnx          | [下载识别模型](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/ch_PP-OCRv5_rec_server.onnx)                |
| ch_ppocr_mobile_v2.0_cls_mobile.onnx | [下载文字行方向模型](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx) |
| ppocrv5_dict.txt                     | [下载识别字典](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/paddle/PP-OCRv5/rec/ch_PP-OCRv5_rec_server/ppocrv5_dict.txt)  |

模型链接来自 [当前官方模型清单](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml)；清单中的 ONNX 模型版本为 v3.10.0。配置接口参考 [官方配置](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/config.yaml)。本次开发只查询了文档，没有代为下载上述文件。

另外，RapidOCR 每次识别都会实例化结果可视化组件，默认会把字体 `FZYTK.TTF` 下载到 `rapidocr/models` 下。本工具改用系统自带的中文字体（`C:\Windows\Fonts` 下的 simfang.ttf、simsun.ttc 或 msyh.ttc），因此不需要额外下载字体，也不会因为联网保护而报错。

## 3. 启动和测试

双击 `start.cmd`，或执行：

```powershell
& 'D:\3-anaconda\envs\py312\python.exe' .\app.py
```

1. 点击“选择文件夹”，选最初提供的人员文件夹（末尾为 `033X`），先测试其中 6 张图片。
2. 点击“开始识别”。首次需要加载本地模型，窗口底部显示阶段和逐图进度。建议先测试这一个人，CPU 速度与图片大小会影响耗时。
3. 左侧选择已完成的图片，中间查看原图或编号框，右侧查看对应编号的文字和分数。
4. 如整张图片横放，选择逆时针旋转 90 或 270 度后重跑。方向模型主要处理文字行，不能替代整页方向判断。
5. 通过“100% / 150% / 200%”和滚动条查看小字；切回原图可检查文字框遮挡的内容。
6. 点击“打开结果文件夹”。每次运行创建独立目录，保存到 `outputs/时间戳`，原始材料保持不变。

红色表示模型分数低于 0.90，仅用于提醒检查。高分也可能识别错误；这里的分数不是经业务样本验证的准确率。成绩单行列对应关系需人工对照。本版保留低分识别行，便于观察，但检测阶段仍可能漏字。

每张图保存：`text.txt`（纯文字）、`lines.csv`（Excel 可打开）、`result.json`（文字和坐标）、`marked.png`（编号框）。运行目录的 `summary.json` 记录成功、空结果和失败原因。坐标以 EXIF 方向校正和手动旋转后的图像为准。

停止按钮在当前图片完成后生效。模型缺失时明确报错；程序有网络连接保护，不会自动下载或向远程服务发送材料。

## 验证范围

已准备标准库 unittest，用模拟 OCR 输出验证中文路径、空结果、坐标一致性、导出和离线保护。执行：

```powershell
& 'D:\3-anaconda\envs\py312\python.exe' -m unittest discover -s tests -v
```

真实模型加载、识别质量和耗时需要你安装及下载完成后运行确认。未执行全量人员处理、压力测试和长时间测试；本阶段无需运行这些测试。
