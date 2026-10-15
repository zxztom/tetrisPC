"""Paired strategy regression check; isolated unseen random seven-bag queues.

Only active/Hold/five Next reach the planner. This is a geometry and score
comparison at equal piece counts, not a native two-minute score or PPS test.
"""
import argparse
import hashlib
import importlib.util
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pc_lab.fast_solver import find_pc
from pc_lab.search_worker import close_worker
from pc_lab.solver import ROOT


def summarize(reports):
    result = {}
    for name in dict.fromkeys(r['variant'] for r in reports):
        rows = [r for r in reports if r['variant'] == name]
        scores = [r['clear_score'] for r in rows]
        result[name] = dict(cases=len(rows), errors=sum(r['error'] is not None for r in rows),
                            mean_score=statistics.mean(scores), median_score=statistics.median(scores),
                            minimum_score=min(scores), maximum_score=max(scores),
                            mean_pcs=statistics.mean(r['pcs'] for r in rows),
                            mean_tspins=statistics.mean(r['tspins'] for r in rows),
                            mean_planner_seconds=statistics.mean(r['planner_wall_seconds'] for r in rows))
        paired = []
        for row in rows:
            base = next((r for r in reports if r['case'] == row['case'] and r['variant'] == 'pc'), None)
            if base is not None:
                paired.append(row['clear_score'] - base['clear_score'])
        result[name]['paired_against_pc'] = dict(cases=len(paired), wins=sum(x > 0 for x in paired),
            losses=sum(x < 0 for x in paired), ties=sum(x == 0 for x in paired),
            mean_score_delta=statistics.mean(paired) if paired else None)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases', type=int, default=6)
    p.add_argument('--pieces', type=int, default=666)
    p.add_argument('--compare-pc-bag',action='store_true')
    p.add_argument('--compare-throughput',action='store_true')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.cases < 1 or a.pieces < 1:
        p.error('cases and pieces must be positive')
    sys.stdout.reconfigure(encoding='utf-8')
    spec = importlib.util.spec_from_file_location('visible_benchmark', ROOT/'scripts/benchmark-blitz-visible.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Include actual score defaults; the older --compare-score intentionally
    # disables these newer heuristics and cannot qualify the current default.
    variants = [('pc', 'pc', False, False, False), ('pc_observed', 'pc', False, False, True),
                ('dpc', 'dpc', False, False, False), ('score_current', 'score', True, True, False)]
    if a.compare_pc_bag:
        variants=[('pc','pc',False,False,False),('pc_bag','pc',True,False,False)]
    if a.compare_throughput:
        variants=[('pc','pc',False,False,False),('pc_throughput','pc',False,False,False)]
    reports = []
    randomizer = random.SystemRandom()
    try:
        find_pc('JLOSTZIJLO', lines=4, timeout=1.2, persistent=True,
                path_mode='ground180', save=False, kick_path=ROOT/'data/srsplus90.properties')
        for case in range(a.cases):
            oracle = ''.join(''.join(randomizer.sample('IJLOSTZ', 7)) for _ in range((a.pieces+35)//7+1))
            # Rotate processing order so a single variant is not always cold.
            order = variants[case % len(variants):] + variants[:case % len(variants)]
            for name, strategy, deduction, wells, observed_first in order:
                policy='throughput' if name=='pc_throughput' else 'balanced'
                r = module.simulate(oracle, policy, strategy, a.pieces, next_count=5,
                                    deduce_bag=deduction, multi_well=wells, observed_first=observed_first)
                r.update(case=case+1, variant=name, oracle_fingerprint=hashlib.sha256(oracle.encode()).hexdigest(),
                         queue_origin='independent unfiltered SystemRandom seven-bag; shared only within paired offline case')
                reports.append(r)
                payload = dict(target_pieces=a.pieces, target_cases=a.cases, preview_count=5,
                    native_verified=False, real_time_execution_simulated=False, drop_points_included=False,
                    selection='all cases included; no starting queue filter; no queue saved or sent to live controller',
                    reports=reports, summary=summarize(reports))
                a.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps({k:r[k] for k in ('case','variant','pieces','clear_score','pcs','tspins','planner_wall_seconds','error')}, ensure_ascii=False), flush=True)
        print(json.dumps(summarize(reports), ensure_ascii=False), flush=True)
    finally:
        close_worker()


if __name__ == '__main__':
    main()
