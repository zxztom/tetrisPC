"""One warm sfinder JVM per planning thread, with bounded cancellation."""
import os
import queue
import subprocess
import threading
import time
from .solver import ROOT,SFINDER,java_path

_local=threading.local()

class SearchWorker:
    def __init__(self):
        self.process=subprocess.Popen([str(java_path()),'-Xmx384m','-cp',os.pathsep.join((str(ROOT/'tools/bridge'),str(SFINDER))),
            'PcSearch','--worker'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.lines=queue.Queue()
        self.reader=threading.Thread(target=self.read,daemon=True);self.reader.start()

    def read(self):
        try:
            for line in self.process.stdout:self.lines.put(line)
        finally:self.lines.put(None)

    def search(self,args,timeout,cancelled):
        if any('\t' in str(x) or '\n' in str(x) for x in args):raise ValueError('求解参数包含非法分隔符。')
        cooperative=len(args)>3 and str(args[3]).startswith('ground')
        if cooperative:args=list(args)+[str(max(1,(timeout-.005)*1000))]
        self.process.stdin.write('\t'.join(map(str,args))+'\n');self.process.stdin.flush()
        deadline=time.perf_counter()+timeout+(.03 if cooperative else 0);result=[]
        try:
            while True:
                if cancelled():raise InterruptedError('已停止求解。')
                remaining=deadline-time.perf_counter()
                if remaining<=0:raise TimeoutError('求解超过时间上限。')
                try:line=self.lines.get(timeout=min(.01,remaining))
                except queue.Empty:continue
                if line is None:raise RuntimeError('常驻求解器已退出。')
                if line.strip()=='END':return ''.join(result),2 if any(l.startswith('SEARCH_ERROR') for l in result) else 0
                result.append(line)
        except BaseException:self.close();raise

    def close(self):
        if self.process.poll() is None:self.process.kill()
        self.process.wait(timeout=2)
        self.reader.join(timeout=1)
        self.process.stdin.close();self.process.stdout.close()

def search(args,timeout,cancelled):
    worker=getattr(_local,'worker',None)
    if worker is None or worker.process.poll() is not None:
        if worker:worker.close()
        worker=SearchWorker();_local.worker=worker
    return worker.search(args,timeout,cancelled)

def close_worker():
    worker=getattr(_local,'worker',None)
    if worker:worker.close();_local.worker=None
