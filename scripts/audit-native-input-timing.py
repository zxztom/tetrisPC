"""Compare executed key lifetimes with an exported native single-player TTR.

Reads key events, handling and aggregate results only. No replay seed,
future queue or reconstructed historical pieces enter live planning.
"""
import argparse,json,statistics,sys
from pathlib import Path

KEYS={'left':'moveLeft','right':'moveRight','cw':'rotateCW','ccw':'rotateCCW',
      'cw180':'rotate180','hard_drop':'hardDrop','hold':'hold'}


def audit(replay,session,pending=None):
    native=replay['replay'];down={};pairs=[];unpaired=[]
    for event in native['events']:
        if event['type'] not in ('keydown','keyup'):continue
        data=event['data'];key=data['key']
        if key not in KEYS.values():continue
        stamp=event['frame']+data.get('subframe',0)
        if event['type']=='keydown':
            if key in down:unpaired.append(dict(key=key,frame=down[key],reason='duplicate keydown'))
            down[key]=stamp
        elif key in down:
            began=down.pop(key)
            pairs.append(dict(key=key,frame=began,native_ms=(stamp-began)*1000/60))
        else:unpaired.append(dict(key=key,frame=stamp,reason='keyup without keydown'))
    unpaired.extend(dict(key=k,frame=v,reason='missing keyup') for k,v in down.items())
    pairs.sort(key=lambda item:item['frame'])
    traces=[]
    for number,step in enumerate(session['steps']+([pending] if pending else []),1):
        traces.extend(dict(item,piece_number=number) for item in step.get('input_timing',[]))
    expected=[KEYS[t['action'].removesuffix('_wall')] for t in traces]
    actual=[p['key'] for p in pairs]
    aligned=not unpaired and expected==actual
    report=dict(native_key_presses=len(pairs),recorded_controller_presses=len(traces),
                key_sequences_identical=aligned,unpaired_events=unpaired,
                verified_pieces=len(session['steps']),pending_piece_included=pending is not None,
                native_final_pieces=native['results']['stats']['piecesplaced'],
                native_handling=native['options']['handling'],
                native_finesse=native['results']['stats']['finesse'],
                lifetime_pairs=[],direction_taps_crossing_das=[],reads_seed_or_future_queue=False)
    if aligned:
        for item,trace in zip(pairs,traces):
            pair=dict(item,action=trace['action'],piece_number=trace['piece_number'],
                      controller_ms=(trace['released']-trace['started'])*1000)
            report['lifetime_pairs'].append(pair)
            if trace['action'] in ('left','right') and item['native_ms']>=native['options']['handling']['das']*1000/60:
                report['direction_taps_crossing_das'].append(pair)
        for label,values in [('native_tap_ms',[p['native_ms'] for p in report['lifetime_pairs'] if p['action'] in ('left','right')]),
                             ('controller_tap_ms',[p['controller_ms'] for p in report['lifetime_pairs'] if p['action'] in ('left','right')])]:
            report[label]=dict(count=len(values),median=statistics.median(values),maximum=max(values)) if values else None
    else:
        report['sequence_mismatch']=[dict(index=i,controller=a,native=b) for i,(a,b) in enumerate(zip(expected,actual)) if a!=b][:10]
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('replay',type=Path);parser.add_argument('session',type=Path)
    parser.add_argument('--pending',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();sys.stdout.reconfigure(encoding='utf-8')
    read=lambda path:json.loads(path.read_text(encoding='utf-8-sig'))
    result=audit(read(args.replay),read(args.session),read(args.pending) if args.pending else None)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='lifetime_pairs'},ensure_ascii=False))
