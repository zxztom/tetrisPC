"""Proven 4+4+6 loops and consecutive streaks from verified placements."""


def dpc_cycles(boundaries,steps):
    points=[dict(pieces=0,lines=0)]+list(boundaries)
    records=[];streak=0;maximum=0;last_end=None
    for index,point in enumerate(points[1:],1):
        end=point['pieces'];valid=False
        if end>=35 and end%35==0:
            start=end-35;phase=start//35
            expected=[dict(pieces=start,lines=14*phase),dict(pieces=start+10,lines=14*phase+4),
                      dict(pieces=start+20,lines=14*phase+8),dict(pieces=end,lines=14*phase+14)]
            if points[max(0,index-3):index+1]==expected and len(steps)>=end:
                sources=[s.get('source_index') for s in steps[start:end]]
                valid=all(isinstance(s,int) and not isinstance(s,bool) for s in sources) and sorted(sources)==list(range(start,end))
            if valid:
                streak=streak+1 if last_end==start and streak else 1
                maximum=max(maximum,streak);last_end=end
                records.append(dict(start_piece=start,end_piece=end,phase=phase+1,
                                    source_start=start,source_end=end-1,complete_bags=5))
                continue
        if streak and point not in (dict(pieces=last_end+10,lines=14*(last_end//35)+4),
                                    dict(pieces=last_end+20,lines=14*(last_end//35)+8)):
            streak=0
    if streak:
        last_pc=points[-1]['pieces']
        next_pc=next(n for n in (last_end+10,last_end+20,last_end+35) if n>last_pc)
        if len(steps)>=next_pc:streak=0
    return dict(verified_cycles=len(records),current_consecutive_cycles=streak,
                maximum_consecutive_cycles=maximum,cycles=records)
