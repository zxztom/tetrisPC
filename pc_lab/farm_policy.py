"""Visible-game farming decisions and a durable, per-attempt score ledger.

No seeds, future replay events, or native input dependencies belong here.
"""
from dataclasses import dataclass
import json
import math
import time
from pathlib import Path


@dataclass(frozen=True)
class FarmPolicy:
    pc_drought: int = 0
    break_cycle: bool = False
    grace_pieces: int = 35
    minimum_score_per_piece: float = 0
    maximum_attempts: int = 0
    continue_after_complete: bool = True

    @classmethod
    def from_request(cls, request):
        raw = request.get('farm', {})
        if not isinstance(raw, dict):
            raise ValueError('刷分设置格式无效。')
        values = {}
        for name, default, limit in (('pc_drought',0,1000),('grace_pieces',35,2000),('maximum_attempts',0,10000)):
            value = raw.get(name, default)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or int(value)!=value or not 0<=value<=limit:
                raise ValueError(f'刷分参数 {name} 必须是 0 至 {limit} 的整数。')
            values[name] = int(value)
        rate = raw.get('minimum_score_per_piece',0)
        if isinstance(rate,bool) or not isinstance(rate,(int,float)) or not math.isfinite(rate) or not 0<=rate<=100000:
            raise ValueError('每块消行估分门槛须为 0 至 100000。')
        values['minimum_score_per_piece'] = float(rate)
        if not isinstance(raw.get('break_cycle',False),bool):raise ValueError('循环断链开关须为布尔值。')
        values['break_cycle'] = raw.get('break_cycle',False)
        if not isinstance(raw.get('continue_after_complete',True),bool):raise ValueError('自动下一局开关须为布尔值。')
        values['continue_after_complete']=raw.get('continue_after_complete',True)
        return cls(**values)

    def reason(self, pieces, boundaries, clear_score):
        last = boundaries[-1]['pieces'] if boundaries else 0
        if self.pc_drought and pieces-last>=self.pc_drought:
            return f'连续 {pieces-last} 块没有 PC'
        if self.break_cycle:
            # Evidence is the verified placement count, never a search timeout.
            for last_pc in boundaries:
                phase,offset=divmod(last_pc['pieces'],35)
                expected=14*phase+{10:4,20:8,0:0}.get(offset,-1000000)
                if offset not in (10,20,0) or last_pc['lines']!=expected:
                    return 'PC 段数或高度偏离 4＋4＋6'
            cycle, offset = divmod(pieces,35)
            if offset in (10,20,0) and pieces:
                wanted = 14*cycle + ({10:4,20:8,0:0}[offset])
                if not boundaries or boundaries[-1] != dict(pieces=pieces,lines=wanted):
                    return '未在 10／20／35 块边界完成 4＋4＋6'
        if self.minimum_score_per_piece and pieces>=max(1,self.grace_pieces) and clear_score/pieces<self.minimum_score_per_piece:
            return f'每块消行估分低于 {self.minimum_score_per_piece:g}（不含下降分）'
        return None


class FarmLedger:
    def __init__(self, folder):
        self.folder = Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.attempts = [];self.best = None
        self.started=time.perf_counter()

    def append(self, attempt):
        item = dict(attempt,attempt=len(self.attempts)+1)
        # A best score requires a native, complete two-minute replay.
        if item.get('native_complete') and item.get('native_replay') and isinstance(item.get('native_score'),(int,float)):
            if self.best is None or item['native_score']>self.best['native_score']:
                self.best = item.copy()
        self.attempts.append(item)
        with (self.folder/'attempts.jsonl').open('a',encoding='utf-8') as out:
            out.write(json.dumps(item,ensure_ascii=False)+'\n');out.flush()
        self.save()
        return item

    def save(self):
        result = dict(attempt_count=len(self.attempts),complete_count=sum(bool(a.get('native_complete')) for a in self.attempts),
                      abandoned_count=sum(a.get('status')=='abandoned' for a in self.attempts),
                      attempt_wall_seconds=sum(a.get('wall_seconds',0) for a in self.attempts),
                      total_wall_seconds=round(time.perf_counter()-self.started,3),best_complete=self.best,
                      scores_are_per_game=True,attempts=self.attempts)
        temp = self.folder/'summary.tmp';temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(self.folder/'summary.json')
        return result


def replay_result(path):
    """Read native stats and hard-drop events; never options or queue."""
    raw = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if raw.get('gamemode')!='blitz':raise ValueError('刷分统计只接受原版 BLITZ 录像。')
    stats = [e['data']['stats'] for e in raw['replay']['events'] if e['type']=='full']
    if not stats:raise ValueError('录像没有原生统计检查点。')
    s = raw['replay'].get('results',{}).get('stats') or stats[-1]
    return dict(native_score=s['score'],native_complete=abs(s['finaltime']-120000)<=1,
                native_pieces=s['piecesplaced'],native_lines=s['lines'],native_level=s['level'],
                native_pcs=s['clears']['allclear'],native_tspins=s['tspins'],native_finesse=s['finesse'],
                native_hard_drops=sum(e['type']=='keydown' and e['data'].get('key')=='hardDrop' for e in raw['replay']['events']),
                native_replay=str(Path(path).resolve()))
