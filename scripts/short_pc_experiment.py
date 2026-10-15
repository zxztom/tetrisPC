"""Offline rejected candidate; not enabled by the live application.

Three unfiltered paired cases showed no consistent score gain.
"""
from pc_lab.engine import empty_board
from pc_lab.finesse import estimated_faults

def try_short_pc(self,state):
    """Only an entirely visible two-line finish may replace a setup.

    No speculative queue, and no repeated probe on recursive choose().
    Preserve an already verified PC finish and a selected DPC setup.
    """
    if not self.request.get('short_pc',False):return False
    if getattr(self,'last_short_pc_probe',None)==len(self.steps):return False
    if self.prefix and self.prefix[0].get('strategy') in ('pc_finish','pc_score_finish','dpc_setup'):return False
    board=tuple(state['board'])
    if any(row!='__________' for row in board[2:]):return False
    missing=20-sum(c!='_' for row in board[:2] for c in row)
    if missing<=0 or missing%4:return False
    required=missing//4;queue=state['active']+state['next']
    if required>len(queue)+bool(state['hold']):return False
    self.last_short_pc_probe=len(self.steps)
    self.two_row_probes+=1
    from .fast_solver import find_pc
    try:
        proposal=find_pc(queue,rows=list(reversed(board[:2])),hold=state['hold'],lines=2,
            mode='soft',timeout=.008,persistent=True,save=False,kick_path=self.kick_path,
            path_mode=self.search_path_mode(),cancelled=self.stopped,allow_hold=state['hold_available'])
    except (TimeoutError,ValueError):return False
    if proposal['status']!='solved' or len(proposal['steps'])!=required:return False
    plan=proposal['steps']
    if tuple(plan[0]['board_before'])!=board or tuple(plan[-1]['board_after'])!=empty_board():return False
    # Respect the selected policy even if a future solver relaxes routes.
    if sum(estimated_faults(s['piece'],s['cells'],s['actions']) for s in plan)>self.fault_allowance():return False
    self.pc_remaining=2;self.two_row_plans+=1
    self.prefix=[dict(s,strategy='pc_finish',two_row_opportunity=True) for s in plan]
    return True

