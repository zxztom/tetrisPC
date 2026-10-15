"""Paired unfiltered random offline cases; oracle never enters live code."""
import argparse,hashlib,importlib.util,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.fast_solver import find_pc
from pc_lab.search_worker import close_worker
from pc_lab.solver import ROOT

p=argparse.ArgumentParser();p.add_argument('--cases',type=int,default=3);p.add_argument('--pieces',type=int,default=700)
p.add_argument('--compare-wells',action='store_true')
p.add_argument('--output',type=Path,required=True);a=p.parse_args();sys.stdout.reconfigure(encoding='utf-8')
spec=importlib.util.spec_from_file_location('visible_benchmark',ROOT/'scripts/benchmark-blitz-visible.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
randomizer=random.SystemRandom();reports=[]
try:
    find_pc('JLOSTZIJLO',lines=4,timeout=1.2,persistent=True,path_mode='ground180',save=False)
    for case in range(a.cases):
        oracle=''.join(''.join(randomizer.sample('IJLOSTZ',7)) for _ in range((a.pieces+35)//7+1))
        for enabled in (False,True):
            report=module.simulate(oracle,'balanced','score',a.pieces,next_count=5,
                deduce_bag=True if a.compare_wells else enabled,multi_well=enabled if a.compare_wells else False)
            report.update(case=case+1,oracle_fingerprint=hashlib.sha256(oracle.encode()).hexdigest(),
                queue_origin='unfiltered offline SystemRandom seven-bag; paired alternatives share this case',initial_active=oracle[0])
            reports.append(report);a.output.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in report.items() if k not in ('pc_boundaries','setup_probe_diagnostics')},ensure_ascii=False),flush=True)
finally:close_worker()
