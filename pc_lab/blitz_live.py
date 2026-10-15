"""Dedicated single-player Blitz score bot."""
import json
import time

from .live import Runner
from .engine import empty_board,poses_for,load_kicks,cells,dropped_cells
from .blitz import Score,ground_locks,ground_action,raw_ground_action,settle,score_move,BLITZ_OPTIONS,air_route,gravity
from .best_fields import field_setups
from .online import choose_plan,PlanningFailure,observation_consistent,resolve_observed_hold
from .config import GUIDELINE,WASD,key_code
from .windows import focus,key_event
from .solver import ROOT
from .finesse import estimated_faults,input_cost
from .blitz_finish import improve_finish,promote_spin


class BlitzRunner(Runner):
    def speed(self):
        result=super().speed()
        pulse=self.request.get('blitz_pulse_ms')
        if pulse is None and self.request.get('finesse_policy','throughput')=='throughput':pulse=0
        if pulse is not None and result['speed_preset']=='extreme':result['tap_ms']=float(pulse)
        return result

    def __init__(self,request,*args,**kwargs):
        # Reject invalid jobs before Runner connects, focuses, or launches
        # the client. Farming uses the same preflight before menu input.
        from .blitz_validation import validate_blitz
        from .config import load_profile
        validate_blitz(request,load_profile(request.get('config_path')))
        super().__init__(request,*args,**kwargs)
        profile=self.request.get('simulation_profile','blitz')
        self.score_state=Score(level=15 if profile=='level15' else int(self.request.get('blitz_start_level',1)),
                               level_cap=15 if profile=='level15' else None)
        self.pc_searches=0;self.pc_timeouts=0;self.score_fallbacks=0
        self.visible_finish_stats=dict(probes=0,plans=0,incomplete=0)
        self.ground_corrections=0;self.prefix=[];self.plan_times=[]
        self.pc_remaining=4;self.stage=0;self.simulation=self.request.get('simulation_profile','blitz')
        self.pc_boundaries=[]
        self.cycle_evidence=dict(verified_cycles=0,current_consecutive_cycles=0,maximum_consecutive_cycles=0,cycles=[])
        self.blitz_strategy=self.request.get('blitz_strategy','pc')
        self.finesse_policy=self.request.get('finesse_policy','throughput')
        from .farm_policy import FarmPolicy
        self.farm_policy=FarmPolicy.from_request(self.request) if self.request.get('farm_enabled') else None
        if self.finesse_policy not in ('balanced','strict','adaptive','gravity','throughput'):raise ValueError('无法识别按键策略。')
        if self.blitz_strategy not in ('pc','dpc','opportunistic','score'):raise ValueError('无法识别 Blitz 得分策略。')
        self.uses_dpc=self.blitz_strategy in ('dpc','opportunistic','score')
        self.two_row_probes=0;self.two_row_plans=0;self.two_row_finishes=0
        self.estimated_finesse_faults=0
        self.finesse_refinements=0;self.last_finesse_refine=-1
        self.early_setup_finishes=0
        self.early_setup_probes=0
        self.kick_path=ROOT/'data/srsplus90.properties';self.kicks=load_kicks(self.kick_path)
        self.allow180=False;self.soft_held=False
        self.solver_warmed=False
        self.allow_wall=bool(self.profile and self.profile['handling']['arr']==0 and (self.speed()['speed_preset']=='extreme' or self.finesse_policy in ('strict','adaptive','gravity')))
        self.finesse_saved=0;self.wall_inputs=0;self.last_persisted=0
        self.air_placements=0
        try:
            from pathlib import Path
            raw=json.loads(Path(self.profile['path']).read_text(encoding='utf-8-sig'))
            controls=raw['controls'];style=controls['style']
            bindings=GUIDELINE if style=='guideline' else WASD if style=='wasd' else controls['custom']
            choices=bindings.get('rotate180',[])
            for code in choices:
                try:vk=key_code(code)
                except ValueError:continue
                if vk not in self.keys.values() and vk not in (0x77,0x1B):
                    self.keys['cw180']=vk;self.allow180=True;break
        except (ValueError,KeyError,OSError):pass

    def release_soft(self):
        if self.soft_held:
            key_event(self.hwnd,'down',False,self.keys);self.soft_held=False
        self.intentional_drop=False

    def send_ground_wall(self,action,board,piece,hold,expected_pose):
        """One held direction, released only after the sprite proves arrival.

        Fixed controller milliseconds cannot prove that the game actually
        processed a DAS charge. Never rotate or hard drop on that guess.
        """
        self.before_input(action);started=time.perf_counter()
        target=tuple(sorted(cells(piece,expected_pose[2],expected_pose[0],expected_pose[1])))
        confirmed=False
        try:
            key_event(self.hwnd,action,True,self.keys)
            # A multi-cell wall move cannot finish before the configured
            # DAS. Avoid repeated full captures competing with the client
            # during this unavoidable charge, then confirm actual arrival.
            first_check=started+(self.profile['handling']['das']+self.profile['handling']['dcd'])/60
            while time.perf_counter()<first_check:
                if self.stopped():raise InterruptedError('压墙期间已停止。')
                time.sleep(min(.005,max(0,first_check-time.perf_counter())))
            self.wait_for(lambda s:tuple(s['board'])==board and s['active']==piece and s['hold']==hold and
                          tuple(sorted(map(tuple,s['active_cells'])))==target,board,
                          timeout=max(.005,started+.22-time.perf_counter()),
                          abort_if=lambda s:tuple(s['board'])!=board or s['hold']!=hold or
                          s['active'] is not None and s['active']!=piece)
            confirmed=True
        finally:
            key_event(self.hwnd,action,False,self.keys)
            self.input_released=time.perf_counter()
            self.input_trace.append(dict(action=action+'_wall',started=started,released=self.input_released,
                interval_ms=self.interval_ms(),duration=self.input_released-started,
                wall_sprite_confirmed=confirmed,wall_target_cells=target))

    def confirm_ground_settle(self,board,piece,hold,pose):
        target=tuple(sorted(cells(piece,pose[2],pose[0],pose[1])))
        return self.wait_for(lambda s:tuple(s['board'])==board and s['active']==piece and s['hold']==hold and
            tuple(sorted(map(tuple,s['active_cells'])))==target,board,timeout=.16,
            abort_if=lambda s:tuple(s['board'])!=board or s['hold']!=hold or
            s['active'] is not None and s['active']!=piece)

    def effective_finesse_policy(self):
        if self.finesse_policy=='gravity':return 'strict' if self.actual_gravity()>=20 else 'balanced'
        return self.finesse_policy

    def standard_inputs_only(self):
        return self.effective_finesse_policy() in ('strict','adaptive')

    def search_path_mode(self):
        if self.effective_finesse_policy()=='throughput':return 'ground180plain' if self.allow180 else 'groundplain'
        return ('ground180' if self.allow180 else 'ground')+('fine' if self.standard_inputs_only() else '')

    def fault_allowance(self):
        policy=self.effective_finesse_policy()
        if policy in ('balanced','throughput'):return 999
        if policy=='strict':return 0
        # A 70-piece window permits one extra reference input, restricted
        # in choose() to a fully observed <=4-piece PC completion.
        start=len(self.steps)//70*70
        return max(0,1-sum(s.get('estimated_finesse_faults',0) for s in self.steps[start:]))

    def try_visible_setup_finish(self,state):
        """Replace a setup only when all pieces for an actual PC are visible.

        Public setups estimate ordinary coverage. Committing the entire
        setup can discard a different standard-input finish revealed after
        its first few pieces. This probe keeps the verified setup on timeout.
        """
        if not self.standard_inputs_only() or not self.request.get('early_setup_finish',False):return False
        if not self.prefix or self.prefix[0].get('strategy') not in ('pc_setup','pco_setup','dpc_setup'):return False
        board=tuple(state['board']);remaining=self.pc_remaining
        occupied=sum(c!='_' for row in board for c in row)
        missing=10*remaining-occupied
        if not occupied or missing<=0 or missing%4:return False
        required=missing//4
        queue=state['active']+state['next']
        if required>len(queue)+int(bool(state['hold'])):return False
        if any(row!='__________' for row in board[remaining:]):return False
        from .fast_solver import find_pc
        self.early_setup_probes=getattr(self,'early_setup_probes',0)+1
        try:
            proposal=find_pc(queue,rows=list(reversed(board[:remaining])),hold=state['hold'],lines=remaining,
                mode='soft',timeout=.03,persistent=True,save=False,kick_path=self.kick_path,
                path_mode=self.search_path_mode(),cancelled=self.stopped,allow_hold=state['hold_available'])
        except (TimeoutError,ValueError):return False
        if self.request.get('diagnostic_setup'):
            log=getattr(self,'setup_probe_diagnostics',[])
            if len(log)<6:log.append(dict(queue=queue,hold=state['hold'],rows=list(reversed(board[:remaining])),remaining=remaining,status=proposal['status'],required=required))
            self.setup_probe_diagnostics=log
        if proposal['status']!='solved' or not proposal['steps']:return False
        steps=proposal['steps']
        if tuple(steps[0]['board_before'])!=board or tuple(steps[-1]['board_after'])!=empty_board():return False
        if any(estimated_faults(s['piece'],s['cells'],s['actions']) for s in steps):return False
        self.prefix=[dict(s,strategy='pc_finish',early_visible_finish=True) for s in steps]
        self.early_setup_finishes+=1
        return True

    def initial_state(self):
        from .windows import emergency_pressed,user
        self.waiting_for_start=True
        self.progress('running','等待 CUSTOM 随机新局；就绪后立即接管高重力方块。')
        end=time.perf_counter()+float(self.request.get('start_timeout',120));seen_frames=0
        while time.perf_counter()<end:
            if self.cancelled() or emergency_pressed() or self.hotkeys.pressed.is_set():raise InterruptedError('已停止等待 CUSTOM。')
            if int(user.GetForegroundWindow() or 0)==self.hwnd:
                try:
                    state,image=self.observe(empty_board())
                    if not self.solver_warmed and not state['active'] and state['board']==empty_board() and len(state['next'])>=5:
                        # An offline PC fixture loads JVM classes during the
                        # countdown. It never supplies a game seed or move.
                        from .fast_solver import find_pc
                        try:find_pc('JLOSTZIJLO',lines=4,allow_hold=True,timeout=1.2,
                                    persistent=True,path_mode=self.search_path_mode(),save=False,kick_path=self.kick_path,cancelled=self.stopped)
                        except TimeoutError:pass
                        self.solver_warmed=True
                    if seen_frames<24:
                        with (self.folder/'initial-states.jsonl').open('a',encoding='utf-8') as out:
                            out.write(json.dumps(dict(active=state['active'],hold=state['hold'],next=state['next'],board=state['board']),ensure_ascii=False)+'\n')
                        if seen_frames%3==0 and not state['active']:image.save(self.folder/f'initial-{seen_frames:02d}.png')
                        seen_frames+=1
                    if not (self.folder/'initial-observation.json').exists():
                        (self.folder/'initial-observation.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
                        image.save(self.folder/'initial-observation.png')
                    visible=(state['hold'] or '')+(state['active'] or '')+state['next']
                    if state['board']==empty_board() and state['active'] and len(state['next'])>=5 and len(set(visible[:7]))==len(visible[:7]):
                        self.waiting_for_start=False;return state,image
                except ValueError as exc:
                    if self.geometry is not None and not (self.folder/'initial-recognition-error.txt').exists():
                        from .windows import capture
                        (self.folder/'initial-recognition-error.txt').write_text(str(exc),encoding='utf-8')
                        capture(self.hwnd).save(self.folder/'initial-recognition-error.png')
                    self.geometry=None
            # A valid countdown frame already calibrated the board. Reuse
            # its ROI so the first 20G sprite is observed before its 500ms
            # lock deadline; a recognition error still forces recalibration.
            time.sleep(.01 if self.geometry is not None else .03)
        raise RuntimeError('未等到 CUSTOM 随机空棋盘。')

    def ground_state(self,board,active=None,held=None,next_prefix=None):
        if not self.soft_held:
            self.before_input();key_event(self.hwnd,'down',True,self.keys);self.soft_held=True
            if self.speed()['speed_preset']!='extreme':time.sleep(.018)
        self.intentional_drop=True
        def matches(s):
            if s['board']!=board or not s['active'] or len(s['active_cells'])!=4:return False
            if active is not None and s['active']!=active:return False
            if held is not None and s['hold']!=held:return False
            if next_prefix is not None and not s['next'].startswith(next_prefix):return False
            return any(set(cells(s['active'],r,x,y))==set(map(tuple,s['active_cells']))
                       for x,y,r in [settle(board,s['active'],p) for p in poses_for(s['active'],s['active_cells'])])
        return self.wait_for(matches,board,timeout=.35)[0]

    def already_grounded(self,state):
        return bool(state['active'] and any(p==settle(state['board'],state['active'],p)
                    for p in poses_for(state['active'],state['active_cells'])))

    def actual_gravity(self):
        if self.simulation=='20g':return 20
        if self.simulation=='level10':return gravity(10)
        if self.simulation=='level15':return gravity(15)
        return gravity(self.score_state.level)

    def air_eligible(self,state,actions=None):
        if not self.allow_wall or self.actual_gravity()>=20 or len(state['active_cells'])!=4:return False
        height=max((y+1 for y,row in enumerate(state['board']) if row!='__________'),default=0)
        gap=min(y for x,y in state['active_cells'])-height
        if gap<6:return False
        # The old level<=8 cutoff forced sonic drop while Level9–13 still
        # offers some usable air time. Estimate the observed remaining
        # window and recheck it after planning, rather than trust a level.
        rate=max(60*self.actual_gravity(),getattr(self,'fall_rate',0))
        age=max(0,time.perf_counter()-self.observed_at) if getattr(self,'observed_at',0) else 0
        if actions is None:needed=.12
        else:
            speed=self.speed();needed=(speed.get('frame_wait_ms',18)/1000+.025+
                max(.025,self.capture_seconds/max(1,self.capture_count)))
            for action in actions:
                if action=='hard_drop':continue
                needed+=((self.profile['handling']['das']+self.profile['handling']['dcd'])/60+
                         (.025 if speed['speed_preset']=='extreme' else .05)) if action.endswith('_wall') else speed['tap_ms']/1000
        return gap/rate>age+needed

    def choose(self,state,known,current,held_source):
        policy=self.effective_finesse_policy()
        if getattr(self,'planning_finesse_policy',policy)!=policy:
            # A low-gravity PC prefix can contain costly later placements.
            # Replan from the actual field on crossing into 20G.
            self.prefix=[]
            self.gravity_policy_switches=getattr(self,'gravity_policy_switches',0)+1
        self.planning_finesse_policy=policy
        board=state['board'];held=state['hold'];active=state['active']
        poses=poses_for(active,state['active_cells']);start=poses[0]
        began=time.perf_counter();deadline=began+.095
        def check():
            if self.stopped():return True
            if time.perf_counter()>=deadline:raise TimeoutError('Blitz 本块规划预算已用完。')
            return False
        # A saved prefix only contains observed pieces, or a fully observed
        # independently verified PC finish. Forecasts commit ONE move only.
        self.try_visible_setup_finish(state)
        if self.prefix:
            step=resolve_observed_hold(self.prefix[0],state)
            self.prefix[0]=step
            piece=held or state['next'][0] if step['hold_used'] else active
            can_hold=not step['hold_used'] or state['hold_available']
            route_start=(4,21,0) if step['hold_used'] else start
            target=tuple(sorted(map(tuple,step['cells'])))
            reachable=ground_locks(board,piece,self.kicks,route_start,self.allow180,wanted=target,allow_wall=self.allow_wall)
            if (can_hold and piece==step['piece'] and tuple(step['board_before'])==board and target in reachable and
                    estimated_faults(piece,target,reachable[target]['actions'])<=self.fault_allowance()):
                if (policy!='throughput' and len(self.prefix)<=4 and len(self.steps)!=self.last_finesse_refine
                        and step.get('strategy') in ('pc_finish','pc_score_finish')
                        and estimated_faults(piece,target,reachable[target]['actions'])>0):
                    self.last_finesse_refine=len(self.steps)
                    from .fast_solver import find_pc
                    try:
                        proposal=find_pc(active+state['next'],rows=list(reversed(board[:self.pc_remaining])),
                            hold=held,lines=self.pc_remaining,mode='soft',timeout=.035,
                            persistent=True,save=False,kick_path=self.kick_path,path_mode=self.search_path_mode(),cancelled=self.stopped,
                            allow_hold=state['hold_available'])
                        if proposal['status']=='solved' and proposal['steps'][0].get('finesse_standard_finish'):
                            self.prefix=[dict(s,strategy='pc_finish') for s in proposal['steps']]
                            self.finesse_refinements+=1
                            return self.choose(state,known,current,held_source)
                    except (TimeoutError,ValueError):pass
                extra=0 if self.standard_inputs_only() else int(self.request.get('spin_extra_inputs',0))
                step=dict(self.prefix.pop(0));step.update(promote_spin(board,piece,target,self.kicks,reachable[target],self.allow180,self.allow_wall,extra_inputs=extra));return step
            self.prefix=[]
        occupied=sum(c!='_' for row in board for c in row)
        height=max((y+1 for y,row in enumerate(board) if row!='__________'),default=0)
        if not occupied:
            self.pc_remaining=4
            if self.blitz_strategy=='opportunistic' and self.steps:
                from .fast_solver import find_pc
                self.two_row_probes+=1
                try:
                    plan=find_pc(active+state['next'],hold=held,lines=2,mode='soft',timeout=.012,persistent=True,
                        save=False,kick_path=self.kick_path,path_mode=self.search_path_mode(),cancelled=self.stopped,
                        allow_hold=state['hold_available'])
                    if plan['status']=='solved':
                        self.pc_remaining=2;self.two_row_plans+=1
                        self.prefix=[dict(s,strategy='pc_finish',two_row_opportunity=True) for s in plan['steps']]
                        return self.choose(state,known,current,held_source)
                except (TimeoutError,ValueError):pass
            cycle_start=len(self.steps)//35*35
            # A boundary is determined by consumed piece count, not by the
            # number of previously perfect cycles. A missed earlier PC must
            # not permanently disable DPC for every subsequent bag cycle.
            dpc_boundary=len(self.steps)%35==20
            if self.uses_dpc and self.blitz_strategy!='score' and len(self.steps)%35==0:
                from .openers import pco_setup
                members=[known[i] for i in range(cycle_start,cycle_start+7) if i in known]
                missing=[i for i in range(cycle_start,cycle_start+7) if i not in known]
                if len(missing)==1 and len(set(members))==6:
                    known[missing[0]]=next(iter(set('IJLOSTZ')-set(members)))
                try:
                    prefix=pco_setup(known,current,held_source,cycle_start,check,state['hold_available'],self.kicks,self.search_path_mode())
                    if prefix:
                        self.prefix=[dict(s,strategy='pco_setup') for s in prefix]
                        return self.choose(state,known,current,held_source)
                except TimeoutError:self.pc_timeouts+=1
            # Prefer the shorter PC. A verified DPC template can justify a
            # six-line envelope; a missing template shouldn't force forty
            # salvage placements before the next all-clear.
            if dpc_boundary and (self.uses_dpc or self.stage%3==2):
                from .openers import dpc_setups
                try:
                    prefix=next(dpc_setups(known,current,held_source,cycle_start,
                                         check,self.kicks,path_mode=self.search_path_mode(),prefer_scoring=self.uses_dpc),None)
                    if prefix:
                        self.pc_remaining=6
                        self.prefix=[dict(s,strategy='dpc_setup') for s in prefix]
                        return self.choose(state,known,current,held_source)
                except TimeoutError:self.pc_timeouts+=1
            # Small verified fields beat searching ten unknown placements.
            if self.pc_remaining==4:
                try:
                    phase=(1,6,4,2,7,5,3)[len(self.steps)%7]
                    setups=field_setups(known,current,held_source,phase,
                        self.kicks,check,state['hold_available'],limit=4,path_mode=self.search_path_mode(),prefer_finesse=policy!='throughput',
                        finesse_weight=float(self.request.get('setup_finesse_weight',.5)))
                    if setups:
                        self.prefix=[dict(s,strategy='pc_setup') for s in setups[0]]
                        return self.choose(state,known,current,held_source)
                except TimeoutError:self.pc_timeouts+=1
        remaining=self.pc_remaining
        # If salvage stacked above the current PC envelope, try the next
        # possible envelope (same cell parity); never call that "no solution".
        if height>remaining or (10*remaining-occupied)%4 or occupied>=10*remaining:
            candidates=[h for h in range(max(height,2),7) if 10*h>occupied and (10*h-occupied)%4==0]
            remaining=min(candidates,default=0)
            if remaining:self.pc_remaining=remaining
        if remaining and time.perf_counter()<deadline-.015:
            self.pc_searches+=1
            try:
                self.prefix=choose_plan(known,current,held_source,board,remaining,
                    current+16,samples=3,cancelled=self.stopped,hold_available=state['hold_available'],
                    kick_path=self.kick_path,time_budget=max(.01,deadline-time.perf_counter()),
                    persistent=True,path_mode=self.search_path_mode(),coverage=self.request.get('forecast_coverage',False),
                    observed_finish_first=self.request.get('observed_finish_first',False),visible_finish_stats=self.visible_finish_stats,
                    deduce_bag=self.request.get('bag_deduction',self.blitz_strategy=='score'))
                if self.prefix and self.prefix[0].get('coverage_compared'):
                    self.coverage_comparisons=getattr(self,'coverage_comparisons',0)+1
                    self.coverage_changes=getattr(self,'coverage_changes',0)+int(self.prefix[0].get('coverage_changed',False))
                for step in self.prefix:step['strategy']='pc_finish' if not step.get('future_was_unknown') else 'pc_forecast'
                if self.prefix and not self.prefix[0].get('future_was_unknown') and self.uses_dpc:
                    self.prefix=improve_finish(board,active+state['next'],held,self.kicks,self.score_state,remaining,self.prefix,
                        self.allow180,self.allow_wall,budget=min(.025,max(0,deadline-time.perf_counter())),
                        hold_available=state['hold_available'],save_dpc_extra=(len(self.steps)+len(self.prefix))%35==20,cancelled=self.stopped,
                        score_first=self.blitz_strategy=='score' or policy=='throughput',
                        max_faults=self.fault_allowance() if self.standard_inputs_only() else None)
                if self.prefix:return self.choose(state,known,current,held_source)
            except (PlanningFailure,TimeoutError,ValueError):self.pc_timeouts+=1
        required=(10*remaining-occupied)//4 if remaining and (10*remaining-occupied)%4==0 else 0
        if self.finesse_policy=='adaptive' and self.fault_allowance() and 1<=required<=4:
            from .fast_solver import find_pc
            try:
                proposal=find_pc(active+state['next'],rows=list(reversed(board[:remaining])),hold=held,
                    lines=remaining,mode='soft',timeout=.025,persistent=True,save=False,kick_path=self.kick_path,
                    path_mode='ground180' if self.allow180 else 'ground',cancelled=self.stopped,allow_hold=state['hold_available'])
                if proposal['status']=='solved' and sum(estimated_faults(s['piece'],s['cells'],s['actions']) for s in proposal['steps'])<=self.fault_allowance():
                    self.prefix=[dict(s,strategy='pc_finish') for s in proposal['steps']]
                    return self.choose(state,known,current,held_source)
            except (TimeoutError,ValueError):pass
        self.score_fallbacks+=1
        step=score_move(board,active,state['next'],held,self.kicks,self.score_state,start,
                       state['hold_available'],self.allow180,budget=.035,cancelled=self.stopped,allow_wall=self.allow_wall,
                       finesse_only=self.standard_inputs_only(),multi_well=self.request.get('multi_well_control',self.blitz_strategy=='score'),
                       fault_penalty=0 if policy=='throughput' else 10)
        self.plan_times.append(time.perf_counter()-began)
        return step

    def ground_execute(self,step,state):
        began=time.perf_counter();trace_start=len(self.input_trace)
        board=state['board'];self.pending_step=step
        if step['hold_used']:
            # A high-gravity piece may lock while the planner is running.
            # Confirm its identity again before Hold can affect a new piece.
            if self.actual_gravity()>=20:
                fresh,_=self.observe(board)
                if any(fresh[key]!=state[key] for key in ('board','active','hold','next')):
                    raise RuntimeError('Hold 前方块已变化；已停止，未向下一块发送 Hold。')
                state=fresh
            self.send('hold')
            if self.air_eligible(state):
                state,_=self.wait_for(lambda s:s['board']==board and s['active']==step['piece'] and s['hold']==step['hold_after'],board,timeout=.35)
            else:state=self.ground_state(board,step['piece'],step['hold_after'])
        target=tuple(sorted(map(tuple,step['cells'])))
        air_success=False
        executed=[]
        if self.air_eligible(state) and step.get('spin','none')=='none':
            self.release_soft()
            matched=next(((p,r) for p in poses_for(step['piece'],state['active_cells'])
                          if (r:=air_route(board,step['piece'],self.kicks,p,target,self.allow180))),None)
            route=matched[1] if matched else None
            if route and not self.air_eligible(state,route['actions']):route=None
            if route and estimated_faults(step['piece'],target,route['actions'])>self.fault_allowance():route=None
            if route:
                step['execution_route_start']=list(matched[0])
                step['air_attempt_actions']=list(route['actions'])
                for action in route['actions'][:-1]:
                    if action.endswith('_wall'):self.send_wall(action[:-5]);self.wall_inputs+=1
                    else:self.send(action)
                    executed.append(action)
                step['input_timing']=self.input_trace[trace_start:]
                if route['actions'][:-1] or self.speed()['speed_preset']!='extreme':
                    time.sleep(self.speed().get('frame_wait_ms',18)/1000)
                try:
                    state,_=self.wait_for(lambda s:s['board']==board and s['active']==step['piece'] and s['hold']==step['hold_after'] and
                        any(tuple(sorted(dropped_cells(board,step['piece'],p)))==target for p in poses_for(step['piece'],s['active_cells'])),board,timeout=.16)
                    step.update(route);air_success=True;self.air_placements+=1
                except RuntimeError:
                    step['air_attempt_failed']=True
                    step['air_observation_after_failure']=dict(active=self.latest['active'],
                        active_cells=self.latest['active_cells'],hold=self.latest['hold'],
                        board=self.latest['board'],next=self.latest['next'])
                    raise RuntimeError('空中路线未确认；已停止，未补发或硬降。')
        if not air_success and not self.already_grounded(state):state=self.ground_state(board,step['piece'],step['hold_after'])
        move_inputs=0
        for attempt in range(0 if air_success else 1):
            poses=poses_for(step['piece'],state['active_cells'])
            wanted_spin=step.get('spin') if step.get('spin')!='none' else None
            matched=next(((p,r) for p in poses for r in ground_locks(board,step['piece'],self.kicks,
                       p,self.allow180,wanted=target,wanted_spin=wanted_spin,max_inputs=12-move_inputs,allow_wall=self.allow_wall).values()),None)
            if matched is None:raise RuntimeError('地面位置无法到达计划落点；已停止，未发送硬降。')
            route=matched[1];step['execution_ground_start']=list(matched[0])
            if estimated_faults(step['piece'],target,executed+route['actions'])>self.fault_allowance():
                raise RuntimeError('实际位置需要超出标准按键预算；少按键策略已停止，未发送硬降。')
            if attempt==0:
                baseline=next((r for p in poses for r in ground_locks(board,step['piece'],self.kicks,p,self.allow180,wanted=target,wanted_spin=wanted_spin).values()),None)
                if baseline:self.finesse_saved+=max(0,len(baseline['actions'])-len(route['actions']))
            expected_pose=matched[0]
            for action_index,action in enumerate(route['actions'][:-1]):
                raw_pose=raw_ground_action(board,step['piece'],expected_pose,action,self.kicks)
                expected_pose=settle(board,step['piece'],raw_pose)
                if action.endswith('_wall'):
                    try:
                        if self.speed()['speed_preset']=='extreme':
                            self.send_ground_wall(action[:-5],board,step['piece'],step['hold_after'],expected_pose)
                        else:self.send_wall(action[:-5])
                    finally:step['input_timing']=self.input_trace[trace_start:]
                    self.wall_inputs+=1
                else:self.send(action,duration_ms=18 if attempt else None)
                executed.append(action)
                step['attempted_ground_actions']=executed.copy()
                if raw_pose!=expected_pose and action_index<len(route['actions'])-2:
                    # Gravity happens between simulation frames, not
                    # necessarily between two different key events. A
                    # dependent next transform must see the actual fall.
                    step['input_timing']=self.input_trace[trace_start:]
                    barrier=dict(after_action=action,expected_pose=expected_pose,confirmed=False)
                    step.setdefault('ground_settle_barriers',[]).append(barrier)
                    self.confirm_ground_settle(board,step['piece'],step['hold_after'],expected_pose)
                    barrier['confirmed']=True
            move_inputs+=len(route['actions'])-1
            step['input_timing']=self.input_trace[trace_start:]
            step['attempted_ground_actions']=executed.copy()
            if route['actions'][:-1] or self.speed()['speed_preset']!='extreme':
                time.sleep(self.speed().get('frame_wait_ms',18)/1000)
            try:
                state,_=self.wait_for(lambda s:s['board']==board and s['active']==step['piece'] and
                                     s['hold']==step['hold_after'] and tuple(sorted(map(tuple,s['active_cells'])))==target,
                                     board,timeout=.16)
            except RuntimeError:
                raise RuntimeError('地面路线未确认；已停止，未补发或硬降。')
            if tuple(sorted(map(tuple,state['active_cells'])))==target:
                step.update(x=route['x'],y=route['y'],rotation=route['rotation'],spin=route['spin'],actions=route['actions'])
                break
            self.ground_corrections+=1
        else:
            if not air_success:raise RuntimeError('地面动作与实际落点不符；已停止，未发送硬降。')
        # The latest image proves BOTH the field and the exact four cells.
        # No renderer wait or planner work is allowed between proof and drop.
        if self.allow_wall and self.actual_gravity()<20:self.release_soft()
        # Keep the exact pre-drop evidence in memory. Failed executions
        # export it alongside the post-failure screenshot; successful
        # placements keep only the small observation and timing record.
        self.pending_lock_image=self.last_image
        step['lock_proof']=dict(active=state['active'],active_cells=state['active_cells'],
                                hold=state['hold'],observed_at=self.observed_at,
                                input_released=self.input_released,air=air_success)
        self.send('hard_drop')
        step['execution_actions']=executed+['hard_drop']
        step['input_timing']=self.input_trace[trace_start:]
        # A stale frame cannot contain the new post-lock board: a tetromino
        # changes occupied-cell count by 4-10*clears, never zero. Observe
        # immediately in extreme mode; wait_for still requires that exact
        # board AND the next active piece before permitting another move.
        if self.speed()['speed_preset']!='extreme':
            time.sleep(self.speed().get('frame_wait_ms',18)/1000)
        expected=tuple(step['board_after']);self.reference_board=expected
        state,image=self.wait_for(lambda s:s['board']==expected and s['active'] is not None and
                                 s['hold']==step['hold_after'],expected,timeout=.65)
        now=time.perf_counter();self.steps.append(step);self.lock_times.append(now)
        step.update(execution_seconds=round(now-began,6),locked_at_seconds=round(now-self.play_started,6),
                    input_timing=self.input_trace[trace_start:],observed_active_after=state['active'],
                    observed_next_after=state['next'],lock_verification='air_sprite_projection_before_and_board_after' if air_success else 'ground_sprite_before_and_board_after')
        self.execution_seconds+=now-began
        recording_started=time.perf_counter()
        lines=len(step['cleared_rows']);pc=expected==empty_board()
        if lines and step.get('source_setup_cleared_lines',0):
            self.full_row_setup_events=getattr(self,'full_row_setup_events',0)+1
        self.cleared+=lines;self.pc_remaining-=lines
        self.score_state=self.score_state.place(lines,step.get('spin','none'),pc)
        if self.simulation not in ('blitz','level15'):
            from dataclasses import replace
            self.score_state=replace(self.score_state,level=1,level_progress=0)
        if pc:
            self.completed_pcs+=1;self.stage+=1;self.prefix=[]
            if step.get('two_row_opportunity'):self.two_row_finishes+=1
            self.pc_boundaries.append(dict(pieces=len(self.steps),lines=self.cleared))
            # Lossless evidence, but favor a shorter lock-window pause over
            # saving a few kilobytes in every PC screenshot.
            image.save(self.folder/f'pc-{self.completed_pcs:03d}.png',compress_level=1)
        from .loop_tracker import dpc_cycles
        self.cycle_evidence=dpc_cycles(self.pc_boundaries,self.steps)
        self.completed_cycles=self.cycle_evidence['verified_cycles']
        step['estimated_clear_score_after']=self.score_state.score
        step['estimated_finesse_faults']=estimated_faults(step['piece'],step['cells'],step['execution_actions'])
        self.estimated_finesse_faults+=step['estimated_finesse_faults']
        with (self.folder/'steps.jsonl').open('a',encoding='utf-8') as out:
            out.write(json.dumps(step,ensure_ascii=False)+'\n')
        self.pending_step=None;self.write_status('running','本块落点与落地棋盘已核对。')
        step['post_lock_recording_seconds']=round(time.perf_counter()-recording_started,6)
        self.pending_lock_image=None
        return state

    def write_status(self,status,message):
        data=super().status_data(status,message)
        from .windows import capture_backend,_capture_local
        from .blitz import ground_cache_info
        data.update(strategy='blitz_score',blitz_strategy=self.blitz_strategy,simulation_profile=self.simulation,
                    setup_finesse_weight=float(self.request.get('setup_finesse_weight',.5)),
                    spin_extra_inputs=int(self.request.get('spin_extra_inputs',0)),
                    full_row_setup_events=getattr(self,'full_row_setup_events',0),
                    visible_finish_stats=self.visible_finish_stats,
                    bag_deduction=self.request.get('bag_deduction',self.blitz_strategy=='score'),
                    multi_well_control=self.request.get('multi_well_control',self.blitz_strategy=='score'),
                    bag_derived_steps=sum(bool(s.get('seven_bag_deductions')) for s in self.steps),
                    finesse_policy=self.finesse_policy,
                    tap_pulse_ms=self.speed()['tap_ms'],
                    effective_finesse_policy=self.effective_finesse_policy(),
                    gravity_policy_switches=getattr(self,'gravity_policy_switches',0),
                    ground_route_cache=ground_cache_info(),
                    post_lock_recording_seconds=round(sum(s.get('post_lock_recording_seconds',0) for s in self.steps),6),
                    estimated_finesse_faults=self.estimated_finesse_faults,
                    finesse_refinements=self.finesse_refinements,
                    early_setup_finishes=self.early_setup_finishes,
                    early_setup_probes=self.early_setup_probes,
                    two_row_probes=self.two_row_probes,two_row_plans=self.two_row_plans,two_row_finishes=self.two_row_finishes,
                    coverage_comparisons=getattr(self,'coverage_comparisons',0),coverage_changes=getattr(self,'coverage_changes',0),
                    rotation_rules='SRS+180' if self.allow180 else 'SRS+90',
                    estimated_clear_score=self.score_state.to_dict(),
                    score_includes_drop_points=False,pc_searches=self.pc_searches,
                    pc_budget_misses=self.pc_timeouts,score_fallbacks=self.score_fallbacks,
                    ground_corrections=self.ground_corrections,allow180=self.allow180,
                    wall_inputs=self.wall_inputs,finesse_inputs_saved=self.finesse_saved,pps_limited=bool(self.speed()['target_pps']),
                    air_placements=self.air_placements,
                    pixel_capture_backend=capture_backend(),capture_backend_failure=getattr(_capture_local,'capture_failure',None),
                    pc_boundaries=self.pc_boundaries,
                    dpc_cycle_evidence=self.cycle_evidence,
                    max_planning_ms=round(max(self.plan_times,default=0)*1000,2))
        if 'live_metrics' in self.request:
            self.request['live_metrics'].update(data['speed_metrics'])
            self.request['live_metrics'].update(estimated_clear_score=self.score_state.score,
                level=self.score_state.level,pcs=self.completed_pcs,score_fallbacks=self.score_fallbacks,
                dpc_cycle_evidence={k:v for k,v in self.cycle_evidence.items() if k!='cycles'})
        # Durable per-piece JSONL retains every verified input. Periodic
        # full snapshots avoid serializing an ever-growing history twice
        # per piece; final/error snapshots still contain the entire run.
        if status!='running' or len(self.steps)%10==0 or self.completed_pcs!=self.last_persisted or not (self.folder/'session.json').exists():
            # JSONL already retains every verified move. Compact periodic
            # snapshots avoid formatting an ever-growing history during
            # the next piece's lock window; final/error files stay readable.
            serialized=json.dumps(data,ensure_ascii=False,**({'separators':(',',':')} if status=='running' else {'indent':2}))
            (self.folder/'session.json').write_text(serialized,encoding='utf-8')
            self.last_persisted=self.completed_pcs
        self.progress('running' if status=='running' else status,
            f"Blitz 策略 · PC {self.completed_pcs} · {len(self.steps)} 块 · {self.cleared} 行 · "
            f"实际 {data['speed_metrics']['overall_pps']:.2f} PPS · 消行估分 {self.score_state.score:,}。{message}")
        return data

    def run_visible(self):
        from .blitz_validation import validate_blitz
        duration,maximum=validate_blitz(self.request,self.profile,self.timing)
        focus(self.hwnd)
        # Load static planning data and the JVM while still waiting for a
        # new game. A first 20G piece has only its ordinary lock window.
        from .best_fields import fields
        from .fast_solver import find_pc
        fields()
        try:find_pc('JLOSTZIJLO',lines=4,allow_hold=True,timeout=1.2,
                    persistent=True,path_mode=self.search_path_mode(),save=False,
                    kick_path=self.kick_path,cancelled=self.stopped)
        except TimeoutError:pass
        self.solver_warmed=True
        if self.request.get('restart'):self.restart_current()
        state,image=self.initial_state()
        if state['game_mode']=='zen':raise ValueError('Blitz 策略请打开 SOLO → BLITZ 或 CUSTOM。')
        self.preview_count=len(state['next']);start_image=image
        self.initial_visible_queue=(state['hold'] or '')+state['active']+state['next']
        current=1 if state['hold'] else 0;held_source=0 if state['hold'] else None
        known={current:state['active']}
        if held_source is not None:known[held_source]=state['hold']
        known.update({current+i+1:p for i,p in enumerate(state['next'])})
        self.play_started=time.perf_counter()
        try:
            # Reserve one normal placement window at the timed objective's
            # end, so a new hard drop is not launched into the results page.
            while time.perf_counter()-self.play_started<max(.25,duration-.6) and (not maximum or len(self.steps)<maximum):
                # Never sleep out a 500ms lock timer when a slow preset is
                # selected. Pace before grounding; clamp waits to 120ms.
                target=self.speed()['target_pps']
                if target:
                    deadline=min(self.play_started+len(self.steps)/target,time.perf_counter()+.12)
                    while time.perf_counter()<deadline:
                        if self.stopped():raise InterruptedError('已停止 Blitz。')
                        time.sleep(.003)
                if self.air_eligible(state):self.release_soft()
                elif not self.soft_held or not self.already_grounded(state):state=self.ground_state(state['board'])
                if state['active']!=known[current]:raise RuntimeError('规划前来块已经改变；已停止，保留当前局。')
                began=time.perf_counter();step=self.choose(state,known,current,held_source)
                planning_seconds=time.perf_counter()-began
                self.plan_times.append(planning_seconds)
                step['planning_seconds']=round(planning_seconds,6)
                before=current;source=current
                if step['hold_used']:
                    source=held_source if held_source is not None else current+1;held_source=current
                current+=step['queue_index_after']-step['queue_index_before']
                step.update(source_index=source,global_queue_index_before=before,global_queue_index_after=current,
                            stage=self.stage%3+1,cycle=self.stage//3+1)
                state=self.ground_execute(step,state)
                revealed={current:state['active']}
                revealed.update({current+i+1:p for i,p in enumerate(state['next'])})
                if not observation_consistent(known,revealed):raise RuntimeError('实际来块与已知七袋不一致；已停止。')
                known.update(revealed)
                if self.farm_policy:
                    reason=self.farm_policy.reason(len(self.steps),self.pc_boundaries,self.score_state.score)
                    if reason:
                        return self.write_status('abandoned',reason+'；已释放按键，交给刷分管理器。')
            if self.last_image:self.last_image.save(self.folder/'finished.png')
            return self.write_status('done','指定运行时长 / 块数已完成；未重开当前局。')
        finally:
            self.release_soft()
            start_image.save(self.folder/'start.png')
