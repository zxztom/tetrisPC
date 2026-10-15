"""One exclusive desktop lease for every farming attempt and menu transition.

Navigation is an independently calibrated, image-guarded adapter. Missing
calibration stops BEFORE starting a game; never guess coordinates or retry R.
"""
import json
import msvcrt
import time
import uuid
from .solver import ROOT
from .farm_policy import FarmPolicy,FarmLedger,replay_result


def farm_loop(request, runner_factory, navigator, ledger, progress, stopped, clock=time.perf_counter):
    policy=FarmPolicy.from_request(request);previous_queue=None
    while not policy.maximum_attempts or len(ledger.attempts)<policy.maximum_attempts:
        if stopped():raise InterruptedError('刷分已停止。')
        began=clock();runner=runner_factory();item=dict(status='error',queue_kind='fresh_menu_random',
            directory=str(runner.folder),strategy=request.get('blitz_strategy','pc'),finesse_policy=request.get('finesse_policy','balanced'))
        recorded=False
        try:
            result=runner.run()
            item.update(status=result['status'],reason=result['message'],placed_pieces=result['placed_pieces'],
                        completed_pcs=result['completed_pcs'],estimated_clear_score=result['estimated_clear_score']['score'],
                        score_includes_drop_points=False)
            # Only already observed/placed identities enter this check.
            sources=dict(enumerate(getattr(runner,'initial_visible_queue','')))
            sources.update({s['source_index']:s['piece'] for s in runner.steps})
            observed=''
            while len(observed) in sources:observed+=sources[len(observed)]
            repeated=bool(previous_queue and min(len(previous_queue),len(observed))>=35 and previous_queue[:35]==observed[:35])
            item['same_observed_queue_prefix']=repeated
            item['observed_queue_prefix_length']=len(observed)
            if repeated:
                raise RuntimeError('连续新局观察到相同的至少35块队列；已停止，请复核菜单是否重复种子。')
            previous_queue=observed
            if stopped():raise InterruptedError('刷分已停止；保留当前局。')
            if result['status']=='done' and not request.get('max_pieces'):
                replay=ledger.folder/f'attempt-{len(ledger.attempts)+1:05d}.ttr'
                navigator.export_complete(replay)
                native=replay_result(replay)
                if not native['native_complete']:raise RuntimeError('导出录像不是完整两分钟；不计最高分。')
                tail=native['native_pieces']-len(runner.steps)
                if tail!=0 and not (tail==1 and native.get('native_hard_drops')==len(runner.steps)):
                    raise RuntimeError('录像与当前局块数不符；不重开。')
                # At 20G the unplayed piece can lock naturally during the
                # reserved final 600ms. All commanded locks were already
                # verified. Record this tail separately, never as a bot move.
                native['natural_tail_pieces']=tail
                native['verified_controlled_pieces']=len(runner.steps)
                item.update(native)
            item['wall_seconds']=round(clock()-began,3);ledger.append(item);recorded=True
            if 'live_metrics' in request:
                request['live_metrics'].update(farm_attempt_count=len(ledger.attempts),
                    farm_complete_count=sum(bool(a.get('native_complete')) for a in ledger.attempts),
                    farm_best_score=ledger.best['native_score'] if ledger.best else None)
            progress('running',f"刷分第 {len(ledger.attempts)} 局已记录；最高完整局 {ledger.best['native_score'] if ledger.best else '尚无'}。")
            if policy.maximum_attempts and len(ledger.attempts)>=policy.maximum_attempts:break
            if result['status']=='done' and not policy.continue_after_complete:break
            # Safe failures and cancellation never go through restart.
            navigator.fresh_game(abandoned=result['status']=='abandoned')
        except Exception as exc:
            if not recorded:
                item.update(status='cancelled' if isinstance(exc,InterruptedError) else 'error',reason=str(exc),wall_seconds=round(clock()-began,3),
                            placed_pieces=len(getattr(runner,'steps',[])),completed_pcs=getattr(runner,'completed_pcs',0))
                ledger.append(item)
            else:
                (ledger.folder/'navigation-stop.json').write_text(json.dumps(dict(reason=str(exc),after_attempt=len(ledger.attempts)),ensure_ascii=False,indent=2),encoding='utf-8')
            raise
    report=ledger.save()
    return dict(status='done',message='本次刷分已完成；按局记录，未累计跨局分数。',
                output_directory=str(ledger.folder),farm=report,placed_pieces=sum(a.get('placed_pieces',0) for a in ledger.attempts),
                completed_pcs=sum(a.get('completed_pcs',0) for a in ledger.attempts),cleared_lines=0)


def run_farm(request,progress=lambda *_:None,cancelled=lambda:False):
    if request.get('cycle_mode')!='blitz' or request.get('simulation_profile','blitz')!='blitz':
        raise ValueError('当前刷分模式只统计原版 SOLO → BLITZ；CUSTOM 请关闭刷分后测试。')
    if request.get('seed') is not None or request.get('restart') or request.get('max_pieces') or float(request.get('blitz_seconds',120))!=120:
        raise ValueError('刷分须为无种子、120秒完整局，不能用 R 同队列重试或块数上限。')
    policy=FarmPolicy.from_request(request)
    from .config import load_profile
    from .blitz_validation import validate_blitz
    validate_blitz(request,load_profile(request.get('config_path')))
    from .farm_navigation import NativeNavigator
    # Read and validate recipe before acquiring focus or issuing input.
    recipe=NativeNavigator.load_recipe()
    if (policy.pc_drought or policy.break_cycle or policy.minimum_score_per_piece) and not recipe.get('abandoned'):
        raise ValueError('提前放弃的菜单尚未校准；请关闭提前放弃条件，仅使用打完自动下一局。')
    from .windows import EmergencyKeys,emergency_pressed,user,find_game,focus
    from .blitz_live import BlitzRunner
    lease=(ROOT/'output/desktop-control.lock').open('a+b')
    if lease.tell()==0:lease.write(b'0');lease.flush()
    lease.seek(0)
    try:msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        lease.close();raise RuntimeError('已有桌面控制任务，未启动刷分。')
    hotkeys=None
    folder=ROOT/'output'/('farm-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    ledger=FarmLedger(folder)
    try:
        game=find_game();hwnd=game['hwnd'];focus(hwnd);hotkeys=EmergencyKeys()
        def stopped():return cancelled() or emergency_pressed() or hotkeys.pressed.is_set() or int(user.GetForegroundWindow() or 0)!=hwnd
        navigator=NativeNavigator(hwnd,recipe,stopped,folder,cancelled=lambda:cancelled() or hotkeys.pressed.is_set())
        # Calibrated HOME, results, or BLITZ start page only; never AGAIN.
        navigator.fresh_game(abandoned=False,initial=True)
        req=dict(request,restart=False,auto_retry=False,recover_on_failure=False)
        # A finished individual game does not finish the outer API job.
        def report(state,message):progress('running' if state in ('abandoned','done') else state,message)
        return farm_loop(req,lambda:BlitzRunner(req,report,stopped,control_lock=lease),navigator,ledger,progress,stopped)
    except Exception as exc:
        (folder/'navigation-stop.json').write_text(json.dumps(dict(reason=str(exc),after_attempt=len(ledger.attempts)),ensure_ascii=False,indent=2),encoding='utf-8')
        ledger.save()
        raise
    finally:
        if hotkeys:hotkeys.close()
        lease.close()
