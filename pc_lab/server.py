"""Loopback-only PC solver and explicitly started desktop bot jobs."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import secrets
import threading
import uuid
import webbrowser

from .solver import ROOT, SFINDER, java_path, solve
from .fast_solver import solve_fast
from .loop import plan_loop
from .config import load_profile,parse_config,optimize_config,save_current
from .speed import PRESETS,speed_settings


class Lab:
    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = {}
        self.workers = []
        self.token = secrets.token_urlsafe(32)
        self.settings={'operation_interval_ms':20,'speed_preset':'custom','recover_on_failure':False,'max_retries':0}
        try:
            saved=json.loads((ROOT/'output/preferences.json').read_text(encoding='utf-8'))
            value=float(saved['operation_interval_ms'])
            if 0<=value<=2000:self.settings['operation_interval_ms']=value
            self.settings['speed_preset']=speed_settings(saved.get('speed_preset','custom'))['speed_preset']
            self.settings['recover_on_failure']=bool(saved.get('recover_on_failure',False))
            retries=int(saved.get('max_retries',0))
            if 0<=retries<=1000:self.settings['max_retries']=retries
        except (OSError,ValueError,TypeError,KeyError):pass

    def start(self, request):
        if request.get('kind')=='live':
            name=request.get('speed_preset',self.settings['speed_preset'])
            interval=request.get('operation_interval_ms',self.settings['operation_interval_ms'] if name==self.settings['speed_preset'] else None)
            request['timing']=speed_settings(name,interval)
            request['live_metrics']={}
        with self.lock:
            if any(job["state"] in ("searching", "validating", "queued", "running", "retrying") for job in self.jobs.values()):
                raise ValueError("已有求解任务，请等待完成或先停止。")
            job_id = uuid.uuid4().hex
            event = threading.Event()
            self.jobs[job_id] = {"id": job_id,"kind":request.get("kind","pc"), "state": "queued", "message": "准备求解…", "cancel": event}
            if request.get('kind')=='live':
                self.jobs[job_id]['settings']=request['timing'];self.jobs[job_id]['metrics']=request['live_metrics']
            # Keep recent results without growing memory indefinitely.
            if len(self.jobs) > 20:
                del self.jobs[next(iter(self.jobs))]
        def progress(state, message):
            with self.lock:
                self.jobs[job_id].update(state=state, message=message)
        def work():
            try:
                if request.get("kind")=="live":
                    from .live import run_live
                    result=run_live(request,progress,event.is_set)
                elif request.get("kind")=="loop":
                    result=plan_loop(request,progress,event.is_set)
                else:
                    result=solve_fast(request,progress,event.is_set)
                if event.is_set():
                    raise InterruptedError("已停止求解。")
                with self.lock:
                    self.jobs[job_id].update(state="done", message=result["message"], result=result)
            except InterruptedError as exc:
                progress("cancelled", str(exc))
            except Exception as exc:
                progress("error", str(exc))
        worker = threading.Thread(target=work, daemon=True)
        with self.lock:
            self.workers = [thread for thread in self.workers if thread.is_alive()] + [worker]
        worker.start()
        return job_id

    def snapshot(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            return {key: dict(value) if key=='metrics' else value for key, value in job.items() if key != "cancel"} if job else None


def serve(port=8787, open_browser=False):
    lab = Lab()
    ui_dir = ROOT / "ui"
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, data, mime="application/json; charset=utf-8"):
            payload = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def trusted(self):
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self.trusted():
                return self.send(403, {"error": "只允许本机访问。"})
            if self.path == "/api/config":
                with lab.lock:
                    active=next((j["id"] for j in lab.jobs.values() if j.get("kind")=="live" and
                                 j["state"] in ("queued","running","retrying")),None)
                profile=load_profile()
                raw=json.loads((ROOT/'output/current-config.ttc').read_text(encoding='utf-8')) if profile else None
                from .farm_navigation import NativeNavigator
                try:
                    farm_recipe=NativeNavigator.load_recipe();farm_ready=True
                    farm_abandon_ready=bool(farm_recipe.get('abandoned'))
                except (ValueError,OSError,KeyError,TypeError):farm_ready=False;farm_abandon_ready=False
                return self.send(200, {"name": "PC Lab", "version": "0.12.13", "token": lab.token,"active_live_job":active,"settings":lab.settings,
                                       "farm_navigation_ready":farm_ready,
                                       "farm_abandon_ready":farm_abandon_ready,
                                       "speed_presets":PRESETS,
                                       "control_profile":profile,"control_config":raw,
                                       "project_root": str(ROOT),
                                       "solver_ready": SFINDER.is_file() and bool(list((ROOT / "tools/java").glob("*/bin/java.exe")))})
            if self.path.startswith("/api/jobs/"):
                job = lab.snapshot(self.path.rsplit("/", 1)[-1])
                return self.send(200 if job else 404, job or {"error": "任务不存在。"})
            if self.path.startswith('/api/blitz-profile/'):
                name=self.path.rsplit('/',1)[-1]
                if name not in ('blitz','level10','level15','20g'):return self.send(400,{'error':'无法识别模拟条件。'})
                path=ROOT/'output/blitz-configs'/f'{name}-random.ttp'
                if not path.is_file():return self.send(404,{'error':'模拟配置尚未生成。'})
                config=json.loads(path.read_text(encoding='utf-8-sig'))
                if not config.get('seed_random') or config.get('bagtype')!='7-bag':return self.send(400,{'error':'模拟配置必须启用随机七袋。'})
                return self.send(200,config)
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/manual": ("manual.html", "text/html; charset=utf-8"),
                     "/pure4-manual": ("pure4-manual.html", "text/html; charset=utf-8"),
                     "/blitz-manual": ("blitz-manual.html", "text/html; charset=utf-8"),
                     "/blitz-research": ("blitz-research.html", "text/html; charset=utf-8"),
                     "/blitz-bounds": ("blitz-bounds.html", "text/html; charset=utf-8"),
                     "/setup-clears": ("setup-clears.html", "text/html; charset=utf-8"),
                     "/wr-study.json": ("wr-study.json", "application/json; charset=utf-8"),
                     "/wr-first-pc.jpg": ("wr-first-pc.jpg", "image/jpeg"),
                     "/wr-second-pc.jpg": ("wr-second-pc.jpg", "image/jpeg"),
                     "/wr-third-pc.jpg": ("wr-third-pc.jpg", "image/jpeg"),
                     "/blitz-best-native.png": ("blitz-best-native.png", "image/png"),
                     "/blitz-result.png": ("blitz-result.png", "image/png"),
                     "/blitz-result.jpg": ("blitz-result.jpg", "image/jpeg"),
                     "/app.js": ("app.js", "application/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if self.path in files:
                name, mime = files[self.path]
                return self.send(200, (ui_dir / name).read_bytes(), mime)
            self.send(404, {"error": "页面不存在。"})

        def do_POST(self):
            if not self.trusted() or self.headers.get("X-PC-Token") != lab.token:
                return self.send(403, {"error": "请求来源无效，请刷新本机页面。"})
            if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self.send(403, {"error": "请求来源无效。"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1048576:
                    raise ValueError("请求大小无效。")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError("请求格式无效。")
                if self.path == "/api/solve":
                    return self.send(202, {"id": lab.start(request)})
                if self.path == "/api/live":
                    request["kind"]="live"
                    return self.send(202,{"id":lab.start(request)})
                if self.path == '/api/control-config':
                    with lab.lock:
                        if any(j['state'] in ('queued','running','retrying') and j.get('kind')=='live' for j in lab.jobs.values()):
                            raise ValueError('请先停止自动操作，再更换配置。')
                    raw=request.get('config');parse_config(raw)
                    if request.get('optimize'):
                        raw=optimize_config(raw,request.get('speed_preset','steady'),paired_taps=request.get('paired_taps') is True);profile=parse_config(raw)
                    else:profile=save_current(raw)
                    return self.send(200,{'profile':profile,'config':raw})
                if self.path == '/api/live/settings':
                    name=request.get('speed_preset',lab.settings['speed_preset'])
                    interval=request.get('operation_interval_ms',None if 'speed_preset' in request else lab.settings['operation_interval_ms'])
                    speed=speed_settings(name,interval)
                    retries=int(request.get('max_retries',lab.settings['max_retries']))
                    if not 0<=retries<=1000:raise ValueError('恢复次数须为 0 至 1000。')
                    with lab.lock:
                        job=lab.jobs.get(request.get('id'))
                        active=any(j.get('kind')=='live' and j['state'] in ('queued','running','retrying') for j in lab.jobs.values())
                        if active and name!=lab.settings['speed_preset']:raise ValueError('请先停止自动操作，再切换速度档位。')
                        if job and job.get('kind')=='live':job['settings']['operation_interval_ms']=speed['operation_interval_ms']
                        lab.settings.update(speed_preset=name,operation_interval_ms=speed['operation_interval_ms'])
                        if 'recover_on_failure' in request:lab.settings['recover_on_failure']=bool(request['recover_on_failure'])
                        if 'max_retries' in request:
                            lab.settings['max_retries']=retries
                    (ROOT/'output/preferences.json').write_text(json.dumps(lab.settings),encoding='utf-8')
                    return self.send(200,{'ok':True,**speed})
                if self.path == "/api/game/inspect":
                    from .windows import find_game,focus,capture,close_capture
                    from .vision import read_state
                    game=find_game();focus(game["hwnd"])
                    try:state=read_state(capture(game["hwnd"]))
                    finally:close_capture()
                    return self.send(200,{"game":game,"active":state["active"],"hold":state["hold"],
                                          "next":state["next"],"preview_count":state["preview_count"]})
                if self.path == "/api/cancel":
                    with lab.lock:
                        job = lab.jobs.get(request.get("id"))
                        if job:
                            job["cancel"].set()
                    return self.send(200, {"ok": True})
                if self.path == "/api/shutdown":
                    self.send(200, {"ok": True})
                    threading.Thread(target=server.shutdown, daemon=True).start()
                    return
                self.send(404, {"error": "操作不存在。"})
            except (ValueError, TypeError, RuntimeError,InterruptedError) as exc:
                self.send(400, {"error": str(exc)})

    java_path()  # Fail before displaying a non-functional UI.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    pid_path = ROOT / f"output/server-{port}.pid"
    pid_path.parent.mkdir(exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="ascii")
    print(f"PC Lab: http://127.0.0.1:{port}", flush=True)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    finally:
        with lab.lock:
            for job in lab.jobs.values():
                job["cancel"].set()
        for worker in lab.workers:
            worker.join(timeout=3)
        server.server_close()
        if pid_path.exists() and pid_path.read_text().strip() == str(os.getpid()):
            pid_path.unlink()
