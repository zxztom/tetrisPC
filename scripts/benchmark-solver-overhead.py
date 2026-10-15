"""Paired warm-JVM file/inline transport benchmark, never a native PPS test."""
import argparse,json,sys,time,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.fast_solver import find_pc
from pc_lab.search_worker import close_worker
from pc_lab.solver import ROOT

p=argparse.ArgumentParser();p.add_argument('--rounds',type=int,default=20);p.add_argument('--output',type=Path,required=True)
args=p.parse_args();results=[];cases=[
    dict(name='single_O',queue='O',rows=['__XXXXXXXX','__XXXXXXXX'],hold=None,lines=2),
    dict(name='seven_piece_finish',queue='JLOSLTJ',rows=['I_________','IT________','ITTSS_____','ITSS______'],hold='Z',lines=4)]
try:
    for case in cases:
        request={k:v for k,v in case.items() if k!='name'}
        for _ in range(3):find_pc(**request,mode='soft',path_mode='ground180fine',persistent=True,timeout=1.5,save=False,kick_path=ROOT/'data/srsplus90.properties')
        timing={True:[],False:[]};baseline=None
        for n in range(args.rounds):
            for save in ((True,False) if n%2==0 else (False,True)):
                began=time.perf_counter()
                result=find_pc(**request,mode='soft',path_mode='ground180fine',persistent=True,timeout=1.5,save=save,kick_path=ROOT/'data/srsplus90.properties')
                timing[save].append((time.perf_counter()-began)*1000)
                if result['status']!='solved':raise RuntimeError('Unexpected non-solved regression: '+result['status'])
                if baseline is None:baseline=result['steps']
                if baseline!=result['steps']:raise RuntimeError('Transport changed the verified solution')
        results.append(dict(case=case['name'],rounds=args.rounds,all_solutions_identical=True,
            file_median_ms=statistics.median(timing[True]),inline_median_ms=statistics.median(timing[False]),
            file_samples_ms=timing[True],inline_samples_ms=timing[False],native_pps_measured=False))
    args.output.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps([{k:v for k,v in r.items() if 'samples' not in k} for r in results]))
finally:close_worker()
