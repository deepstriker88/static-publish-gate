"""Small local-only desktop shell. Product adapters own all inspection logic."""
from dataclasses import dataclass
import json
import html
import os
from pathlib import Path
import queue
import threading


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str
    optional: bool = False
    choices: tuple = ()
    default: str = ""
    filters: tuple = (("All files", "*"),)
    maximum: int = 1


@dataclass(frozen=True)
class Result:
    state: str
    title: str
    description: str
    metrics: tuple
    details: tuple
    data: dict
    snapshot: dict = None
    protected_root: str = None


def write_new_bytes(path, payload):
    """Never overwrite an input, existing report, reviewed pin, or symlink."""
    if not isinstance(payload, bytes) or len(payload) > 12 * 1024 * 1024:
        raise ValueError("Report exceeds the export limit")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(payload)


def write_new_json(path, data):
    payload = (json.dumps(data, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("ascii")
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError("Report exceeds the export limit")
    write_new_bytes(path, payload)


def render_report(adapter, result, *, synthetic=False):
    """Script-free, escaped local report. Never an approval or security certificate."""
    if result.state not in ("pass","review","uninspected"):
        raise ValueError("invalid report state")
    e=lambda x:html.escape(str(x),quote=True)
    metrics="".join(f"<div><span>{e(k)}</span><strong>{e(v)}</strong></div>" for k,v in result.metrics)
    findings="".join("<li>"+e(line)+"</li>" for line in result.details[:250])
    if len(result.details)>250:
        findings+="<li>Additional findings are included in the structured data below.</li>"
    raw=json.dumps(result.data,ensure_ascii=True,sort_keys=True,indent=2)
    if len(raw)>8*1024*1024:
        raise ValueError("structured report exceeds export limit")
    label="SYNTHETIC EXAMPLE — NOT A USER INSPECTION" if synthetic else "LOCAL INSPECTION REPORT"
    css="""*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#202530;font:16px/1.55 system-ui,sans-serif}main{width:min(900px,calc(100% - 32px));margin:32px auto}header{color:#354c86;font-size:13px;font-weight:700;letter-spacing:.08em}h1{font-size:clamp(27px,5vw,40px);line-height:1.1;letter-spacing:-.035em;margin:12px 0}p,span{color:#525b69}.card,details{padding:20px;border:1px solid #d7dce3;background:#ffffff;border-radius:14px;margin:14px 0}.status{font-size:22px;font-weight:700;color:#895211}.pass{color:#23664d}.uninspected{color:#a32b36}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:15px 0}.metrics>div{border:1px solid #d7dce3;border-radius:9px;padding:12px;overflow-wrap:anywhere}.metrics span{display:block;font-size:13px}.metrics strong{font-size:23px}li{padding:8px 0;border-bottom:1px solid #d7dce3;overflow-wrap:anywhere}summary{cursor:pointer;font-weight:700;min-height:44px;padding:10px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;background:#f5f6f8;padding:12px;border-radius:8px}summary:focus-visible{outline:3px solid #354c86;outline-offset:3px}@media(max-width:420px){.card,details{padding:13px}.metrics>div{padding:8px}.metrics strong{font-size:19px}}"""
    css += "@media(prefers-color-scheme:dark){body{background:#121720;color:#f1f4f8}header{color:#a7c9ff}p,span{color:#b7c4d5}.card,details{background:#1c2531;border-color:#394657}.metrics>div,li{border-color:#394657}.status{color:#ffd18b}.pass{color:#8bd5b4}.uninspected{color:#ffb3b9}pre{background:#121720}summary:focus-visible{outline-color:#a7c9ff}}"
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta name='referrer' content='no-referrer'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'\">"
            f"<title>{e(adapter.TITLE)} — local report</title><style>{css}</style></head><body><main>"
            f"<header>EZTOOLGO / {e(label)}</header><h1>{e(adapter.TITLE)}</h1>"
            f"<section class='card'><div class='status {e(result.state)}'>{e(result.title)}</div>"
            f"<p>{e(result.description)}</p><div class='metrics'>{metrics}</div>"
            f"<p>{e(adapter.LIMIT)}</p></section><section class='card'><h2>Selected findings</h2><ul>{findings}</ul></section>"
            f"<details><summary>Structured JSON report</summary><pre>{e(raw)}</pre></details>"
            "<p>Review diagnostic metadata before sharing. This report is not a signed attestation.</p></main></body></html>").encode("utf-8")



def launch(adapter, *, root=None, run_loop=True):
    # No optional GUI imports when the package is used as a CLI.
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter.font import nametofont

    class App:
        def __init__(self, window):
            self.root = window
            self.adapter = adapter
            self.result = None
            self.result_mode = None
            self.busy = False
            self.messages = queue.Queue(maxsize=1)
            self.values = {}
            self.variables = {}
            self.controls = []
            self.path_labels = {}
            self.field_widgets = {}
            self.closed = False
            self.bg = "#f6f7f9"
            self.panel = "#ffffff"
            self.fg = "#182230"
            self.muted = "#4b596c"
            self.mint = "#2355a6"
            self.dark = False
            self.root.title(adapter.TITLE + " · EZTOOLGO")
            self.root.configure(bg=self.bg)
            self.root.geometry("1000x620")
            self.root.minsize(760, 550)
            self.root.protocol("WM_DELETE_WINDOW", self.close)
            default = nametofont("TkDefaultFont")
            default.configure(size=11)
            style = ttk.Style(self.root)
            style.theme_use("clam")
            self.style=style
            style.configure(".", font=default, background=self.bg, foreground=self.fg)
            style.configure("TFrame", background=self.bg)
            style.configure("Panel.TFrame", background=self.panel)
            style.configure("TLabel", background=self.bg, foreground=self.fg)
            style.configure("Panel.TLabel", background=self.panel, foreground=self.fg)
            style.configure("Muted.TLabel", background=self.bg, foreground=self.muted)
            style.configure("PanelMuted.TLabel", background=self.panel, foreground=self.muted)
            style.configure("Eyebrow.TLabel", background=self.bg, foreground=self.mint, font=(default.actual("family"), 10, "bold"))
            style.configure("Title.TLabel", font=(default.actual("family"), 22, "bold"))
            style.configure("Section.TLabel", background=self.panel, font=(default.actual("family"), 15, "bold"))
            style.configure("Result.TLabel", background=self.panel, foreground=self.mint, font=(default.actual("family"), 19, "bold"))
            style.configure("Metric.TLabel", background=self.panel, foreground=self.fg, font=(default.actual("family"), 18, "bold"))
            style.configure("TButton", padding=(10, 5), background="#e9edf4", foreground=self.fg, borderwidth=1)
            style.map("TButton", background=[("disabled", "#e3e6ea"), ("active", "#dbe2ef")], foreground=[("disabled", "#697280")])
            style.configure("Primary.TButton", background=self.mint, foreground="#ffffff", font=(default.actual("family"), 11, "bold"))
            style.map("Primary.TButton", background=[("disabled", "#d7dce3"), ("active", "#173e80")], foreground=[("disabled", "#697280")])
            style.configure("TEntry", fieldbackground="#ffffff", foreground=self.fg, insertcolor=self.fg, padding=6)
            style.configure("TCombobox", fieldbackground="#ffffff", foreground=self.fg, padding=5)
            style.map("TCombobox", fieldbackground=[("readonly", "#ffffff")], foreground=[("readonly", self.fg)])
            outer = ttk.Frame(self.root, padding=12)
            outer.pack(fill="both", expand=True)
            ttk.Label(outer, text=adapter.TITLE, style="Title.TLabel").pack(anchor="w", pady=(4, 1))
            self.lead = ttk.Label(outer, text=adapter.LEAD, style="Muted.TLabel", wraplength=900)
            self.lead.pack(anchor="w", pady=(0, 6))
            self.body = ttk.Frame(outer)
            self.body.pack(fill="both", expand=True)
            self.body.columnconfigure(0, weight=1, uniform="panel")
            self.body.columnconfigure(1, weight=1, uniform="panel")
            self.body.rowconfigure(0, weight=1)
            self.inputs = ttk.Frame(self.body, style="Panel.TFrame", padding=12)
            self.inputs.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
            self.inputs.columnconfigure(1, weight=1)
            ttk.Label(self.inputs, text="Inputs", style="Section.TLabel").grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,5))
            row = 1
            for field in adapter.FIELDS:
                existing=set(self.inputs.winfo_children())
                self.make_field(field, row)
                self.field_widgets[field.key]=[w for w in self.inputs.winfo_children() if w not in existing]
                row += 1
            actions = ttk.Frame(self.inputs, style="Panel.TFrame")
            actions.grid(row=row,column=0,columnspan=2,sticky="ew",pady=(4,0))
            self.run_button = ttk.Button(actions, text="Run check", style="Primary.TButton", command=self.run_check)
            self.run_button.pack(side="left", fill="x", expand=True)
            self.demo_button = ttk.Button(actions, text="Try example", command=self.run_demo)
            self.demo_button.pack(side="left", padx=(7,0), fill="x", expand=True)
            self.controls += [self.run_button, self.demo_button]
            self.results = ttk.Frame(self.body, style="Panel.TFrame", padding=12)
            self.results.grid(row=0, column=1, sticky="nsew", padx=(6,0))
            ttk.Label(self.results, text="Result", style="Section.TLabel").pack(anchor="w",pady=(0,8))
            self.headline = ttk.Label(self.results, text="Ready", style="Result.TLabel", wraplength=400)
            self.headline.pack(anchor="w")
            self.description = ttk.Label(self.results, text="Choose your inputs or run the built-in example.", style="PanelMuted.TLabel", wraplength=400)
            self.description.pack(anchor="w",pady=(4,8))
            self.metric_frame = ttk.Frame(self.results, style="Panel.TFrame")
            self.metric_frame.pack(fill="x")
            self.metrics = []
            for i in range(3):
                self.metric_frame.columnconfigure(i, weight=1, uniform="metric")
                box = ttk.Frame(self.metric_frame, style="Panel.TFrame", padding=(0,3,5,3))
                box.grid(row=0,column=i,sticky="nsew")
                label = ttk.Label(box,text="—",style="PanelMuted.TLabel",wraplength=100)
                label.pack(anchor="w")
                value = ttk.Label(box,text="—",style="Metric.TLabel")
                value.pack(anchor="w")
                self.metrics.append((label,value))
            self.detail = ttk.Label(self.results,text=adapter.LIMIT,style="PanelMuted.TLabel",wraplength=400,justify="left")

            buttons=ttk.Frame(self.results,style="Panel.TFrame")
            buttons.pack(side="bottom",fill="x")
            self.details_button=ttk.Button(buttons,text="View report",command=self.show_report,state="disabled")
            self.details_button.pack(side="left",fill="x",expand=True)
            self.save_button=ttk.Button(buttons,text="Save report",command=self.save_report,state="disabled")
            self.save_button.pack(side="left",padx=(7,0),fill="x",expand=True)
            self.extra_button=ttk.Button(self.results,text="Save snapshot for review",command=self.save_snapshot,state="disabled")
            self.extra_button.pack(side="bottom",fill="x",pady=(0,5))
            self.extra_button.pack_forget()
            self.detail.pack(anchor="w",pady=(7,5),fill="x")
            footer=ttk.Frame(outer)
            footer.pack(fill="x",side="bottom",before=self.body,pady=(4,0))
            self.status=ttk.Label(footer,text="Local only · No uploads",style="Muted.TLabel")
            self.status.pack(side="left")
            self.clear_button=ttk.Button(footer,text="Clear",command=self.clear)
            self.clear_button.pack(side="right")
            ttk.Button(footer,text="View more",command=self.more).pack(side="right",padx=(0,6))
            self.theme_button=ttk.Button(footer,text="Dark mode",command=self.toggle_theme)
            self.theme_button.pack(side="right",padx=(0,6))
            self.root.bind("<Configure>",self.resize,add="+")
            self.root.bind("<Escape>",lambda e: None)
            self.root.bind("<Control-Return>",self.keyboard_run)
            if self.root.tk.call("tk","windowingsystem")=="aqua":self.root.bind("<Command-Return>",self.keyboard_run)
            self.refresh_run_state()
            self.poll_id=self.root.after(50,self.poll)

        def toggle_theme(self):
            self.dark=not self.dark
            self.bg,self.panel,self.fg,self.muted,self.mint = (("#121720","#1c2531","#f1f4f8","#b7c4d5","#a7c9ff") if self.dark else ("#f6f7f9","#ffffff","#182230","#4b596c","#2355a6"))
            style=self.style
            self.root.configure(bg=self.bg)
            style.configure(".",background=self.bg,foreground=self.fg)
            for key in ("TFrame","TLabel","Title.TLabel"):style.configure(key,background=self.bg,foreground=self.fg)
            for key in ("Panel.TFrame","Panel.TLabel","Section.TLabel","Metric.TLabel"):style.configure(key,background=self.panel,foreground=self.fg)
            style.configure("Muted.TLabel",background=self.bg,foreground=self.muted)
            style.configure("PanelMuted.TLabel",background=self.panel,foreground=self.muted)
            style.configure("Eyebrow.TLabel",background=self.bg,foreground=self.mint)
            style.configure("Result.TLabel",background=self.panel,foreground=self.mint)
            soft="#303d50" if self.dark else "#e9edf4"
            style.configure("TButton",background=soft,foreground=self.fg)
            style.map("TButton",background=[("active","#394657" if self.dark else "#dce4ef")],foreground=[("disabled",self.muted)])
            style.configure("Primary.TButton",background=self.mint,foreground="#11233c" if self.dark else "#ffffff")
            style.map("Primary.TButton",background=[("disabled",soft),("active","#d0e2ff" if self.dark else "#173e80")],foreground=[("disabled",self.muted),("!disabled","#11233c" if self.dark else "#ffffff")])
            style.configure("TEntry",fieldbackground=self.panel,foreground=self.fg,insertcolor=self.fg)
            style.configure("TCombobox",fieldbackground=self.panel,foreground=self.fg)
            style.map("TCombobox",fieldbackground=[("readonly",self.panel)],foreground=[("readonly",self.fg)])
            self.theme_button.configure(text="Light mode" if self.dark else "Dark mode")
            if self.result is not None:
                self.headline.configure(foreground=self.result_color(self.result.state))
            else:self.headline.configure(foreground=self.mint)

        def result_color(self,state):
            return ({"pass":"#8bd5b4","review":"#ffd18b","uninspected":"#ffb3b9"} if self.dark else {"pass":"#23664d","review":"#895211","uninspected":"#a32b36"})[state]

        def resize(self,event):
            if event.widget is not self.root: return
            w=max(240,(self.root.winfo_width()-98)//2)
            self.lead.configure(wraplength=max(300,self.root.winfo_width()-50))
            for widget in (self.headline,self.description,self.detail):
                widget.configure(wraplength=w)

        def make_field(self, field, row):
            label=field.label+(" (optional)" if field.optional and field.key not in getattr(self.adapter,"CONDITIONAL_FIELDS",()) else "")
            ttk.Label(self.inputs,text=label,style="PanelMuted.TLabel",wraplength=105).grid(row=row,column=0,sticky="w",pady=2,padx=(0,8))
            if field.kind in ("file","files","directory"):
                self.values[field.key]=() if field.kind=="files" else ""
                holder=ttk.Frame(self.inputs,style="Panel.TFrame")
                holder.grid(row=row,column=1,sticky="ew",pady=2)
                holder.columnconfigure(1,weight=1)
                b=ttk.Button(holder,text="Choose",width=7,command=lambda f=field:self.pick(f))
                b.grid(row=0,column=0,sticky="w")
                s=ttk.Label(holder,text="None",style="PanelMuted.TLabel",width=8)
                s.grid(row=0,column=1,sticky="ew",padx=(6,0))
                self.path_labels[field.key]=s
                self.controls.append(b)
                if field.optional:
                    remove=ttk.Button(holder,text="Clear",width=5,command=lambda f=field:self.set_value(f.key,""))
                    remove.grid(row=0,column=2,sticky="e",padx=(4,0))
                    self.controls.append(remove)
            else:
                v=tk.StringVar(value=field.default)
                self.variables[field.key]=v
                if field.kind=="choice":
                    w=ttk.Combobox(self.inputs,textvariable=v,values=field.choices,state="readonly",width=15)
                    w._idle_state="readonly"
                else:
                    w=ttk.Entry(self.inputs,textvariable=v,width=15)
                w.grid(row=row,column=1,sticky="ew",pady=2)
                self.controls.append(w)
                v.trace_add("write",lambda *_:self.invalidate())

        def pick(self,field):
            if self.busy:return
            kwargs={"parent":self.root,"title":field.label}
            if field.kind=="files":
                p=filedialog.askopenfilenames(filetypes=field.filters,**kwargs)
                if not p:return
                if len(p)>field.maximum:
                    messagebox.showerror("Input limit",f"Choose at most {field.maximum} files.",parent=self.root)
                    return
                p=tuple(p)
            elif field.kind=="directory":
                p=filedialog.askdirectory(mustexist=True,**kwargs)
            else:
                p=filedialog.askopenfilename(filetypes=field.filters,**kwargs)
            if not p:return
            self.set_value(field.key,p)

        def set_value(self,key,value):
            if self.busy:raise RuntimeError("Inspection in progress")
            if key in self.variables:
                self.variables[key].set(value)
                return
            self.values[key]=value
            label=(f"{len(value)} file"+("s" if len(value)!=1 else "") if isinstance(value,(tuple,list)) else "Selected") if value else "None"
            self.path_labels[key].configure(text=label)
            self.invalidate()

        def invalidate(self):
            if self.busy:return
            if self.result is not None:
                self.result=None
                self.reset_result("Inputs changed","Run a new inspection before exporting a report.")
            self.refresh_run_state(update_status=True)

        def reset_result(self,title,desc):
            self.headline.configure(text=title,foreground=self.mint)
            self.description.configure(text=desc)
            for label,value in self.metrics:
                label.configure(text="—");value.configure(text="—")
            self.detail.configure(text=self.adapter.LIMIT)
            self.details_button.configure(state="disabled")
            self.save_button.configure(state="disabled",text="Save report")
            self.extra_button.pack_forget()

        def input_values(self):
            return {**self.values,**{k:v.get() for k,v in self.variables.items()}}

        def missing_fields(self,values):
            conditional=getattr(self.adapter,"required_for_mode",lambda values:())(values)
            return [f.label for f in self.adapter.FIELDS
                    if (not f.optional or f.key in conditional) and not values.get(f.key)]

        def refresh_run_state(self,update_status=False):
            values=self.input_values()
            visible=getattr(self.adapter,"visible_for_mode",lambda v:tuple(self.field_widgets))(values)
            for key,widgets in self.field_widgets.items():
                for widget in widgets:
                    if key in visible:widget.grid()
                    else:widget.grid_remove()
            missing=self.missing_fields(values)
            self.run_button.configure(state="disabled" if self.busy or missing else "normal")
            if update_status and not self.busy:
                self.status.configure(text="Choose "+missing[0].lower()+" first" if missing else "Ready · Local only")

        def state(self,busy):
            self.busy=busy
            for c in self.controls:
                c.configure(state="disabled" if busy else getattr(c,"_idle_state","normal"))
            self.clear_button.configure(state="disabled" if busy else "normal")
            self.refresh_run_state()

        def start(self,func,mode):
            if self.busy:return
            self.result=None
            self.reset_result("Checking locally…","No files are sent to a server.")
            self.status.configure(text=mode+" · Running")
            self.state(True)
            def work():
                try:
                    result=func()
                    if not isinstance(result,Result) or result.state not in ("pass","review","uninspected"):
                        raise ValueError("Invalid result")
                    self.messages.put((result,mode))
                except Exception:
                    # Never display exception paths, raw values or stack traces.
                    self.messages.put((None,mode))
            threading.Thread(target=work,daemon=True,name="local-inspection").start()

        def keyboard_run(self,event=None):
            if not self.busy and self.root.grab_current() is None:self.run_check()
            return "break"

        def run_check(self):
            if self.busy:return
            values=self.input_values()
            missing=self.missing_fields(values)
            if missing:
                self.refresh_run_state(update_status=True)
                return
            self.start(lambda:self.adapter.run(values),"Your inputs")

        def run_demo(self):
            if not self.busy:
                values=self.input_values()
                demo=getattr(self.adapter,"demo_for_mode",lambda v:self.adapter.demo())
                self.start(lambda:demo(values),"Synthetic example")

        def poll(self):
            if self.closed:return
            try:result,mode=self.messages.get_nowait()
            except queue.Empty:pass
            else:
                self.state(False)
                if result is None:
                    self.reset_result("Not inspected","Input could not be inspected. Check the format, limits and selected files.")
                    self.headline.configure(foreground="#a32b36")
                    self.status.configure(text=mode+" · No pass result")
                else:
                    self.render(result,mode)
            self.poll_id=self.root.after(50,self.poll)

        def render(self,result,mode):
            self.result=result
            self.result_mode=mode
            color=self.result_color(result.state)
            self.headline.configure(text=result.title,foreground=color)
            self.description.configure(text=result.description)
            for (label,value),(name,number) in zip(self.metrics,result.metrics):
                label.configure(text=str(name));value.configure(text=str(number))
            preview = self.adapter.LIMIT
            if result.state != "pass" and result.details:
                first = " ".join(str(result.details[0]).split())
                if len(first)>88:first=first[:85]+"…"
                preview = "First finding: "+first+"\n"+self.adapter.LIMIT
            self.detail.configure(text=preview)
            self.details_button.configure(state="normal")
            self.save_button.configure(state="normal",text="Save example" if mode=="Synthetic example" else "Save report")
            if result.snapshot is not None:
                self.extra_button.configure(state="normal")
                self.extra_button.pack(side="bottom",fill="x",pady=(0,5),before=self.detail)
            self.status.configure(text=mode+" · "+{"pass":"Checks passed","review":"Review required","uninspected":"Not fully inspected"}[result.state])

        def popup(self,title,body,summary=None):
            w=tk.Toplevel(self.root)
            w.title(title)
            w.configure(bg=self.bg)
            w.geometry("690x490")
            w.transient(self.root)
            box=ttk.Frame(w,padding=15)
            box.pack(fill="both",expand=True)
            ttk.Label(box,text=title,style="Title.TLabel",wraplength=650).pack(anchor="w",pady=(0,8))
            holder=ttk.Frame(box);holder.pack(fill="both",expand=True)
            scroll=ttk.Scrollbar(holder);scroll.pack(side="right",fill="y")
            view=tk.Text(holder,wrap="word",font=nametofont("TkDefaultFont"),bg=self.panel,fg=self.fg,padx=12,pady=10,relief="flat",yscrollcommand=scroll.set)
            view.pack(side="left",fill="both",expand=True)
            scroll.configure(command=view.yview)
            view.insert("1.0",body);view.configure(state="disabled")
            actions=ttk.Frame(box);actions.pack(fill="x",pady=(8,0))
            ttk.Button(actions,text="Close",command=w.destroy).pack(side="right")
            if summary is not None:
                def copy_summary():
                    if self.result is None:return
                    self.root.clipboard_clear();self.root.clipboard_append(summary)
                    feedback.configure(text="Summary copied")
                feedback=ttk.Label(actions,text="",style="Muted.TLabel");feedback.pack(side="left",padx=(8,0))
                ttk.Button(actions,text="Copy summary",command=copy_summary).pack(side="left")
            w.bind("<Escape>",lambda e:w.destroy())
            w.protocol("WM_DELETE_WINDOW",w.destroy)
            w.grab_set()
            view.focus_set()
            return w

        def show_report(self):
            if self.result:
                report=self.result
                lines=[report.title,report.description,""]+list(report.details[:250])
                if len(report.details)>250:lines.append("Additional findings: export JSON for the full bounded report.")
                summary="\n".join([self.adapter.TITLE, self.result_mode, report.title]+[f"{key}: {value}" for key,value in report.metrics])
                self.popup("Inspection report","\n".join(lines),summary)

        def more(self):
            self.popup("Scope, privacy and use",self.adapter.MORE)

        def save(self,data,title,*,allow_html=False):
            if not data:return
            p=filedialog.asksaveasfilename(parent=self.root,title=title,defaultextension=".json",
                filetypes=(("JSON report","*.json"),("Local HTML report","*.html")) if allow_html else (("JSON report","*.json"),))
            if not p:return
            try:
                target=Path(p)
                if self.result and self.result.protected_root:
                    # Avoid adding reports or candidate pins to the folder being audited.
                    if target.resolve().is_relative_to(Path(self.result.protected_root).resolve()):
                        messagebox.showerror("Choose another folder","Save outside the audited build folder.",parent=self.root)
                        return
                suffix=target.suffix.lower()
                if allow_html and suffix==".html":
                    write_new_bytes(target,render_report(self.adapter,self.result,synthetic=self.result_mode=="Synthetic example"))
                elif suffix==".json":
                    write_new_json(target,data)
                else:
                    raise ValueError("Choose a supported export extension")
                self.status.configure(text="Saved new local report · Review before sharing")
            except (ValueError,OSError):
                messagebox.showerror("Not saved","Choose a new writable filename. Existing files are never overwritten.",parent=self.root)

        def save_report(self):
            if self.result:self.save(self.result.data,"Save synthetic example" if self.result_mode=="Synthetic example" else "Save inspection report",allow_html=True)
        def save_snapshot(self):
            if self.result and self.result.snapshot is not None:
                if messagebox.askyesno("Review required","This snapshot is a candidate inventory, not approval. Review the actual build independently before using it as a verification pin.",parent=self.root):
                    self.save(self.result.snapshot,"Save candidate snapshot")
        def clear(self):
            if self.busy:return
            self.result=None
            for field in self.adapter.FIELDS:
                self.set_value(field.key,() if field.kind=="files" else field.default)
            self.reset_result("Ready to inspect","Choose your inputs or run the built-in example.")
            self.status.configure(text="Local only · No uploads")
        def close(self):
            self.closed=True
            self.root.after_cancel(self.poll_id)
            self.root.destroy()

    window = root or tk.Tk()
    app = App(window)
    if run_loop:
        window.mainloop()
    return app
