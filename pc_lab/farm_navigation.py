"""Calibrated visual menu adapter for the user's farming product.

Not an agent computer-use helper. Never invoked on authentication screens.
Every single click needs two visible anchors from recorded game menus.
"""
import ctypes
import json
import time
from pathlib import Path
from PIL import Image,ImageChops,ImageStat,ImageFilter
from .solver import ROOT


class NativeNavigator:
    @staticmethod
    def load_recipe(path=None):
        path=Path(path or ROOT/'output/farm-navigation/recipe.json')
        if not path.is_file():raise ValueError('刷分菜单尚未完成实机校准；未发送按键。请先关闭刷分，进入游戏后继续校准。')
        recipe=json.loads(path.read_text(encoding='utf-8'));base=path.parent.resolve()
        if recipe.get('version')!=1 or recipe.get('queue_route')!='home_solo_blitz_start':raise ValueError('刷分菜单校准格式无效。')
        required={'initial':('solo','blitz','start'),'complete':('home','solo','blitz','start'),
                  'export':('download','filename','save')}
        if recipe.get('abandoned'):
            required['abandoned']=('pause','exit','home','solo','blitz','start')
        for route,roles in required.items():
            steps=recipe.get(route)
            if not isinstance(steps,list) or tuple(s.get('role') for s in steps)!=roles:raise ValueError(f'菜单 {route} 路径未经完整校准。')
            for step in steps:
                anchors=step.get('anchors',[])
                if len(anchors)!=2:raise ValueError('每个菜单动作必须有两个画面校验区。')
                for a in anchors:
                    template=(base/a['file']).resolve()
                    if not template.is_relative_to(base) or not template.is_file():raise ValueError('菜单校验图片缺失或越界。')
                    x,y,w,h=a['rect']
                    if not all(isinstance(v,int) and not isinstance(v,bool) for v in (x,y,w,h)) or w<20 or h<8 or x<0 or y<0 or x+w>1536 or y+h>960:
                        raise ValueError('菜单校验区域无效。')
                    with Image.open(template) as im:
                        if im.size!=(w,h) or ImageStat.Stat(im.convert('L')).stddev[0]<15:raise ValueError('菜单图片须包含清晰的按钮文字，不能只录背景。')
                    a['path']=str(template)
                x,y=step['point']
                if not 0<=x<1536 or not 0<=y<960:raise ValueError('菜单点击位置无效。')
                step['timeout']=min(15,max(1,float(step.get('timeout',8))))
        return recipe

    def __init__(self,hwnd,recipe,stopped,folder,cancelled=lambda:False):
        self.hwnd=hwnd;self.recipe=recipe;self.stopped=stopped;self.cancelled=cancelled;self.folder=Path(folder);self.counter=0

    def guard(self,dialog=False):
        from .windows import user,emergency_pressed
        foreground=int(user.GetForegroundWindow() or 0)
        # The callback stops on any focus change; a file dialog is owned by
        # this exact game window and is the only permitted exception.
        owned=False
        if dialog and foreground and foreground!=self.hwnd:
            user.GetWindow.argtypes=[ctypes.c_void_p,ctypes.c_uint];user.GetWindow.restype=ctypes.c_void_p
            owned=int(user.GetWindow(foreground,4) or 0)==self.hwnd
        if self.cancelled() or emergency_pressed() or (self.stopped() and not owned):raise InterruptedError('刷分菜单停止：取消、F8/Esc或游戏失焦。')
        if foreground!=self.hwnd and not owned:raise InterruptedError('刷分菜单失去游戏焦点。')

    @staticmethod
    def matches(image,step):
        normalized=image.convert('RGB').resize((1536,960))
        for a in step['anchors']:
            x,y,w,h=a['rect']
            crop=normalized.crop((x,y,x+w,y+h)).convert('L').filter(ImageFilter.GaussianBlur(.5))
            with Image.open(a['path']) as reference:
                reference=reference.convert('L').filter(ImageFilter.GaussianBlur(.5))
                if ImageStat.Stat(ImageChops.difference(crop,reference)).mean[0]>8:return False
        return True

    @staticmethod
    def move_pointer(x,y):
        from .windows import user,INPUT,INPUTUNION,MOUSEINPUT
        if not user.SetCursorPos(round(x),round(y)):raise RuntimeError('无法移动游戏鼠标。')
        # Electron's drawn cursor can retain the last genuine mouse-move
        # position after SetCursorPos alone. Send a small real move too, so
        # the visible glow leaves the anchor before its image is checked.
        event=INPUT(type=0,data=INPUTUNION(mi=MOUSEINPUT(dx=1,dy=0,dwFlags=1)))
        if user.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))!=1:raise RuntimeError('菜单鼠标移动未被接受。')

    def wait(self,step):
        from .windows import capture,bounds,user
        if step['role'] not in ('filename','save'):
            self.guard()
            left,top,right,bottom=bounds(self.hwnd)
            # Keep the pointer on the observed empty lower-right game
            # background so hover animations cannot move menu words.
            self.move_pointer(left+(right-left)*1450/1536,top+(bottom-top)*850/960)
        end=time.perf_counter()+step['timeout'];hits=0;image=None
        while time.perf_counter()<end:
            self.guard(step['role'] in ('filename','save'))
            x1,y1,x2,y2=bounds(self.hwnd)
            if abs((x2-x1)/(y2-y1)-1.6)>.025:raise RuntimeError('窗口比例变化；请重新校准刷分菜单。')
            image=capture(self.hwnd,require_focus=False)
            hits=hits+1 if self.matches(image,step) else 0
            if hits>=2:
                self.counter+=1;image.save(self.folder/f'menu-{self.counter:04d}-{step["role"]}.png')
                return image
            time.sleep(.05)
        if image is not None:image.save(self.folder/f'menu-stop-{step["role"]}.png')
        raise RuntimeError(f'没有确认 {step["role"]} 菜单，未点击；刷分停止。')

    def click(self,step):
        from .windows import user,bounds,INPUT,INPUTUNION,MOUSEINPUT
        self.wait(step);self.guard(step['role'] in ('filename','save'))
        left,top,right,bottom=bounds(self.hwnd);x,y=step['point']
        # No focus acquisition: user focus loss is a stop, not a refocus.
        self.move_pointer(left+x*(right-left)/1536,top+y*(bottom-top)/960)
        event=INPUT(type=0,data=INPUTUNION(mi=MOUSEINPUT(dwFlags=2)))
        try:
            self.guard(step['role'] in ('filename','save'))
            if user.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))!=1:raise RuntimeError('菜单点击未被接受。')
            time.sleep(.03)
        finally:
            event.data.mi.dwFlags=4;user.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))

    def filename(self,step,path):
        from .windows import user,INPUT,INPUTUNION,KEYBDINPUT
        # The filename field is clicked after its own two image guards.
        self.click(step);self.guard(True)
        def key(vk,up=False):
            event=INPUT(type=1,data=INPUTUNION(ki=KEYBDINPUT(wVk=vk,dwFlags=2 if up else 0)))
            if user.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))!=1:raise RuntimeError('文件名输入未被接受。')
        try:key(0x11);key(0x41)
        finally:key(0x41,True);key(0x11,True)
        for unit in memoryview(str(path).encode('utf-16-le')).cast('H'):
            self.guard(True)
            event=INPUT(type=1,data=INPUTUNION(ki=KEYBDINPUT(wScan=unit,dwFlags=4)))
            try:
                if user.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))!=1:raise RuntimeError('文件名输入未被接受。')
            finally:
                event.data.ki.dwFlags=6;user.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))

    def confirm_save(self,step):
        from .windows import user,INPUT,INPUTUNION,KEYBDINPUT
        # A calibrated native Save dialog can swallow the first pointer
        # click while leaving the filename edit active. Its default Save
        # action is Enter. Still require both anchors and exact ownership;
        # send it once, then require the actual new valid replay file.
        self.wait(step);self.guard(True)
        event=INPUT(type=1,data=INPUTUNION(ki=KEYBDINPUT(wVk=0x0D)))
        try:
            if user.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))!=1:
                raise RuntimeError('原生保存操作未被接受。')
            time.sleep(.03)
        finally:
            event.data.ki.dwFlags=2
            user.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))

    def fresh_game(self,abandoned=False,initial=False):
        route=self.recipe['abandoned' if abandoned else 'complete'] if not initial else None
        if initial:
            from .windows import capture,bounds,user
            self.guard()
            left,top,right,bottom=bounds(self.hwnd)
            self.move_pointer(left+(right-left)*1450/1536,top+(bottom-top)*850/960)
            end=time.perf_counter()+12
            candidates=[self.recipe['initial'],self.recipe['complete'],[self.recipe['initial'][-1]]]
            while time.perf_counter()<end:
                self.guard();image=capture(self.hwnd)
                route=next((steps for steps in candidates if self.matches(image,steps[0])),None)
                if route:break
                time.sleep(.05)
            if not route:raise RuntimeError('请停在 HOME、BLITZ 启动页或已结束的结果页；未点击。')
        for step in route:self.click(step)

    def export_complete(self,path):
        path=Path(path).resolve()
        if not path.is_relative_to(self.folder.resolve()) or path.suffix!='.ttr' or path.exists():raise ValueError('录像目标必须是本次刷分目录里的新 .TTR 文件。')
        for step in self.recipe['export']:
            if step['role']=='filename':self.filename(step,path)
            elif step['role']=='save':self.confirm_save(step)
            else:self.click(step)
        end=time.perf_counter()+5
        while time.perf_counter()<end:
            self.guard(True)
            if path.is_file():
                try:
                    json.loads(path.read_text(encoding='utf-8-sig'))
                    from .windows import user
                    if int(user.GetForegroundWindow() or 0)==self.hwnd:return
                except (ValueError,OSError):pass
            time.sleep(.05)
        raise RuntimeError('未确认原生录像导出，刷分停止并保留结果页。')
