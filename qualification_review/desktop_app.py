"""简洁桌面入口：选择考生、后台识别材料、生成个人与岗位联动Excel。"""
import json
import os
import queue
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from review import load_table, text
from evidence_pipeline import ROOT, save


class ReviewApp:
    def __init__(self, root):
        self.root=root;root.title('资格审查 · Excel生成');root.geometry('1040x720');root.minsize(900,620)
        self.events=queue.Queue();self.process=None;self.running=False;self.report_dir=None
        self.records={};self.selected=set();self.controls=[];self.rendering=False
        cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
        self.input=tk.StringVar(value=str((ROOT.parent/cfg['personnel_file']).resolve()))
        self.materials=tk.StringVar(value=str(Path(self.input.get()).parent))
        self.output=tk.StringVar(value=str(ROOT/'outputs'))
        self.ocr=tk.BooleanVar(value=True);self.llm=tk.BooleanVar(value=False)
        self.search=tk.StringVar();self.count=tk.StringVar();self.status=tk.StringVar(value='请选择考生')
        self.show_log=tk.BooleanVar(value=True)
        self.model_config=json.loads((ROOT/'evidence_config.json').read_text(encoding='utf-8'))
        style=ttk.Style(root);style.configure('Treeview',rowheight=30,font=('微软雅黑',10))
        style.configure('Treeview.Heading',font=('微软雅黑',10,'bold'))
        style.configure('Title.TLabel',font=('微软雅黑',19,'bold'))
        style.configure('Hint.TLabel',foreground='#667085',font=('微软雅黑',9))
        main=ttk.Frame(root,padding=22);main.pack(fill='both',expand=True)
        ttk.Label(main,text='资格审查与赋分',style='Title.TLabel').pack(anchor='w')
        ttk.Label(main,text='选择材料 → 选择考生 → 生成个人赋分表与岗位汇总',style='Hint.TLabel').pack(anchor='w',pady=(4,16))
        paths=ttk.Frame(main);paths.pack(fill='x');paths.columnconfigure(1,weight=1)
        for row,(label,var,kind) in enumerate([('报名表',self.input,'file'),('材料目录',self.materials,'dir'),('输出目录',self.output,'dir')]):
            ttk.Label(paths,text=label,width=10).grid(row=row,column=0,sticky='w',pady=4)
            entry=ttk.Entry(paths,textvariable=var);entry.grid(row=row,column=1,sticky='ew',padx=8,pady=4)
            button=ttk.Button(paths,text='选择…',command=lambda v=var,k=kind:self.choose(v,k));button.grid(row=row,column=2)
            self.controls.extend([entry,button])
            if kind=='file':entry.bind('<Return>',lambda e:self.load_people())
        ttk.Label(main,text='材料目录下按身份证号存放考生文件夹。报名表自动读取；手动粘贴路径后按回车。',style='Hint.TLabel').pack(anchor='w',pady=(4,12))
        toolbar=ttk.Frame(main);toolbar.pack(fill='x',pady=(0,8))
        ttk.Label(toolbar,text='搜索考生').pack(side='left')
        search=ttk.Entry(toolbar,textvariable=self.search,width=26);search.pack(side='left',padx=8);self.controls.append(search)
        for title,command in [('全选当前列表',self.select_all),('清空选择',self.clear_selection)]:
            button=ttk.Button(toolbar,text=title,command=command);button.pack(side='left',padx=3);self.controls.append(button)
        ttk.Label(toolbar,textvariable=self.count,style='Hint.TLabel').pack(side='right')
        table=ttk.Frame(main);table.pack(fill='both',expand=True)
        self.people=ttk.Treeview(table,columns=('name','ident','political','degree','job'),show='headings',selectmode='extended',height=9)
        for col,label,width in [('name','姓名',90),('ident','身份证号',190),('political','政治面貌',170),('degree','最高学历',130),('job','报考岗位',240)]:
            self.people.heading(col,text=label);self.people.column(col,width=width,minwidth=80)
        bar=ttk.Scrollbar(table,orient='vertical',command=self.people.yview);self.people.configure(yscrollcommand=bar.set)
        self.people.pack(side='left',fill='both',expand=True);bar.pack(side='right',fill='y')
        self.people.bind('<<TreeviewSelect>>',self.selection_changed)
        self.people.bind('<Button-1>',lambda event:'break' if self.running else None)
        self.people.bind('<Key>',lambda event:'break' if self.running else None)
        ttk.Label(main,text='Ctrl / Shift 多选；支持搜索姓名、身份证号、政治面貌、学历或岗位。',style='Hint.TLabel').pack(anchor='w',pady=(5,10))
        options=ttk.Frame(main);options.pack(fill='x')
        for title,var in [('本地OCR',self.ocr),('内网大模型（可选）',self.llm)]:
            box=ttk.Checkbutton(options,text=title,variable=var,command=self.options_changed);box.pack(side='left',padx=(0,22));self.controls.append(box)
        ttk.Label(options,text='默认仅用本地OCR；固定证书无需大模型。',style='Hint.TLabel').pack(side='left')
        actions=ttk.Frame(main);actions.pack(fill='x',pady=(14,8))
        self.start=ttk.Button(actions,text='开始处理选中考生',command=self.start_run);self.start.pack(side='left');self.controls.append(self.start)
        self.stop=ttk.Button(actions,text='停止处理',command=self.cancel,state='disabled');self.stop.pack(side='left',padx=8)
        ttk.Button(actions,text='打开输出目录',command=self.open_output).pack(side='right')
        refresh=ttk.Button(actions,text='刷新岗位汇总',command=self.refresh_summary)
        refresh.pack(side='right',padx=8);self.controls.append(refresh)
        self.progress=ttk.Progressbar(main,mode='determinate',maximum=100);self.progress.pack(fill='x')
        status=ttk.Frame(main);status.pack(fill='x',pady=(6,0))
        ttk.Label(status,textvariable=self.status).pack(side='left')
        ttk.Checkbutton(status,text='运行日志',variable=self.show_log,command=self.toggle_log).pack(side='right')
        # 底部日志默认可见，滚动条便于回看识别进度和错误。
        self.log_panel=ttk.Frame(main)
        self.log=tk.Text(self.log_panel,height=6,wrap='word',state='disabled',font=('Consolas',9))
        log_scroll=ttk.Scrollbar(self.log_panel,orient='vertical',command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side='left',fill='both',expand=True)
        log_scroll.pack(side='right',fill='y')
        self.toggle_log()
        ttk.Label(main,text='个人Excel修改得分列后保存并关闭，点击“刷新岗位汇总”；仅同步分数，其他内容保留。',style='Hint.TLabel').pack(anchor='w',pady=(10,0))
        self.search.trace_add('write',lambda *_:self.render_people())
        root.after(150,self.poll);root.protocol('WM_DELETE_WINDOW',self.close)
        self.load_people()

    def choose(self,var,kind):
        if self.running:return
        path=filedialog.askopenfilename(filetypes=[('报名Excel','*.xlsx')]) if kind=='file' else filedialog.askdirectory()
        if not path:return
        var.set(path)
        if var is self.input:self.materials.set(str(Path(path).parent));self.load_people()

    def load_people(self):
        if self.running:return
        try:
            cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
            _,rows,_=load_table(Path(self.input.get()),cfg['personnel_sheet'])
            records={}
            for _,p in rows:
                ident=text(p.get('身份证号码')).upper()
                if not ident or ident in records:raise ValueError('报名表中有缺失或重复身份证号，请先核对')
                records[ident]=p
            self.records=records;self.selected.clear();self.loaded_input=Path(self.input.get()).resolve()
            self.render_people();self.status.set('已读取报名表，请选择需要处理的考生')
        except Exception as exc:
            self.records={};self.selected.clear();self.loaded_input=None;self.render_people()
            self.status.set('报名表读取失败');messagebox.showerror('读取失败',str(exc))

    def render_people(self):
        if self.running:return
        self.rendering=True;self.people.delete(*self.people.get_children());query=self.search.get().strip().lower()
        for ident,p in self.records.items():
            # 直接展示报名填报内容，保留正式党员、预备党员等原始区别。
            values=(text(p.get('姓名')),ident,text(p.get('政治面貌')),text(p.get('最高学历')),
                    text(p.get('岗位编码'))+' '+text(p.get('岗位名称')))
            if query and query not in (' '.join(values)+' '+text(p.get('考生类别'))).lower():continue
            self.people.insert('','end',iid=ident,values=values)
            if ident in self.selected:self.people.selection_add(ident)
        self.rendering=False;self.update_count()

    def update_count(self):self.count.set(f'共 {len(self.records)} 人 · 已选 {len(self.selected)} 人')

    def selection_changed(self,event=None):
        if self.rendering or self.running:return
        self.selected.difference_update(self.people.get_children());self.selected.update(self.people.selection());self.update_count()

    def select_all(self):
        if self.running:return
        self.selected.update(self.people.get_children());self.people.selection_set(self.people.get_children());self.update_count()

    def clear_selection(self):
        if self.running:return
        self.selected.clear();self.people.selection_remove(self.people.selection());self.update_count()

    def options_changed(self):
        if self.llm.get():self.ocr.set(True)

    def build_options(self):
        if not self.selected:raise ValueError('请选择考生；整批处理可点击“全选当前列表”')
        if Path(self.input.get()).resolve()!=self.loaded_input:raise ValueError('报名表路径已改变，请按回车重新读取')
        if not Path(self.materials.get()).is_dir():raise ValueError('材料目录不存在')
        if not self.output.get().strip():raise ValueError('请选择输出目录')
        if self.llm.get() and not self.ocr.get():raise ValueError('大模型处理需要开启OCR')
        # 统计材料实际页数，覆盖所选人员全部材料，取消旧版8页限制。
        pages=0;unknown=0
        for ident in sorted(self.selected):
            for path in (Path(self.materials.get())/ident).rglob('*'):
                if not path.is_file():continue
                if path.suffix.lower() in {'.jpg','.jpeg','.png','.bmp','.webp','.tif','.tiff'}:pages+=1
                elif path.suffix.lower()=='.pdf':
                    try:
                        import fitz
                        with fitz.open(path) as pdf:pages+=len(pdf)
                    except Exception:pages+=5;unknown+=1
        return dict(input=self.input.get(),materials=self.materials.get(),selected_ids=sorted(self.selected),
                    ocr=self.ocr.get(),llm=self.llm.get(),max_pages=max(1,pages),
                    model_config=dict(self.model_config),export_review=False),pages,unknown

    def set_running(self,value):
        self.running=value
        for control in self.controls:control.state(['disabled' if value else '!disabled'])
        self.stop.state(['!disabled' if value else 'disabled'])

    def start_run(self):
        if self.running:return
        try:
            options,pages,unknown=self.build_options()
            minutes=(pages*10 if options['ocr'] else 0)/60+(len(self.selected)*90 if options['llm'] else 0)/60
            if minutes>10:
                note=f'按{pages}页材料粗估约{minutes*.5:.0f}～{minutes*1.5:.0f}分钟；主要耗时为OCR，缓存、图片密度和模型排队会影响速度。逐人逐页显示进度。'
                if unknown:note+=f'其中{unknown}个PDF暂按5页估算。'
                if minutes>30:
                    if not messagebox.askyesno('预计耗时较长，是否现在开始？',note):return
                else:messagebox.showinfo('处理时间预估',note)
            stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f');folder=Path(self.output.get()).resolve()/('桌面批次_'+stamp)
            self.cancel_path=ROOT/'cache/desktop'/f'cancel_{stamp}'
            options.update(output=str(folder),cancel_file=str(self.cancel_path.resolve()))
            request=ROOT/'cache/desktop'/f'request_{stamp}.json';save(request,options)
            process=subprocess.Popen([sys.executable,str(ROOT/'desktop_workflow.py'),'--request',str(request)],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
                env=dict(os.environ,PYTHONIOENCODING='utf-8'),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.process=process;self.set_running(True);self.progress['value']=0;self.status.set('开始核验资格并处理材料…')
            def collect():
                for line in process.stdout:self.events.put(('log',line))
                self.events.put(('done',(process.wait(),folder)))
            threading.Thread(target=collect,daemon=True).start()
        except Exception as exc:
            self.set_running(False);self.status.set('处理未启动');messagebox.showerror('无法开始',str(exc))

    def append_log(self,value):
        self.log.configure(state='normal');self.log.insert('end',value)
        if int(self.log.index('end-1c').split('.')[0])>1500:self.log.delete('1.0','200.0')
        self.log.see('end');self.log.configure(state='disabled')

    def cancel(self):
        if self.running:
            self.cancel_path.parent.mkdir(parents=True,exist_ok=True);self.cancel_path.write_text('cancel',encoding='utf-8')
            self.stop.state(['disabled']);self.status.set('正在停止：当前识别完成后保留已完成结果')

    def poll(self):
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='log':
                self.append_log(value);person=re.search(r'\[2/4\]\s*(\d+)/(\d+)',value)
                if person:
                    done,total=map(int,person.groups());self.progress['value']=100*(done-1)/max(1,total);self.status.set(f'正在处理第 {done}/{total} 位考生')
                elif '[OCR]' in value:self.status.set('识别材料：'+value.split('[OCR]',1)[1].strip())
                elif '[3/4]' in value:self.status.set('正在生成个人Excel和岗位汇总…')
            else:
                code,folder=value;self.set_running(False);self.process=None
                if code==0:
                    self.report_dir=folder;stopped=self.cancel_path.exists()
                    if not stopped:self.progress['value']=100
                    self.status.set('已停止，已完成结果保留在输出目录' if stopped else '处理完成，可打开输出目录查看Excel')
                else:
                    self.status.set('处理失败，请查看运行日志');self.show_log.set(True);self.toggle_log()
                    messagebox.showerror('处理失败','请查看运行日志；已有识别缓存会保留。')
        self.root.after(150,self.poll)

    def toggle_log(self):
        if self.show_log.get():self.log_panel.pack(fill='x',pady=(8,0))
        else:self.log_panel.pack_forget()

    def open_output(self):
        path=self.report_dir or Path(self.output.get())
        if path.is_dir():os.startfile(path)
        else:messagebox.showinfo('尚无输出','处理完成后即可打开结果目录。')

    def refresh_summary(self):
        if self.running:return
        folder=filedialog.askdirectory(title='选择要刷新分数的批次目录（请先保存并关闭Excel）',initialdir=str(self.report_dir or self.output.get()))
        if not folder:return
        try:
            from refresh_summary import refresh_summary
            results=refresh_summary(folder)
            self.report_dir=Path(folder)
            messagebox.showinfo('刷新完成',f'已刷新{len(results)}个岗位、{sum(len(r["scores"]) for r in results)}人的分数。\n其他内容未同步；原汇总已备份到内部记录。')
        except Exception as exc:
            messagebox.showerror('刷新未完成',str(exc)+'\n请先保存并关闭Excel后重试；已处理岗位可重复刷新。')

    def close(self):
        if self.running:self.cancel();messagebox.showinfo('正在停止','请等待当前步骤结束后再关闭窗口。');return
        self.root.destroy()


if __name__=='__main__':
    root=tk.Tk();ReviewApp(root);root.mainloop()
