"""Clash auto selector GUI. All Tk access stays on the main thread."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk
from core import choose, all_timeout, next_due
import windows
from vision import Vision

DEFAULTS = {"interval": 60.0, "wait": 10.0, "keyword": "新加坡"}


class App:
    def __init__(self, root):
        self.root = root
        root.title("Clash 自动选择节点")
        root.geometry("850x690")
        root.minsize(720, 570)
        self.data = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ClashAutoSelector"
        self.data.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("selector")
        self.logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(self.data / "selector.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger.addHandler(handler)
        self.config = dict(DEFAULTS)
        try:
            saved = json.loads((self.data / "config.json").read_text(encoding="utf-8"))
            self.config = self.validate(saved)
        except (OSError, ValueError, TypeError, KeyError):
            pass
        self.lock = threading.Lock()
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.quit = threading.Event()
        self.now = threading.Event()
        self.worker = None
        self.engine = None
        self.window_list = []
        self.values = {key: tk.StringVar(value=str(value)) for key, value in self.config.items()}
        self.status = tk.StringVar(value="尚未运行。请先打开 Clash 的代理节点页面。")
        self.countdown = tk.StringVar(value="快捷停止：Ctrl+Alt+F12")
        pad = ttk.Frame(root, padding=14)
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, text="Clash 自动选择节点", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
        ttk.Label(pad, text="运行时自动将 Clash 切到前台；全部目标节点 Timeout 时立即重新测速。", wraplength=790).pack(anchor="w", pady=(6,12))
        settings = ttk.LabelFrame(pad, text="运行设置", padding=10)
        settings.pack(fill="x")
        for col, (key, label) in enumerate([("interval", "测速间隔（秒）"), ("wait", "测速等待（秒）"), ("keyword", "节点名称关键词")]):
            ttk.Label(settings, text=label).grid(row=0, column=col, sticky="w", padx=6)
            ttk.Entry(settings, textvariable=self.values[key], width=23).grid(row=1, column=col, sticky="ew", padx=6, pady=5)
            settings.columnconfigure(col, weight=1)
        ttk.Button(settings, text="保存设置（下一轮生效）", command=self.save).grid(row=2, column=0, columnspan=3, sticky="w", padx=6)
        targets = ttk.Frame(pad)
        targets.pack(fill="x", pady=10)
        ttk.Label(targets, text="Clash 窗口：").pack(side="left")
        self.window_combo = ttk.Combobox(targets, state="readonly")
        self.window_combo.pack(side="left", fill="x", expand=True)
        self.refresh_btn = ttk.Button(targets, text="刷新", command=self.refresh)
        self.refresh_btn.pack(side="left", padx=(8,0))
        buttons = ttk.Frame(pad)
        buttons.pack(fill="x")
        self.start_btn = ttk.Button(buttons, text="开始循环", command=lambda: self.begin("loop"))
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(buttons, text="停止", command=self.request_stop)
        self.stop_btn.pack(side="left", padx=6)
        self.once_btn = ttk.Button(buttons, text="立即执行一轮", command=self.immediate)
        self.once_btn.pack(side="left")
        self.preview_btn = ttk.Button(buttons, text="识别预览", command=lambda: self.begin("preview"))
        self.preview_btn.pack(side="left", padx=6)
        ttk.Label(pad, textvariable=self.status, wraplength=790).pack(anchor="w", pady=(12,3))
        ttk.Label(pad, textvariable=self.countdown).pack(anchor="w")
        self.table = ttk.Treeview(pad, columns=("name","delay","selected"), show="headings", height=7)
        for key, label, width in [("name","匹配节点",420),("delay","延迟 / 状态",150),("selected","当前选中",90)]:
            self.table.heading(key, text=label)
            self.table.column(key, width=width)
        self.table.pack(fill="both", expand=True, pady=8)
        self.logs = tk.Text(pad, height=7, state="disabled", wrap="word")
        self.logs.pack(fill="both", expand=True)
        self.refresh()
        self.set_busy(False)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(80, self.poll)
        threading.Thread(target=windows.hotkey_loop, args=(self.quit,self.emit), daemon=True).start()

    @staticmethod
    def validate(values):
        import math
        interval, wait = float(values["interval"]), float(values["wait"])
        keyword = str(values["keyword"]).strip()
        if not all(math.isfinite(v) and 1 <= v <= 86400 for v in (interval,wait)) or not keyword:
            raise ValueError("间隔和等待时间必须为 1～86400 秒，关键词不能为空。")
        return {"interval": interval, "wait": wait, "keyword": keyword}

    def save(self):
        try:
            config = self.validate({key: var.get() for key,var in self.values.items()})
            temp = self.data / "config.tmp"
            temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.data / "config.json")
            with self.lock:
                self.config = config
            return True
        except (ValueError, OSError) as exc:
            messagebox.showerror("设置未保存", str(exc))
            return False

    def emit(self, event, value):
        self.events.put((event,value))

    def log(self, text):
        self.logger.info(text)
        self.emit("log",text)

    def refresh(self):
        self.window_list = windows.find_windows()
        self.window_combo["values"] = [f"{title}  [窗口 {hwnd}]" for hwnd,title in self.window_list]
        self.window_combo.set("")
        if len(self.window_list) == 1:
            self.window_combo.current(0)
        elif not self.window_list:
            self.status.set("未找到 Clash 窗口。请打开 Clash 后点击刷新。")

    def begin(self, mode):
        if self.worker and self.worker.is_alive():
            return
        if not self.save():
            return
        index = self.window_combo.current()
        if index < 0:
            messagebox.showinfo("选择窗口", "请打开 Clash、刷新列表，并选择目标窗口。")
            return
        hwnd = self.window_list[index][0]
        self.stop.clear()
        self.now.clear()
        self.set_busy(True)
        self.worker = threading.Thread(target=self.run, args=(hwnd, mode), daemon=True)
        self.worker.start()

    def set_busy(self, busy):
        for widget in [self.start_btn,self.preview_btn,self.refresh_btn]:
            widget.configure(state="disabled" if busy else "normal")
        self.window_combo.configure(state="disabled" if busy else "readonly")
        self.stop_btn.configure(state="normal" if busy else "disabled")

    def immediate(self):
        if self.worker and self.worker.is_alive():
            if self.save():
                self.now.set()
                self.log("已请求尽快执行一轮；当前测速完成后再执行，不并发。")
        else:
            self.begin("once")

    def request_stop(self):
        self.stop.set()
        self.status.set("正在停止，已取消后续点击…")

    def pause(self, seconds, label):
        deadline = time.monotonic()+seconds
        while not self.stop.is_set():
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                return
            self.emit("countdown", f"{label}：{remaining:.0f} 秒 · Ctrl+Alt+F12 停止")
            if self.stop.wait(min(.2,remaining)):
                break
        raise InterruptedError()

    def run(self, hwnd, mode):
        retry_count = 0
        due = time.monotonic()
        try:
            if self.engine is None:
                self.emit("status", "正在加载本地 OCR 模型…")
                self.engine = Vision()
            while not self.stop.is_set():
                while time.monotonic() < due and not self.stop.is_set() and not self.now.is_set():
                    self.emit("countdown", f"下次测速：{max(0,due-time.monotonic()):.0f} 秒 · Ctrl+Alt+F12 停止")
                    self.stop.wait(.2)
                if self.stop.is_set():
                    break
                self.now.clear()
                with self.lock:
                    config = dict(self.config)
                started = time.monotonic()
                retry = False
                try:
                    windows.activate(hwnd,self.stop)
                    rgb,bounds = windows.capture(hwnd)
                    candidates,complete,texts = self.engine.scan(rgb,config["keyword"])
                    expected_count = len(candidates)
                    button = self.engine.button(rgb,texts)
                    if mode == "preview":
                        self.emit("candidates",candidates)
                        self.emit("preview",self.engine.preview(rgb,candidates,button))
                        self.log(f"识别预览：{len(candidates)} 个匹配节点；完整识别={complete}；本次没有点击。")
                        break
                    self.emit("status", "已定位测速按钮，开始测速…")
                    windows.click(hwnd,bounds,button,self.stop)
                    started = time.monotonic()
                    self.log(f"开始测速：关键词={config['keyword']}，等待 {config['wait']:g} 秒")
                    self.pause(config["wait"],"测速等待")
                    windows.activate(hwnd,self.stop)
                    rgb,bounds = windows.capture(hwnd)
                    candidates,complete,texts = self.engine.scan(rgb,config["keyword"])
                    complete = complete and len(candidates) >= expected_count
                    self.engine.button(rgb,texts)  # Reconfirm the page before selecting a card.
                    self.emit("candidates",candidates)
                    if self.stop.is_set():
                        raise InterruptedError()
                    best = choose(candidates)
                    if best:
                        retry_count = 0
                        if best.selected:
                            self.log(f"当前已是最低延迟：{best.name}，{best.delay} ms")
                        else:
                            x,y,w,h = best.rect
                            windows.click(hwnd,bounds,(x+w*.40,y+h*.35),self.stop)
                            self.pause(.5,"确认选择")
                            after,after_bounds = windows.capture(hwnd)
                            if after_bounds != bounds:
                                raise RuntimeError("选择后窗口位置改变，无法确认结果")
                            checked,_,_ = self.engine.scan(after,config["keyword"])
                            confirmed = any(c.name == best.name and c.selected and c.rect == best.rect for c in checked)
                            if not confirmed:
                                raise RuntimeError(f"已点击 {best.name}，但未确认选中样式；请检查 Clash")
                            self.emit("candidates",checked)
                            self.log(f"已选择最低延迟节点：{best.name}，{best.delay} ms")
                    elif all_timeout(candidates,complete):
                        retry = True
                        retry_count += 1
                        self.log(f"全部 {len(candidates)} 个目标节点 Timeout，立即重测（连续重试 {retry_count} 次）")
                    else:
                        retry_count = 0
                        self.log("没有可可靠使用的数字延迟，保留当前节点，按正常间隔重试。")
                except InterruptedError:
                    raise
                except Exception as exc:
                    retry_count = 0
                    self.log(f"本轮跳过：{exc}")
                finished = time.monotonic()
                if mode == "once" and not retry and not self.now.is_set():
                    break
                due = next_due(started,finished,config["interval"],retry)
                self.emit("status", "全部超时，立即重试…" if retry else "本轮结束，等待下一轮。")
        except InterruptedError:
            self.log("已停止，后续点击已取消。")
        except Exception as exc:
            self.log(f"运行失败：{exc}")
        finally:
            self.emit("done",None)

    def show_preview(self, im):
        top = tk.Toplevel(self.root)
        top.title("识别预览：绿框为可靠结果，橙框需检查，红圈为测速按钮")
        # Fit preview to the current display; the analysis uses original pixels.
        im.thumbnail((self.root.winfo_screenwidth()-100,self.root.winfo_screenheight()-150))
        photo = ImageTk.PhotoImage(im)
        label = ttk.Label(top,image=photo)
        label.image = photo
        label.pack()

    def poll(self):
        try:
            while True:
                event,value = self.events.get_nowait()
                if event == "log":
                    self.logs.configure(state="normal")
                    self.logs.insert("end",time.strftime("%H:%M:%S ")+value+"\n")
                    if int(self.logs.index("end-1c").split(".")[0]) > 500:
                        self.logs.delete("1.0","100.0")
                    self.logs.see("end")
                    self.logs.configure(state="disabled")
                    self.status.set(value)
                elif event in ("status","countdown"):
                    getattr(self,event).set(value)
                elif event == "candidates":
                    self.table.delete(*self.table.get_children())
                    for c in value:
                        self.table.insert("","end",values=(c.name,c.status or "未识别","是" if c.selected else ""))
                elif event == "preview":
                    self.show_preview(value)
                elif event == "stop":
                    self.request_stop()
                elif event == "hotkey_error":
                    self.log(value)
                elif event == "done":
                    self.set_busy(False)
                    self.countdown.set("已停止 · 快捷停止：Ctrl+Alt+F12")
        except queue.Empty:
            pass
        self.root.after(80,self.poll)

    def close(self):
        self.stop.set()
        self.quit.set()
        # Keep the process alive until in-flight OCR returns and the worker exits.
        if self.worker and self.worker.is_alive():
            self.status.set("正在退出，等待当前识别结束；后续点击已取消…")
            self.root.after(100,self.close)
        else:
            self.root.destroy()


def main():
    windows.dpi_awareness()
    root = tk.Tk()
    ttk.Style().theme_use("vista")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from selftest import run
        raise SystemExit(run(sys.argv[2]))
    main()
