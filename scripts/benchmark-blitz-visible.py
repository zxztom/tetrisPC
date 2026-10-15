"""Offline planner comparison with an isolated random seven-bag oracle.

The planner gets active/Hold and the requested five or six Next only. It never receives this oracle's
remaining queue, a seed, or a replay. No desktop input or capture is used.
This proves neither native finesse nor real-time gravity stability.
"""
import argparse,json,random,sys,time,hashlib
from contextlib import nullcontext
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz_live import BlitzRunner
from pc_lab.blitz import Score,settle,ground_locks
from pc_lab.engine import empty_board,load_kicks,cells,lock
from pc_lab.finesse import estimated_faults
from pc_lab.fast_solver import find_pc
from pc_lab.search_worker import close_worker
from pc_lab.solver import ROOT


def simulate(oracle,policy,strategy,count,setup_replan=False,coverage=False,setup_weight=.5,observed_first=False,next_count=6,short_pc=False,deduce_bag=False,multi_well=False):
    # Skip the desktop constructor entirely; only choose() is invoked.
    runner=object.__new__(BlitzRunner)
    runner.prefix=[];runner.steps=[];runner.pc_remaining=4;runner.stage=0
    runner.pc_searches=0;runner.pc_timeouts=0;runner.score_fallbacks=0;runner.plan_times=[]
    runner.last_finesse_refine=-1;runner.finesse_refinements=0
    runner.early_setup_finishes=0;runner.early_setup_probes=0;runner.request=dict(early_setup_finish=setup_replan,diagnostic_setup=True,forecast_coverage=coverage,setup_finesse_weight=setup_weight,observed_finish_first=observed_first,short_pc=short_pc,bag_deduction=deduce_bag,multi_well_control=multi_well)
    runner.visible_finish_stats=dict(probes=0,plans=0,incomplete=0)
    runner.kick_path=ROOT/'data/srsplus90.properties';runner.kicks=load_kicks(runner.kick_path)
    runner.allow180=True;runner.allow_wall=True;runner.finesse_policy=policy;runner.blitz_strategy=strategy
    runner.uses_dpc=strategy in ('dpc','opportunistic','score');runner.two_row_probes=0;runner.two_row_plans=0;runner.two_row_finishes=0
    runner.score_state=Score();runner.stopped=lambda:False;runner.simulation='blitz'
    board=empty_board();held=None;current=0;held_source=None;boundaries=[];faults=0
    observed={i:oracle[i] for i in range(next_count+1)};started=time.perf_counter();error=None
    high_gravity_pieces=high_gravity_faults=0
    choose=runner.choose
    if short_pc:
        from short_pc_experiment import try_short_pc
        original_choose=runner.choose
        def choose(state,known,current,held_source):
            try_short_pc(runner,state)
            return original_choose(state,known,current,held_source)
    try:
        for n in range(count):
            active=oracle[current];start=settle(board,active,(4,21,0))
            state=dict(board=board,active=active,hold=held,next=oracle[current+1:current+1+next_count],hold_available=True,
                       active_cells=cells(active,start[2],start[0],start[1]))
            # The only oracle exposure at this transition is the visible queue.
            observed.update({current+i:p for i,p in enumerate(active+state['next'])})
            step=choose(state,observed,current,held_source)
            piece=held or state['next'][0] if step['hold_used'] else active
            if piece!=step['piece']:raise ValueError('planner piece mismatch')
            target=tuple(sorted(map(tuple,step['cells'])))
            route_start=settle(board,piece,(4,21,0)) if step['hold_used'] else start
            routes=ground_locks(board,piece,runner.kicks,route_start,True,wanted=target,
                                wanted_spin=step.get('spin') if step.get('spin')!='none' else None,allow_wall=True)
            if target not in routes:raise ValueError('unreachable plan')
            route=routes[target];extra=estimated_faults(piece,target,route['actions'])
            if runner.actual_gravity()>=20:high_gravity_pieces+=1;high_gravity_faults+=extra
            if extra>runner.fault_allowance():raise ValueError('route exceeds policy fault budget')
            after,_,cleared=lock(board,target,piece)
            if tuple(step['board_after'])!=after or tuple(step['cleared_rows'])!=cleared:raise ValueError('board mismatch')
            source=current
            if step['hold_used']:
                source=held_source if held_source is not None else current+1;held_source=current
            current+=step['queue_index_after']-step['queue_index_before'];held=step['hold_after']
            step['source_index']=source;step['estimated_finesse_faults']=extra;runner.steps.append(step);faults+=extra;board=after
            pc=board==empty_board();runner.pc_remaining-=len(cleared)
            if cleared and step.get('source_setup_cleared_lines',0):
                runner.full_row_setup_events=getattr(runner,'full_row_setup_events',0)+1
            runner.score_state=runner.score_state.place(len(cleared),route['spin'],pc)
            if pc:
                if step.get('two_row_opportunity'):runner.two_row_finishes+=1
                boundaries.append(dict(pieces=n+1,lines=runner.score_state.lines));runner.stage+=1;runner.prefix=[]
    except (ValueError,RuntimeError,KeyError,IndexError) as exc:error=f'{type(exc).__name__}: {exc}'
    return dict(policy=policy,strategy=strategy,pieces=len(runner.steps),clear_score=runner.score_state.score,
                lines=runner.score_state.lines,level=runner.score_state.level,pcs=runner.score_state.pcs,
                high_gravity_pieces=high_gravity_pieces,high_gravity_faults=high_gravity_faults,
                gravity_policy_switches=getattr(runner,'gravity_policy_switches',0),
                tspins=runner.score_state.tspins,estimated_faults=faults,pc_boundaries=boundaries,
                planner_wall_seconds=round(time.perf_counter()-started,3),error=error,
                setup_replan=setup_replan,early_setup_finishes=runner.early_setup_finishes,
                early_setup_probes=runner.early_setup_probes,
                setup_probe_diagnostics=getattr(runner,'setup_probe_diagnostics',[]),
                two_row_probes=runner.two_row_probes,two_row_plans=runner.two_row_plans,two_row_finishes=runner.two_row_finishes,
                forecast_coverage=coverage,coverage_comparisons=getattr(runner,'coverage_comparisons',0),coverage_changes=getattr(runner,'coverage_changes',0),
                setup_finesse_weight=setup_weight,
                full_row_setup_events=getattr(runner,'full_row_setup_events',0),
                observed_finish_first=observed_first,visible_finish_stats=runner.visible_finish_stats,short_pc=short_pc,
                bag_deduction=deduce_bag,bag_derived_steps=sum(bool(s.get('seven_bag_deductions')) for s in runner.steps),
                multi_well_control=multi_well,
                maximum_board_height=max((max((y+1 for y,row in enumerate(s['board_after']) if row!='__________'),default=0) for s in runner.steps),default=0),
                spawn_region_locks=sum(any(y>=20 for x,y in s['cells']) for s in runner.steps),
                preview_count=next_count,
                native_verified=False,drop_points_included=False,execution_and_gravity_simulated=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pieces',type=int,default=700);p.add_argument('--cases',type=int,default=1)
    p.add_argument('--strategy',choices=('pc','dpc','opportunistic','score'),default='dpc');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--compare-score',action='store_true')
    p.add_argument('--compare-short-pc',action='store_true')
    p.add_argument('--compare-two-row',action='store_true')
    p.add_argument('--compare-gravity',action='store_true')
    p.add_argument('--compare-coverage',action='store_true')
    p.add_argument('--compare-setup-weight',action='store_true')
    p.add_argument('--compare-full-row-fields',action='store_true')
    p.add_argument('--compare-observed-first',action='store_true')
    p.add_argument('--next-count',type=int,choices=(5,6),default=6)
    p.add_argument('--compare-setup',action='store_true')
    p.add_argument('--early-setup-finish',action='store_true')
    args=p.parse_args();sys.stdout.reconfigure(encoding='utf-8')
    randomizer=random.SystemRandom();reports=[]
    try:
        find_pc('JLOSTZIJLO',lines=4,allow_hold=True,timeout=1.2,persistent=True,path_mode='ground180fine',save=False,kick_path=ROOT/'data/srsplus90.properties')
        for case in range(args.cases):
            queue=[]
            for bag in range((args.pieces+20)//7+1):
                pieces=list('IJLOSTZ');randomizer.shuffle(pieces)
                queue.extend(pieces)
            oracle=''.join(queue)
            choices=[('strict',False,args.strategy),('strict',True,args.strategy)] if args.compare_setup else [(p,args.early_setup_finish,args.strategy) for p in ('balanced','strict','adaptive')]
            if args.compare_two_row:choices=[('strict',False,'dpc'),('strict',False,'opportunistic')]
            runs=[(policy,setup,strategy,False,.5) for policy,setup,strategy in choices]
            if args.compare_gravity:runs=[(policy,False,args.strategy,False,.5) for policy in ('balanced','gravity')]
            if args.compare_score:runs=[('balanced',False,strategy,False,.5) for strategy in ('pc','dpc','score')]
            if args.compare_coverage:runs=[('strict',False,args.strategy,c,.5) for c in (False,True)]
            if args.compare_setup_weight:runs=[('balanced',False,args.strategy,False,w) for w in (.5,8)]
            libraries=[(None,None)]
            if args.compare_full_row_fields:
                previous=json.loads((ROOT/'output/best-chance-before-full-row-fix.json').read_text(encoding='utf-8'))['fields']
                from pc_lab.best_fields import fields
                libraries=[('before_full_row_fix',previous),('with_full_row_fix',fields())]
                runs=[(policy,False,args.strategy,False,.5) for policy in ('balanced','strict')]
            observed_modes=[False];short_modes=[False]
            if args.compare_short_pc:
                runs=[('balanced',False,args.strategy,False,.5)]
                short_modes=[False,True]
            if args.compare_observed_first:
                runs=[(policy,False,args.strategy,False,.5) for policy in ('balanced','strict')]
                observed_modes=[False,True]
            for policy,setup_replan,strategy,coverage,setup_weight in runs:
                for library_name,library in libraries:
                    for observed_first in observed_modes:
                        for short_pc in short_modes:
                            with patch('pc_lab.best_fields.fields',return_value=library) if library is not None else nullcontext():
                                report=simulate(oracle,policy,strategy,args.pieces,setup_replan,coverage,setup_weight,observed_first,args.next_count,short_pc)
                            if library_name:report.update(field_library=library_name,field_count=len(library))
                            report.update(case=case+1,oracle_fingerprint=hashlib.sha256(oracle.encode()).hexdigest(),
                                          queue_origin='unfiltered offline SystemRandom seven-bag; paired policies share this case',
                                          initial_active=oracle[0])
                            reports.append(report);args.output.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
                            print(json.dumps({k:v for k,v in report.items() if k not in ('pc_boundaries','setup_probe_diagnostics')},ensure_ascii=False),flush=True)
    finally:close_worker()
