import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.live import run_live

parser=argparse.ArgumentParser()
parser.add_argument('--seed',type=int,default=None,help='Optional developer replay mode; ordinary play reads Next only.')
parser.add_argument('--cycles',type=int,default=1)
parser.add_argument('--pcs',type=int,default=0)
parser.add_argument('--cycle-mode',choices=('dpc','pure4'),default='dpc')
parser.add_argument('--rotation-rules',choices=('SRS','SRS+'),default='SRS+')
parser.add_argument('--restart',action='store_true')
parser.add_argument('--visible',action='store_true')
parser.add_argument('--samples',type=int,default=8)
parser.add_argument('--auto-retry',action='store_true')
parser.add_argument('--max-retries',type=int,default=3)
parser.add_argument('--wait-start',action='store_true')
parser.add_argument('--interval-ms',type=float,default=None)
parser.add_argument('--speed',choices=('careful','steady','fast','sprint','custom'),default='custom')
parser.add_argument('--resume',type=Path,default=None)
parser.add_argument('--config',type=Path,default=None)
parser.add_argument('--recover',action='store_true',help='Clear/restart after PC failure; max-retries 0 is unlimited.')
args=parser.parse_args()
sys.stdout.reconfigure(encoding='utf-8')
try:
    result=run_live({'seed':args.seed,'max_cycles':args.cycles,'max_pcs':args.pcs,'restart':args.restart,
                     'cycle_mode':args.cycle_mode,'rotation_rules':args.rotation_rules,
                     'resume_from_recording':str(args.resume.resolve()) if args.resume else None,
                     'live_mode':'seeded' if args.seed is not None and not args.visible else 'visible','forecast_samples':args.samples,
                     'auto_retry':args.auto_retry,'max_retries':args.max_retries,'wait_start':args.wait_start,
                     'operation_interval_ms':args.interval_ms,'recover_on_failure':args.recover,
                     'speed_preset':args.speed,
                     'config_path':str(args.config.resolve()) if args.config else None},
                    progress=lambda state,message:print(state,message,flush=True))
    print(json.dumps({k:result[k] for k in ('status','completed_cycles','completed_pcs','cleared_lines','output_directory')},ensure_ascii=False))
except Exception as exc:
    print(str(exc),flush=True)
    raise SystemExit(1)
