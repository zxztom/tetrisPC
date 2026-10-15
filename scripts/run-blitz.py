"""Launch the dedicated single-player score strategy without reading a seed."""
import argparse,json,sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.live import run_live

p=argparse.ArgumentParser()
p.add_argument('--seconds',type=float,default=120)
p.add_argument('--pieces',type=int,default=0)
p.add_argument('--profile',choices=('blitz','level10','level15','20g'),default='blitz')
p.add_argument('--strategy',choices=('pc','dpc','opportunistic','score'),default='pc')
p.add_argument('--finesse',choices=('balanced','strict','adaptive','gravity','throughput'),default='throughput')
p.add_argument('--start-level',type=int,default=1)
p.add_argument('--speed',choices=('steady','fast','sprint','extreme','custom'),default='extreme')
p.add_argument('--interval-ms',type=float,default=None)
p.add_argument('--restart',action='store_true')
p.add_argument('--farm',action='store_true')
p.add_argument('--pc-drought',type=int,default=0)
p.add_argument('--break-cycle',action='store_true')
p.add_argument('--minimum-score-per-piece',type=float,default=0)
p.add_argument('--grace-pieces',type=int,default=35)
p.add_argument('--attempts',type=int,default=0)
p.add_argument('--stop-after-complete',action='store_true')
p.add_argument('--early-setup-finish',action='store_true')
p.add_argument('--forecast-coverage',action='store_true')
p.add_argument('--setup-finesse-weight',type=float,default=.5)
p.add_argument('--observed-finish-first',action='store_true')
p.add_argument('--deduce-bag',action='store_true',help='Use the uniquely inferable seventh piece of an aligned bag; never reads a seed or unseen order.')
p.add_argument('--spin-extra-inputs',type=int,choices=(0,1),default=0,help='Experimental same-cell T-spin promotion; allows one extra input without an extra wall charge.')
p.add_argument('--pulse-ms',type=float,default=None,help='Experimental extreme key pulse for this process only; game handling is unchanged.')
a=p.parse_args();sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
if a.pulse_ms is not None:
    if a.speed!='extreme' or not math.isfinite(a.pulse_ms) or not (a.pulse_ms==0 or .5<=a.pulse_ms<=24):
        p.error('--pulse-ms requires extreme mode and 0 (paired events) or a finite value from 0.5 to 24ms')
result=run_live(dict(cycle_mode='blitz',live_mode='visible',wait_start=True,
                    launch_game=False,blitz_seconds=a.seconds,max_pieces=a.pieces,
                    simulation_profile=a.profile,blitz_strategy=a.strategy,finesse_policy=a.finesse,observed_finish_first=a.observed_finish_first,bag_deduction=a.deduce_bag or a.strategy=='score',spin_extra_inputs=a.spin_extra_inputs,setup_finesse_weight=a.setup_finesse_weight,early_setup_finish=a.early_setup_finish,forecast_coverage=a.forecast_coverage,blitz_start_level=a.start_level,speed_preset=a.speed,
                    operation_interval_ms=a.interval_ms,restart=a.restart,
                    auto_retry=False,recover_on_failure=False,farm_enabled=a.farm,
                    blitz_pulse_ms=a.pulse_ms,
                    farm=dict(continue_after_complete=not a.stop_after_complete,pc_drought=a.pc_drought,break_cycle=a.break_cycle,minimum_score_per_piece=a.minimum_score_per_piece,
                              grace_pieces=a.grace_pieces,maximum_attempts=a.attempts)),
                progress=lambda state,message:print(state,message,flush=True))
print(json.dumps({k:result[k] for k in ('placed_pieces','completed_pcs','cleared_lines','output_directory')},ensure_ascii=False))
