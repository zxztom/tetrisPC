"""Build random CUSTOM settings from the user's exported .TTP."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.solver import ROOT
from pc_lab.blitz import BLITZ_OPTIONS,gravity
base=json.loads((ROOT/'output/custom-before-blitz.ttp').read_text(encoding='utf-8-sig'))
folder=ROOT/'output/blitz-configs';folder.mkdir(exist_ok=True)
common=dict(base,**{k:v for k,v in BLITZ_OPTIONS.items() if k in base})
common.update(seed_random=True,seed=0,levelstatic=False,masterlevels=False,
              levelgspeed=.007,startinglevel=1,objective_result='score',
              absolute_lines=False,slot_counter1='timer',mission='CUSTOM BLITZ SIMULATION',
              g=1/60,countdown_count=3,countdown_interval=1000,
              precountdown=3000,prestart=1000,zoominto='slow',stride=False)
profiles={'blitz':common,'level10':dict(common,levels=False,g=gravity(10)),
          'level15':dict(common,levels=True,startinglevel=15,levelstatic=True,levelstaticspeed=10000,g=gravity(15)),
          '20g':dict(common,levels=False,g=20,gravitymay20g=True)}
for name,config in profiles.items():
    path=folder/f'{name}-random.ttp'
    path.write_text(json.dumps(config,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(path)
