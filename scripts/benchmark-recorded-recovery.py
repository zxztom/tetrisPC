"""Same-history counterfactual recovery, NOT independent random evidence.

Only identities already captured by the past bot enter an isolated oracle.
Every counterfactual planner receives its own current/Hold/five Next only.
No replay seed or desktop input; this script is never a live queue source.
"""
import argparse,copy,importlib.util,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz import Score,settle,ground_locks
from pc_lab.engine import empty_board,cells,lock
from pc_lab.finesse import estimated_faults
from pc_lab.search_worker import close_worker
from pc_lab.solver import ROOT

p=argparse.ArgumentParser();p.add_argument('--session',type=Path,required=True);p.add_argument('--after',type=int,default=480)
p.add_argument('--output',type=Path,required=True);a=p.parse_args();sys.stdout.reconfigure(encoding='utf-8')
spec=importlib.util.spec_from_file_location('visible_benchmark',ROOT/'scripts/benchmark-blitz-visible.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
session=json.loads(a.session.read_text(encoding='utf-8'));history=session['steps'];identities={}
for step in history:
    identities[step['source_index']]=step['piece'];index=step['global_queue_index_after']
    identities[index]=step['observed_active_after']
    identities.update({index+1+i:p for i,p in enumerate(step['observed_next_after'])})
reports=[]
try:
    for enabled in (False,True):
        runner=object.__new__(module.BlitzRunner)
        runner.prefix=[];runner.steps=copy.deepcopy(history[:a.after]);runner.pc_searches=runner.pc_timeouts=runner.score_fallbacks=0;runner.plan_times=[]
        runner.last_finesse_refine=-1;runner.finesse_refinements=runner.early_setup_finishes=runner.early_setup_probes=0
        runner.request=dict(multi_well_control=enabled,bag_deduction=True)
        runner.visible_finish_stats=dict(probes=0,plans=0,incomplete=0)
        runner.kick_path=ROOT/'data/srsplus90.properties';runner.kicks=module.load_kicks(runner.kick_path)
        runner.allow180=runner.allow_wall=runner.uses_dpc=True;runner.finesse_policy='balanced';runner.blitz_strategy='score'
        runner.two_row_probes=runner.two_row_plans=runner.two_row_finishes=0;runner.simulation='blitz';runner.stopped=lambda:False
        runner.score_state=Score();held_source=None;last_pc_lines=0
        established={}
        for step in runner.steps:
            if step['hold_used']:held_source=step['global_queue_index_before']
            runner.score_state=runner.score_state.place(len(step['cleared_rows']),step.get('spin','none'),tuple(step['board_after'])==empty_board())
            established[step['source_index']]=step['piece']
            if tuple(step['board_after'])==empty_board():last_pc_lines=runner.score_state.lines
        runner.stage=runner.score_state.pcs;runner.pc_remaining=4-(runner.score_state.lines-last_pc_lines)
        last=runner.steps[-1];current=last['global_queue_index_after'];held=last['hold_after'];board=tuple(last['board_after'])
        maximum=max((y+1 for y,row in enumerate(board) if row!='__________'),default=0)
        start_pcs=runner.score_state.pcs;reason='recorded observations exhausted';began=time.perf_counter()
        while all(i in identities for i in range(current,current+6)):
            active=identities[current];preview=''.join(identities[i] for i in range(current+1,current+6))
            established.update({current+i:p for i,p in enumerate(active+preview)})
            pose=settle(board,active,(4,21,0));state=dict(board=board,active=active,next=preview,hold=held,
                hold_available=True,active_cells=cells(active,pose[2],pose[0],pose[1]))
            try:step=runner.choose(state,established,current,held_source)
            except (ValueError,RuntimeError) as exc:reason=str(exc);break
            target=tuple(sorted(map(tuple,step['cells'])));piece=step['piece']
            route=ground_locks(board,piece,runner.kicks,allow180=True,allow_wall=True,wanted=target,
                wanted_spin=step.get('spin') if step.get('spin')!='none' else None).get(target)
            if route is None:raise ValueError('unreachable counterfactual step')
            after,_,cleared=lock(board,target,piece)
            if any(y>=20 for x,y in target):reason='placement enters spawn region; not counted as safe recovery';break
            if tuple(step['board_after'])!=after:raise ValueError('counterfactual geometry mismatch')
            if step['hold_used']:held_source=current
            current+=step['queue_index_after']-step['queue_index_before'];held=step['hold_after'];board=after
            step['estimated_finesse_faults']=estimated_faults(piece,target,route['actions']);runner.steps.append(step)
            pc=board==empty_board();runner.pc_remaining-=len(cleared);runner.score_state=runner.score_state.place(len(cleared),route['spin'],pc)
            if pc:runner.stage+=1;runner.prefix=[]
            maximum=max(maximum,max((y+1 for y,row in enumerate(board) if row!='__________'),default=0))
        report=dict(multi_well_control=enabled,source=str(a.session),start_after_piece=a.after,
            additional_pieces=len(runner.steps)-a.after,additional_pcs=runner.score_state.pcs-start_pcs,
            maximum_height=maximum,clear_score=runner.score_state.score,stop_reason=reason,
            seconds=round(time.perf_counter()-began,3),independent_random=False,native_test=False,
            same_recorded_history=True,online_future_queue_supplied=False,actual_native_failure_reproduced=False)
        reports.append(report);print(json.dumps(report,ensure_ascii=False),flush=True)
    a.output.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
finally:close_worker()
