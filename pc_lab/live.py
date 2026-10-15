"""Closed-loop desktop execution: observe, plan, move, verify every lock."""
from collections import Counter
import json
import time
import uuid
import subprocess
import msvcrt
from pathlib import Path
from PIL import Image

from .engine import cells, empty_board, fits, load_kicks, lock,preferred_route,poses_for,dropped_cells,falls_to,advance_pose
from .fast_solver import find_pc
from .rng import seeded_queue
from .online import choose_plan,PlanningFailure,observation_consistent
from .openers import pco_setup,dpc_setup
from .dpc import seeded_dpc
from .cycles import cycle_spec
from .best_fields import field_setups
from .solver import ROOT, KICKS
from .vision import detect_geometry, read_state,Geometry,is_zen,aligned_board
from .windows import (find_game, focus, capture, tap, key_event,
                      emergency_pressed, DEFAULT_KEYS, user)
from .windows import GameNotFound,EmergencyKeys,close_capture
from .config import load_profile
from .speed import speed_settings


class Runner:
    def __init__(self, request, progress=lambda *_: None, cancelled=lambda: False, control_lock=None):
        self.request=request;self.progress=progress;self.cancelled=cancelled
        self.profile=load_profile(request.get('config_path'))
        (ROOT/'output').mkdir(exist_ok=True)
        self.owns_control_lock=control_lock is None
        self.control_lock=control_lock or (ROOT/'output/desktop-control.lock').open('a+b')
        if self.control_lock.tell()==0:self.control_lock.write(b'0');self.control_lock.flush()
        self.control_lock.seek(0)
        try:
            if self.owns_control_lock:msvcrt.locking(self.control_lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self.control_lock.close()
            raise RuntimeError('已有桌面操作任务；请先停止当前任务，避免两个程序同时按键。')
        try:self.game=connect_game(request,progress,cancelled);self.hwnd=self.game["hwnd"]
        except Exception:
            if self.owns_control_lock:self.control_lock.close()
            raise
        self.keys=dict(DEFAULT_KEYS)
        if self.profile:self.keys.update(self.profile['keys'])
        self.keys.update(request.get("keys",{}))
        self.geometry=None;self.palette=None
        self.folder=ROOT/"output"/("live-"+time.strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:8])
        self.folder.mkdir()
        self.steps=[];self.completed_cycles=0;self.completed_pcs=0;self.cleared=0
        self.latest=None;self.reference_board=None;self.fall_anchor=None;self.fall_rate=0;self.intentional_drop=False;self.pending_step=None
        self.game_mode=None
        self.waiting_for_start=False
        self.preview_count=None
        self.kick_path=KICKS
        self.kicks=load_kicks(KICKS)
        self.timing=request.get('timing',speed_settings(request.get('speed_preset','custom'),request.get('operation_interval_ms')))
        from .windows import set_capture_backend
        set_capture_backend('dxgi' if self.timing.get('speed_preset')=='extreme' else 'gdi')
        self.input_released=0
        self.input_trace=[]
        self.observed_at=0;self.last_image=None;self.play_started=None;self.piece_started=0
        self.lock_times=[];self.execution_seconds=0;self.capture_seconds=0;self.capture_count=0
        self.capture_region=None
        self.full_geometry=None;self.vision_fallbacks=0
        self.animation_pending=False;self.animation_waits=0
        self.interval_ms()

    def speed(self):
        return speed_settings(self.timing.get('speed_preset',self.request.get('speed_preset','custom')),self.interval_ms())

    def pace_piece(self):
        target=self.speed()['target_pps']
        # Keep the target rhythm across short solver pauses rather than
        # shifting the whole schedule later after every slow placement.
        deadline=self.play_started+len(self.lock_times)/target if target and self.play_started is not None else 0
        while time.perf_counter()<deadline:
            if self.stopped():raise InterruptedError('已停止自动操作。')
            time.sleep(min(.005,max(0,deadline-time.perf_counter())))
        self.piece_started=time.perf_counter()
        if self.play_started is None:self.play_started=self.piece_started

    def recovery_permitted(self):
        return bool(self.request.get('recover_on_failure'))

    def restart_current(self):
        state,image=self.observe()
        if state['game_mode']=='zen' and not self.recovery_permitted():
            raise RuntimeError('ZEN 清场需要打开“PC 无法继续时清空 / 重开”选项。')
        image.save(self.folder/'before-recovery.png')
        # In ZEN the retry action clears only the field. Never use the SOLO
        # ZEN RESET button, which discards the user's saved level/progress.
        # Leave render-frame margin beyond the client's three-second hold
        # threshold; precise timing must not release just before it samples.
        tap(self.hwnd,'retry',self.keys,duration=3.25,gap=.2,cancelled=self.stopped)
        self.reference_board=empty_board();self.geometry=None
        state,image=self.wait_for(lambda s:s['board']==empty_board() and s['active'] is not None,
                                  empty_board(),timeout=6)
        image.save(self.folder/'after-recovery.png')
        return state

    def interval_ms(self):
        value=float(self.timing.get('operation_interval_ms',75))
        if not 0<=value<=2000:raise ValueError('操作间隔应为 0 至 2000 毫秒。')
        return value

    def before_input(self,action=None):
        interval=self.interval_ms()/1000
        trace=getattr(self,'input_trace',[])
        if action and trace and trace[-1]['action'].removesuffix('_wall')==action:
            # Separate two presses of the same physical key by a neutral
            # simulation frame. With a zero gap, down/up/down can reach
            # the game in one update and behave as a held DAS charge.
            interval=max(interval,1/60)
        elapsed=time.perf_counter()-self.input_released
        while elapsed<interval:
            if self.stopped():raise InterruptedError('已停止自动操作。')
            time.sleep(min(.005,max(.001,interval-elapsed)))
            elapsed=time.perf_counter()-self.input_released

    def initial_state(self):
        timeout=int(self.request.get("start_timeout",120 if self.request.get("wait_start") else 10))
        deadline=time.perf_counter()+timeout
        self.waiting_for_start=True
        self.progress("running","等待空棋盘的单人练习，正在读取当前块、Hold 和实际 Next 数量。")
        previous=None;stable_since=0
        while time.perf_counter()<deadline:
            if self.cancelled() or emergency_pressed() or (getattr(self,'hotkeys',None) and self.hotkeys.pressed.is_set()):raise InterruptedError("已停止等待新局。")
            if int(user.GetForegroundWindow() or 0)!=self.hwnd:
                time.sleep(.1)
                continue
            try:
                self.geometry=None
                state,image=self.observe()
                if state["board"]==empty_board() and state["active"] is not None:
                    visible=(state["hold"] or '')+state["active"]+state["next"]
                    if len(visible[:7])!=len(set(visible[:7])):
                        if self.recovery_permitted():raise PlanningFailure('当前空场来块不在七袋起点，将清场重新同步。')
                        raise RuntimeError("当前空场的来块未能对应七袋起点，已停止；不会清除已有进度。")
                    signature=(state["active"],state["hold"],state["next"])
                    if signature!=previous:
                        previous=signature;stable_since=time.perf_counter()
                        continue
                    if time.perf_counter()-stable_since<.15:continue
                    self.preview_count=len(state["next"])
                    self.waiting_for_start=False
                    return state,image
            except ValueError:
                pass
            time.sleep(.1)
        raise RuntimeError("未等到可接管的空棋盘单人练习，不需要设置种子。")

    def stopped(self):
        return self.cancelled() or emergency_pressed() or (getattr(self,'hotkeys',None) and self.hotkeys.pressed.is_set()) or (not self.waiting_for_start and
               int(user.GetForegroundWindow() or 0)!=self.hwnd)

    def observe(self, expected_board=None):
        if self.stopped():raise InterruptedError("已停止：F8 / Esc、取消操作或游戏失去焦点。")
        started=time.perf_counter()
        scale=self.speed()['capture_scale']
        if self.geometry is None:
            image=capture(self.hwnd);geom=detect_geometry(image)
            self.full_geometry=geom
            if not self.game_mode:self.game_mode='zen' if is_zen(image) else 'practice'
            self.capture_region=None
            if scale!=1:
                region=(max(0,int(geom.left-5.4*geom.cell)),max(0,int(geom.top-4.3*geom.cell)),
                        min(image.width,int(geom.right+6.2*geom.cell)),min(image.height,int(geom.bottom+2*geom.cell)))
                self.capture_region=region
                image=capture(self.hwnd,scale=scale,region=region)
                self.geometry=Geometry((geom.left-region[0])*scale,(geom.top-region[1])*scale,geom.cell*scale,*image.size)
            else:self.geometry=geom
        else:image=capture(self.hwnd,scale=scale,region=self.capture_region)
        if self.game_mode=='zen' and not aligned_board(image,self.geometry):
            if not self.animation_pending:
                self.animation_waits+=1;self.progress('running','ZEN 升级过场：棋盘正在倾斜，等待画面恢复后继续。')
            self.animation_pending=True
            raise ValueError('ZEN 升级过场尚未结束。')
        self.animation_pending=False
        reference=expected_board if expected_board is not None else self.reference_board
        try:
            state=read_state(image,self.geometry,self.palette,reference,self.game_mode,
                             ignore_countdown=self.request.get('cycle_mode')=='blitz' and
                             (self.play_started is None or time.perf_counter()-self.play_started<1.5))
            if self.preview_count is not None and len(state['next'])!=self.preview_count:
                raise ValueError('高速截图中 Next 数量不完整。')
        except ValueError:
            if scale==1:raise
            self.vision_fallbacks+=1
            if self.vision_fallbacks==1:image.save(self.folder/'vision-fallback.png')
            image=capture(self.hwnd)
            state=read_state(image,self.full_geometry,self.palette,reference,self.game_mode,
                             ignore_countdown=self.request.get('cycle_mode')=='blitz' and
                             (self.play_started is None or time.perf_counter()-self.play_started<1.5))
        now=time.perf_counter();signature=(state['active'],state['hold'],state['next'])
        if state['active'] and len(state['active_cells'])==4 and not self.intentional_drop:
            anchor=self.fall_anchor
            if (anchor and signature==anchor[0] and reference is not None and
                    falls_to(reference,state['active'],anchor[1],state['active_cells'])):
                distance=min(y for x,y in anchor[1])-min(y for x,y in state['active_cells'])
                elapsed=now-anchor[2]
                if distance>0 and elapsed>.2 and min(y for x,y in state['active_cells'])>=8:
                    self.fall_rate=max(self.fall_rate,distance/elapsed)
            else:self.fall_anchor=(signature,state['active_cells'],now)
        self.game_mode=state['game_mode']
        self.palette=state["palette"];self.latest=state;self.last_image=image;self.observed_at=now
        self.capture_seconds+=time.perf_counter()-started;self.capture_count+=1
        return state,image

    def wait_for(self, predicate, expected_board=None, timeout=2,abort_if=None):
        started=time.perf_counter();end=started+timeout
        last_error=None
        while time.perf_counter()<end:
            try:
                state,image=self.observe(expected_board)
                if abort_if and abort_if(state):raise PlanningFailure('当前块已自然锁定，PC 断链；按恢复选项清场重试。')
                if predicate(state):return state,image
            except ValueError as exc:
                last_error=exc
                if self.animation_pending:end=max(end,started+30)
            time.sleep(.005 if self.speed()['burst'] else .025)
        raise RuntimeError("画面未与预测状态对齐，已停止。"+(str(last_error) if last_error else ""))

    def send(self, action, duration_ms=None):
        self.before_input(action)
        started=time.perf_counter()
        pressed_ms=self.speed()['tap_ms'] if duration_ms is None else duration_ms
        tap(self.hwnd,action,self.keys,duration=pressed_ms/1000,gap=0,cancelled=self.stopped)
        self.input_released=time.perf_counter()
        self.input_trace.append({'action':action,'started':started,'released':self.input_released,
                                 'interval_ms':self.interval_ms(),'tap_ms':pressed_ms})

    def send_wall(self,action):
        self.before_input(action);started=time.perf_counter()
        duration=(self.profile['handling']['das']+self.profile['handling']['dcd'])/60+(.025 if self.speed()['speed_preset']=='extreme' else .05)
        tap(self.hwnd,action,self.keys,duration=duration,gap=0,cancelled=self.stopped)
        self.input_released=time.perf_counter()
        self.input_trace.append({'action':action+'_wall','started':started,'released':self.input_released,
                                 'interval_ms':self.interval_ms(),'duration':duration})

    def confirm_preview(self,known,current,board,held):
        end=time.perf_counter()+4;previous=None;since=0
        while time.perf_counter()<end:
            if self.speed()['burst'] and self.latest and time.perf_counter()-self.observed_at<.1:
                state,image=self.latest,self.last_image
            else:state,image=self.observe(board)
            revealed={current:state["active"]}
            revealed.update({current+i+1:p for i,p in enumerate(state["next"])})
            valid=(state["board"]==board and state["active"] is not None and
                   state["hold"]==held and len(state["next"])==self.preview_count and observation_consistent(known,revealed))
            signature=(state["active"],state["hold"],state["next"]) if valid else None
            now=time.perf_counter()
            if signature is not None and self.speed()['preview_stable_ms']==0:return state,revealed
            if signature is not None and signature==previous and now-since>=.15:
                return state,revealed
            if signature!=previous:previous=signature;since=now
            time.sleep(.03)
        image.save(self.folder/"preview-mismatch.png")
        (self.folder/"preview-mismatch.json").write_text(json.dumps(
            {"current":current,"previously_known":known,"actual":revealed,'state':state},indent=2),encoding="utf-8")
        raise RuntimeError("实际 Next 未与七袋规则及之前的稳定识别对齐，已停止。")

    def soft_drop(self, target, board):
        self.before_input()
        self.intentional_drop=True
        key_event(self.hwnd,"down",True,self.keys)
        try:
            observed=self.wait_for(lambda state:set(map(tuple,state["active_cells"]))==set(target),board,timeout=5)
        finally:
            key_event(self.hwnd,"down",False,self.keys)
            self.input_released=time.perf_counter()
            self.intentional_drop=False;self.fall_anchor=None
        return observed

    def verify_movement(self, action, previous, target, board):
        try:
            self.wait_for(lambda s:falls_to(board,'?',target,s['active_cells']),board,timeout=.5)
        except RuntimeError:
            state,_=self.observe(board)
            # The client's colored PERFECT CLEAR text briefly overlays the
            # board after a clear. Wait without sending another input until
            # a clean frame separates the active piece from the locked field.
            if state["board"]!=board or len(state["active_cells"])!=4:
                state,_=self.wait_for(lambda s:s["board"]==board and len(s["active_cells"])==4,
                                      board,timeout=4)
            if falls_to(board,'?',target,state['active_cells']):return
            if state["board"]!=board or not falls_to(board,'?',previous,state['active_cells']):
                (self.folder/"movement-mismatch.json").write_text(json.dumps(
                    {"action":action,"previous":previous,"target":target,
                     "actual_cells":state["active_cells"],"board_matches":state["board"]==board},indent=2),encoding="utf-8")
                raise RuntimeError("方块出现意外移动，已停止；没有重复发送按键。")
            # A fresh frame proves the first input did not move the piece.
            # Retry once, accommodating entry/clear animation input timing.
            self.send(action)
            self.wait_for(lambda s:falls_to(board,'?',target,s['active_cells']),board,timeout=2)

    def tuck_suffix(self,board,piece,pose,route,step,expected_next):
        """Execute a verified sonic-drop/tuck before lock delay expires.

        Only instant soft drop profiles qualify. The final pose/projection
        is read again before locking; the whole locked board is verified.
        """
        if self.interval_ms()>100:raise PlanningFailure('有限锁定延迟下旋入需要操作间隔不超过 100ms。')
        actions=route['actions'][:-1];predicted=[];current=pose
        for action in actions:
            current=advance_pose(board,piece,current,action,self.kicks);predicted.append((action,current))
        if set(dropped_cells(board,piece,current))!=set(map(tuple,step['cells'])):
            raise RuntimeError('旋入组合未通过落点校验。')
        for action,current in predicted:
            self.send('down' if action=='soft_drop' else action)
            step['execution_progress'].append({'action':action,'predicted_pose':current,'tuck_combination':True})
        try:
            state,_=self.wait_for(lambda s:s['board']==board and s['active']==piece and s['next']==expected_next and
                                 any(set(dropped_cells(board,piece,p))==set(map(tuple,step['cells']))
                                     for p in poses_for(piece,s['active_cells'])),board,timeout=.5)
        except RuntimeError as exc:
            if self.fall_rate and self.latest and self.latest['next']!=expected_next:
                raise PlanningFailure('旋入期间发生自然锁定，当前 PC 已断链。') from exc
            raise
        self.send('hard_drop')
        return actions+['hard_drop']

    def burst_piece(self,state,step,before,after_hold):
        """Simulate the entire route, then verify its projection before lock."""
        piece=step['piece'];used_hold=step['hold_used']
        if used_hold:
            pose=(4,21,0)
            expected_next=state['next'][1:] if state['hold'] is None else state['next']
        else:
            poses=poses_for(piece,state['active_cells'])
            if not poses:raise PlanningFailure('当前块无法定位，未发送动作组合。')
            pose=next((p for p in poses if p[2]==0),poses[0]);expected_next=state['next']
        try:route=preferred_route(before,piece,step['cells'],self.kicks,pose)
        except ValueError as exc:raise PlanningFailure('当前块已下落，当前高度无法到达 PC 落点。') from exc
        actions=route['actions'][:-1]
        if 'soft_drop' in actions and (not self.profile or self.profile['handling']['sdf']!=41):return None
        predicted=[];current=pose
        for action in actions:
            current=advance_pose(before,piece,current,action,self.kicks);predicted.append((action,current))
        if set(dropped_cells(before,piece,current))!=set(map(tuple,step['cells'])):
            raise RuntimeError('动作组合落点校验失败，未发送按键。')
        if used_hold:self.send('hold')
        for action,current in predicted:
            self.send('down' if action=='soft_drop' else action)
            step['execution_progress'].append({'action':action,'predicted_pose':current,'burst':True})
        if not self.speed().get('projection_check',True) and 'soft_drop' not in actions and pose[1]>8:
            # Air-only routes have already passed SRS simulation. Sprint
            # verifies the resulting entire board after this single lock.
            # Surface tucks and low pieces retain the pre-lock image check.
            self.send('hard_drop');step['lock_verification']='after_lock_air_only'
            return actions+['hard_drop'],[pose,current]
        time.sleep(.012)  # Let the client render queued key events before capture.
        try:
            observed,_=self.wait_for(lambda s:s['board']==before and s['active']==piece and s['hold']==after_hold and
                    s['next'].startswith(expected_next) and any(set(dropped_cells(before,piece,p))==set(map(tuple,step['cells']))
                    for p in poses_for(piece,s['active_cells'])),before,timeout=4 if self.completed_pcs and before==empty_board() else .6,
                    abort_if=lambda s:self.fall_rate>0 and s['active'] not in (None,piece) and s['hold']==after_hold and
                            s['preview_count']==self.preview_count and not s['next'].startswith(expected_next) and s['board']!=before)
        except PlanningFailure:raise
        except RuntimeError:
            (self.folder/'burst-mismatch.json').write_text(json.dumps({'piece':piece,'target':step['cells'],
                'actions':actions,'actual':self.latest},ensure_ascii=False,indent=2),encoding='utf-8')
            return self.repair_burst(before,piece,step,expected_next,after_hold,actions,pose)
        self.send('hard_drop')
        return actions+['hard_drop'],[pose,poses_for(piece,observed['active_cells'])[0]]

    def repair_burst(self,board,piece,step,expected_next,held,actions,start):
        """Replan from a clean observed pose; never replay the blind burst."""
        try:
            state,_=self.wait_for(lambda s:s['board']==board and s['active']==piece and s['hold']==held and
                                 s['next'].startswith(expected_next) and len(s['active_cells'])==4,board,timeout=4)
        except RuntimeError as exc:
            latest=self.latest
            if latest and latest['hold']==held and not latest['next'].startswith(expected_next) and latest['board']!=board:
                raise PlanningFailure('动作期间当前块已锁定、Next 已推进，当前 PC 断链；按恢复选项清场重试。') from exc
            raise RuntimeError('快速操作后未能读取稳定的当前块，已停止，未发送硬降。') from exc
        corrected=[];observed=[start]
        for _ in range(16):
            poses=poses_for(piece,state['active_cells'])
            if not poses:raise RuntimeError('无法定位快速组合后的当前块，未发送硬降。')
            pose=poses[0];observed.append(pose)
            try:route=preferred_route(board,piece,step['cells'],self.kicks,pose)
            except ValueError as exc:raise PlanningFailure('当前块已下落，补正路线无法到达 PC 落点。') from exc
            action=route['actions'][0]
            if action=='hard_drop':
                step['burst_repaired']=True;step['correction_actions']=corrected
                self.send('hard_drop',duration_ms=24)
                return actions+corrected+['hard_drop'],observed
            target=advance_pose(board,piece,pose,action,self.kicks)
            self.send('down' if action=='soft_drop' else action,duration_ms=24)
            corrected.append(action)
            state,_=self.wait_for(lambda s:s['board']==board and s['active']==piece and s['hold']==held and
                    s['next'].startswith(expected_next) and falls_to(board,piece,cells(piece,target[2],target[0],target[1]),s['active_cells']),board,timeout=2)
        raise RuntimeError('动作补正次数超限，未发送硬降。')

    def execute(self, step, expected_active, expected_hold, after_active=None, after_hold=None, after_next=None,expected_next=None):
        self.pace_piece();execute_started=time.perf_counter()
        capture_start=self.capture_count
        self.pending_step=step;step['execution_progress']=[]
        trace_start=len(self.input_trace)
        before=tuple(step["board_before"])
        self.reference_board=before
        try:
            matches=lambda s:s["board"]==before and s["active"]==expected_active and s["hold"]==expected_hold and (expected_next is None or s['next'].startswith(expected_next))
            if self.speed()['burst'] and self.latest and time.perf_counter()-self.observed_at<.15 and matches(self.latest):state=self.latest
            else:state,_=self.wait_for(matches,before,timeout=2)
        except RuntimeError as exc:
            if self.fall_rate and self.latest and self.latest['board']!=before:
                raise PlanningFailure('规划期间发生自然锁定，当前 PC 已断链。') from exc
            raise
        burst=self.burst_piece(state,step,before,after_hold) if self.speed()['burst'] else None
        if burst is not None:actual_actions,observed_poses=burst
        else:
            if step["hold_used"]:
                self.send("hold")
                state,_=self.wait_for(lambda s:s["active"]==step["piece"] and s['hold']==after_hold,before)
            executing_next=state['next']
            piece=step["piece"]
            actual_actions=[];observed_poses=[];rotation_hint=0;ground_observation=None
            for _ in range(50):
                if self.stopped():raise InterruptedError("已停止自动操作。")
                self.before_input()
                try:
                    if ground_observation is not None:
                        state,_=ground_observation;ground_observation=None
                    else:state,_=self.wait_for(lambda s:s['board']==before and s['active']==piece and s['next']==executing_next,before)
                except RuntimeError as exc:
                    if self.fall_rate and self.latest and self.latest['next']!=executing_next:
                        raise PlanningFailure('移动前当前块已自然锁定，当前 PC 已断链。') from exc
                    raise
                poses=poses_for(piece,state['active_cells'])
                if not poses:raise PlanningFailure('重力下当前块无法定位，已断链。')
                pose=next((p for p in poses if p[2]==rotation_hint),poses[0])
                x,y,rotation=pose;rotation_hint=rotation
                observed_poses.append(pose)
                try:route=preferred_route(before,piece,step['cells'],self.kicks,pose)
                except ValueError as exc:raise PlanningFailure('方块已下落，当前高度无法到达 PC 落点。') from exc
                action=route['actions'][0]
                step['execution_progress'].append({'pose':pose,'action':action,'active':state['active'],
                                                    'hold':state['hold'],'next':state['next']})
                grounded=not fits(before,cells(piece,rotation,x,y-1))
                if ((grounded or action=='soft_drop') and action!='hard_drop' and self.profile and self.profile['handling']['sdf']==41):
                    actual_actions.extend(self.tuck_suffix(before,piece,pose,route,step,executing_next))
                    break
                if action=="hard_drop":
                    if set(dropped_cells(before,piece,pose))!=set(map(tuple,step['cells'])):
                        raise PlanningFailure('当前投影与 PC 落点不符，未锁定。')
                    self.send(action)
                    actual_actions.append(action)
                    break
                previous=cells(piece,rotation,x,y)
                if action in ("left","right"):
                    direction=-1 if action=='left' else 1
                    run=0
                    for next_action in route['actions']:
                        if next_action!=action:break
                        run+=1
                    wall=x
                    while fits(before,cells(piece,rotation,wall+direction,y)):wall+=direction
                    if (self.profile and self.profile['handling']['arr']==0 and run>=3 and wall==x+direction*run):
                        x=wall;self.send_wall(action)
                        action_record=action+'_wall'
                    else:x+=direction;self.send(action);action_record=action
                elif action in ("cw","ccw"):
                    nr=(rotation+(1 if action=="cw" else -1))%4
                    key=piece+"."+"NESW"[rotation]+"NESW"[nr]
                    for dx,dy in self.kicks[key]:
                        if fits(before,cells(piece,nr,x+dx,y+dy)):
                            x,y,rotation=x+dx,y+dy,nr;break
                    else:raise RuntimeError("计划中存在不可执行的旋转。")
                    self.send(action)
                elif action=="soft_drop":
                    while fits(before,cells(piece,rotation,x,y-1)):y-=1
                    ground_observation=self.soft_drop(cells(piece,rotation,x,y),before)
                elif action=="down":
                    raise RuntimeError("实时方案包含不可靠的半空单格软降，已停止。")
                else:raise RuntimeError("未知操作动作。")
                target=cells(piece,rotation,x,y)
                actual_actions.append(action_record if action in ('left','right') else action);rotation_hint=rotation
                if action in ("left","right","cw","ccw"):
                    self.verify_movement(action,previous,target,before)
                elif ground_observation is None:
                    self.wait_for(lambda s:set(map(tuple,s["active_cells"]))==set(target),before)
            else:raise PlanningFailure('移动次数超限，当前 PC 无法完成。')
        step.update(actions=actual_actions,observed_poses=observed_poses)
        expected=tuple(step["board_after"])
        self.reference_board=expected
        if burst is not None:time.sleep(.012)
        state,image=self.wait_for(lambda s:s["board"]==expected and s["active"] is not None and
                                  (after_active is None or s["active"]==after_active) and
                                  s["hold"]==after_hold and
                                  (after_next is None or s["next"]==after_next[:len(s["next"])]),expected,timeout=3)
        self.steps.append(step)
        now=time.perf_counter();self.lock_times.append(now)
        step['execution_seconds']=round(now-execute_started,6)
        step['capture_count']=self.capture_count-capture_start
        step['locked_at_seconds']=round(now-self.play_started,6)
        self.execution_seconds+=now-execute_started
        step['input_timing']=self.input_trace[trace_start:]
        self.cleared+=len(step["cleared_rows"])
        if all(row=="__________" for row in expected):
            self.completed_pcs+=1
            image.save(self.folder/f"pc-{self.completed_pcs:03d}.png")
        self.write_status("running", "本块落地已核对。")
        self.pending_step=None
        return state

    def status_data(self,status,message):
        data={"status":status,"message":message,"completed_cycles":self.completed_cycles,
              "cycle_mode":self.request.get('cycle_mode','dpc'),
              "mode":"seeded" if self.request.get("live_mode")=="seeded" else "visible",
              "uses_fixed_seed":self.request.get("live_mode")=="seeded",
              "control_profile":self.profile,"gravity_tracking":True,
              "game_mode":self.game_mode,
              "observed_fall_rate":round(self.fall_rate,3),
              "operation_interval_ms":self.interval_ms(),"rotation_rules":"SRS+90" if self.kick_path!=KICKS else "SRS90",
              "speed_preset":self.speed()['speed_preset'],"speed_metrics":self.speed_metrics(),
              "geometry":self.geometry.to_dict() if self.geometry else None,"capture_region":self.capture_region,
              "vision_fallbacks":self.vision_fallbacks,
              "animation_waits":self.animation_waits,
              "completed_pcs":self.completed_pcs,"placed_pieces":len(self.steps),
              "cleared_lines":self.cleared,"steps":self.steps,"output_directory":str(self.folder)}
        return data

    def write_status(self,status,message):
        data=self.status_data(status,message)
        if 'live_metrics' in self.request:self.request['live_metrics'].update(data['speed_metrics'])
        (self.folder/"session.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        self.progress("running" if status=="running" else status,
                      f"循环 {self.completed_cycles} · PC {self.completed_pcs} · {len(self.steps)} 块 · {self.cleared} 行 · 实际 {data['speed_metrics']['overall_pps']:.2f} PPS。{message}")
        return data

    def speed_metrics(self):
        elapsed=time.perf_counter()-self.play_started if self.play_started is not None else 0
        locks=self.lock_times
        recent=(len(locks[-10:])-1)/(locks[-1]-locks[-10:][0]) if len(locks)>1 else 0
        peak=max((5/(locks[i]-locks[i-5]) for i in range(5,len(locks))),default=0)
        return dict(target_pps=self.speed()['target_pps'],overall_pps=round(len(locks)/elapsed,3) if elapsed else 0,
                    execution_pps=round(len(locks)/self.execution_seconds,3) if self.execution_seconds else 0,
                    recent_pps=round(recent,3),peak_5_piece_pps=round(peak,3),elapsed_seconds=round(elapsed,3),
                    capture_ms=round(self.capture_seconds*1000/self.capture_count,2) if self.capture_count else 0)

    def run_seeded(self):
        focus(self.hwnd)
        if self.request.get("restart"):
            self.observe()  # Only retry after recognizing an actual game board.
            tap(self.hwnd,"retry",self.keys,duration=3,gap=.2,cancelled=self.stopped)
        seed=int(self.request.get("seed",1234))
        max_cycles=int(self.request.get("max_cycles",0))
        if max_cycles<0 or max_cycles>1000:raise ValueError("循环次数应为 0（持续）至 1000。")
        queue=seeded_queue(seed,35035)
        current,held_source=0,None
        startup_deadline=time.perf_counter()+10
        while True:
            try:
                self.geometry=None
                state,image=self.observe()
                if state["active"] is not None and state["hold"] is None and state["board"]==empty_board():
                    break
            except ValueError:
                pass
            if time.perf_counter()>startup_deadline:raise RuntimeError("等待练习倒计时结束超时。")
            time.sleep(.1)
        if state["active"]!=queue[0] or state["next"]!=queue[1:1+len(state["next"])]:
            raise ValueError(f"画面块序 {state['active']+state['next']} 与种子期望 {queue[:1+len(state['next'])]} 不匹配。请从相同种子的单人自定义空场开始。")
        if state["hold"] is not None or state["board"]!=empty_board():
            raise ValueError("请从初始空棋盘、空 Hold 开始。")
        image.save(self.folder/"start.png")
        self.write_status("running", "已核对固定种子与当前块、全部可见 Next。")
        while not max_cycles or self.completed_cycles<max_cycles:
            cycle_start=self.completed_cycles*35;cycle_end=cycle_start+35
            used=[]
            for stage_number,lines in enumerate((4,4,6),1):
                self.progress("running",f"第 {self.completed_cycles+1} 循环第 {stage_number} 段，正在求解 {lines} 行 PC…")
                held=queue[held_source] if held_source is not None else None
                plan=(seeded_dpc(queue,current,held_source,cycle_start,cycle_end,self.stopped) if stage_number==3 else
                      find_pc(queue[current:cycle_end],hold=held,lines=lines,mode="soft",
                              path_mode="instant",timeout=25,cancelled=self.stopped))
                if plan["status"]!="solved":raise RuntimeError(plan["message"])
                base=current
                for local in plan["steps"]:
                    before=base+local["queue_index_before"]
                    expected_hold=queue[held_source] if held_source is not None else None
                    placed_source=before
                    if local["hold_used"]:
                        if held_source is None:
                            placed_source=before+1;held_source=before
                        else:
                            placed_source,held_source=held_source,before
                    current=base+local["queue_index_after"]
                    if not cycle_start<=placed_source<cycle_end:
                        raise RuntimeError("当前循环使用了边界外的方块。")
                    after_hold=queue[held_source] if held_source is not None else None
                    step=dict(local,source_index=placed_source,stage=stage_number,cycle=self.completed_cycles+1,
                              hold_before=expected_hold,hold_after=after_hold,
                              global_queue_index_before=before,global_queue_index_after=current)
                    self.execute(step,queue[before],expected_hold,queue[current],after_hold,queue[current+1:current+7])
                    used.append(placed_source)
            if sorted(used)!=list(range(cycle_start,cycle_end)):
                raise RuntimeError("循环的五包来源校验失败。")
            if self.completed_pcs!=3*(self.completed_cycles+1):
                raise RuntimeError("未严格保持每轮三个全清，已停止。")
            self.completed_cycles+=1
            self.write_status("running","完整的 4＋4＋6 与五包来源已核对。")
        return self.write_status("done","已完成指定循环次数。")

    def run_visible(self):
        stage_lines,cycle_size=cycle_spec(self.request.get('cycle_mode','dpc'))
        focus(self.hwnd)
        if self.request.get("restart"):
            self.restart_current()
        resume=None
        if self.request.get('resume_from_recording'):
            source=Path(self.request['resume_from_recording']).resolve()
            if not source.is_relative_to((ROOT/'output').resolve()):raise ValueError('只能继续本项目内的实机记录。')
            resume=json.loads((source/'session.json').read_text(encoding='utf-8'))
            if not resume.get('steps'):raise ValueError('该记录没有已验证的落地。')
            original=read_state(Image.open(source/'start.png'))
            self.geometry=Geometry(**original['geometry'])
            board=tuple(resume['steps'][-1]['board_after'])
            state,image=self.observe(board)
            if state['board']!=board or set(map(tuple,state['active_cells']))!=set(cells(state['active'],0,4,21)):
                raise RuntimeError('当前棋盘或出生方块不符合停止记录，未发送按键。')
            if state['hold']!=resume['steps'][-1]['hold_after']:
                raise RuntimeError('当前 Hold 与停止记录不同，未发送按键。')
            self.steps=list(resume['steps']);self.completed_cycles=resume['completed_cycles']
            self.completed_pcs=resume['completed_pcs'];self.cleared=resume['cleared_lines']
            self.preview_count=len(state['next'])
        else:
            state,image=self.initial_state()
        rotation=self.request.get('rotation_rules','SRS+')
        if rotation not in ('SRS','SRS+'):raise ValueError('实时旋转规则须为 SRS 或 SRS+。')
        if state['game_mode']=='zen' or rotation=='SRS+':
            self.kick_path=ROOT/'data/srsplus90.properties'
            self.kicks=load_kicks(self.kick_path)
        current=1 if state["hold"] is not None else 0
        held_source=0 if state["hold"] is not None else None
        known={current:state["active"]}
        if held_source is not None:known[held_source]=state["hold"]
        known.update({current+i+1:p for i,p in enumerate(state["next"])})
        if resume:
            current=1 if original['hold'] else 0;held_source=0 if original['hold'] else None
            known={current:original['active']}
            if held_source is not None:known[held_source]=original['hold']
            known.update({current+i+1:p for i,p in enumerate(original['next'])})
            for previous in self.steps:
                known[previous['source_index']]=previous['piece']
                if previous['hold_used']:held_source=previous['global_queue_index_before']
                current=previous['global_queue_index_after']
                if previous.get('observed_active_after'):
                    known[current]=previous['observed_active_after']
                    known.update({current+i+1:p for i,p in enumerate(previous['observed_next_after'])})
            observed,revealed=self.confirm_preview(known,current,board,state['hold'])
            known.update(revealed)
        hold_available=state.get("hold_available",True)
        board=tuple(resume['steps'][-1]['board_after']) if resume else empty_board()
        max_cycles=int(self.request.get("max_cycles",0));samples=int(self.request.get("forecast_samples",8))
        max_pcs=int(self.request.get('max_pcs',0))
        if not 0<=max_pcs<=7000:raise ValueError('PC 次数应为 0 至 7000。')
        if not 0<=max_cycles<=1000:raise ValueError("循环次数应为 0（持续）至 1000。")
        if not 1<=samples<=32:raise ValueError("预览采样数须为 1 至 32。")
        image.save(self.folder/"start.png")
        while (not max_cycles or self.completed_cycles<max_cycles) and (not max_pcs or self.completed_pcs<max_pcs):
            cycle_start=self.completed_cycles*cycle_size;cycle_end=cycle_start+cycle_size
            past=[s for s in self.steps if s['cycle']==self.completed_cycles+1] if resume else []
            used=[s['source_index'] for s in past]
            for number,lines in enumerate(stage_lines,1):
                if past and number<past[-1]['stage']:continue
                stage_past=[s for s in past if s['stage']==number]
                remaining=lines-sum(len(s['cleared_rows']) for s in stage_past);placed=len(stage_past)
                prefix=None
                if not stage_past and lines==4 and self.request.get('use_best_fields',True):
                    choices=field_setups(known,current,held_source,number,self.kicks,self.stopped,hold_available)
                    if choices:prefix=choices[0]
                if not prefix:
                    prefix=(pco_setup(known,current,held_source,cycle_start,self.stopped,hold_available,self.kicks) if number==1 else
                            dpc_setup(known,current,held_source,cycle_start,self.stopped,self.kicks) if lines==6 else None)
                # If the standard opener forces I into the first bag, its
                # coverage is lower. Use adaptive search for those orders.
                if number==1 and prefix and len(prefix)==7 and hold_available:
                    prefix=None
                prefix=list(prefix or [])
                if stage_past:prefix=[]
                while remaining:
                    self.progress("running",f"读取可见 Next，第 {self.completed_cycles+1} 循环第 {number} 段，剩余 {remaining} 行…")
                    if not prefix:
                        state,_=self.observe(board)
                        poses=poses_for(state['active'],state['active_cells']) if state['active'] else []
                        budget=None
                        if self.fall_rate and poses:
                            drop=dropped_cells(board,state['active'],poses[0])
                            distance=min(y for x,y in state['active_cells'])-min(y for x,y in drop)
                            budget=max(.3,min(15,distance/self.fall_rate-2))
                        prefix=choose_plan(known,current,held_source,board,remaining,cycle_end,samples,self.stopped,
                                           hold_available=hold_available,kick_path=self.kick_path,time_budget=budget,persistent=self.speed()['burst'])
                    local=dict(prefix.pop(0))
                    local["queue_index_after"]-=local["queue_index_before"]
                    local["queue_index_before"]=0
                    before=current;expected_hold=known[held_source] if held_source is not None else None
                    source=before
                    if local["hold_used"]:
                        if held_source is None:source=before+1;held_source=before
                        else:source,held_source=held_source,before
                    current+=local["queue_index_after"]
                    after_hold=known[held_source] if held_source is not None else None
                    step=dict(local,source_index=source,stage=number,cycle=self.completed_cycles+1,
                              hold_before=expected_hold,hold_after=after_hold,
                              global_queue_index_before=before,global_queue_index_after=current)
                    actual_next=''.join(known[i] for i in range(before+1,before+1+self.preview_count) if i in known)
                    self.execute(step,known[before],expected_hold,known.get(current),after_hold,expected_next=actual_next)
                    board=tuple(local["board_after"])
                    observed,revealed=self.confirm_preview(known,current,board,after_hold)
                    hold_available=observed.get("hold_available",True)
                    known.update(revealed)
                    step.update(observed_active_after=observed["active"],observed_next_after=observed["next"])
                    remaining-=len(local["cleared_rows"]);placed+=1;used.append(source)
                    if all(row=="__________" for row in board) and remaining:
                        raise PlanningFailure("提前出现全清，未保持所选循环节奏，已断链。")
                if placed!=lines*10//4:raise RuntimeError("本段放置块数不符合循环。")
                if max_pcs and self.completed_pcs>=max_pcs and number<len(stage_lines):
                    return self.write_status('done','已完成指定 PC 次数；未完成的循环不计数。')
            if sorted(used)!=list(range(cycle_start,cycle_end)):raise RuntimeError("循环的七袋来源校验失败。")
            self.completed_cycles+=1
            resume=None
            self.write_status("running","可见 Next 模式完成一个循环。")
        return self.write_status("done","已完成指定循环次数。")

    def run(self):
        self.hotkeys=EmergencyKeys()
        try:
            if self.request.get('live_mode')=='seeded' and self.request.get('cycle_mode','dpc')!='dpc':
                raise ValueError('纯四行循环使用可见 Next 模式，不接受固定种子执行。')
            return self.run_seeded() if self.request.get("live_mode")=="seeded" else self.run_visible()
        except Exception as exc:
            if self.pending_step:
                (self.folder/'unfinished-step.json').write_text(json.dumps(self.pending_step,ensure_ascii=False,indent=2),encoding='utf-8')
            if getattr(self,'pending_lock_image',None) is not None:
                self.pending_lock_image.save(self.folder/'before-hard-drop.png')
            try:capture(self.hwnd).save(self.folder/"stopped.png")
            except Exception:pass
            self.write_status("cancelled" if isinstance(exc,InterruptedError) else
                              "retrying" if isinstance(exc,PlanningFailure) and (self.request.get("auto_retry") or self.recovery_permitted()) else "error",str(exc))
            raise
        finally:
            self.hotkeys.close()
            if self.owns_control_lock:self.control_lock.close()
            close_capture()
            from .search_worker import close_worker
            close_worker()


def connect_game(request,progress,cancelled):
    try:return find_game()
    except GameNotFound:
        if not request.get("launch_game"):raise
    exe=ROOT/"tetrio-desktop/TETR.IO.exe"
    if not exe.is_file():raise RuntimeError("项目中的 TETR.IO.exe 不存在。")
    subprocess.Popen([str(exe)],cwd=exe.parent)
    progress("running","正在打开 TETR.IO，进入随机自定义练习后会自动开始。")
    end=time.perf_counter()+30
    while time.perf_counter()<end:
        if cancelled() or emergency_pressed():raise InterruptedError("已停止等待游戏。")
        try:return find_game()
        except GameNotFound:time.sleep(.2)
    raise RuntimeError("未找到 TETR.IO 窗口，请打开本项目内的客户端。")


def run_live(request, progress=lambda *_:None, cancelled=lambda:False):
    request=dict(request)
    if request.get('farm_enabled'):
        from .farm_live import run_farm
        return run_farm(request,progress,cancelled)
    max_retries=int(request.get("max_retries",3))
    recovering=bool(request.get('recover_on_failure'))
    if not 0<=max_retries<=(1000 if recovering else 20):raise ValueError("恢复次数须为 0 至 1000。")
    failures=[]
    while True:
        if request.get('cycle_mode')=='blitz':
            from .blitz_live import BlitzRunner
            runner=BlitzRunner(request,progress,cancelled)
        else:runner=Runner(request,progress,cancelled)
        try:
            result=runner.run()
            result["previous_attempts"]=failures
            result['recovery_count']=len(failures)
            (runner.folder/'session.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            return result
        except PlanningFailure:
            if runner.latest and runner.latest.get("game_mode")=="zen" and not recovering:
                message="ZEN 当前无法继续 PC，已停止并保留进度；不会自动重开。"
                runner.write_status("error",message)
                raise PlanningFailure(message)
            unlimited=recovering and max_retries==0
            if (not (request.get("auto_retry") or recovering) or (not unlimited and len(failures)>=max_retries) or
                    cancelled() or runner.stopped()):raise
            failures.append({"directory":str(runner.folder),"completed_cycles":runner.completed_cycles,
                             "completed_pcs":runner.completed_pcs,"placed_pieces":len(runner.steps)})
            request["restart"]=True
            request.pop('resume_from_recording',None)
            progress("running",f"第 {len(failures)} 次断链，正在清场 / 重开随机练习；历史记录已保留。")
