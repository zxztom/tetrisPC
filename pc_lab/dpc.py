"""Build a standard DPC structure before searching its small finish."""
from .openers import dpc_setups
from .fast_solver import find_pc


def seeded_dpc(queue,current,held_source,cycle_start,cycle_end,cancelled=lambda:False):
    known={i:p for i,p in enumerate(queue)}
    held=queue[held_source] if held_source is not None else None
    for prefix in dpc_setups(known,current,held_source,cycle_start,cancelled):
        consumed=prefix[-1]["queue_index_after"]
        after=prefix[-1]["board_after"]
        cleared=sum(len(s["cleared_rows"]) for s in prefix)
        held_after=prefix[-1]["hold_after"]
        remaining=6-cleared
        tail=find_pc(queue[current+consumed:cycle_end],rows=list(reversed(after[:remaining])),
                     hold=held_after,lines=remaining,mode="soft",path_mode="instant",timeout=8,
                     cancelled=cancelled)
        if tail["status"]!="solved":continue
        steps=list(prefix)
        for raw in tail["steps"]:
            copied=dict(raw,queue_index_before=raw["queue_index_before"]+consumed,
                        queue_index_after=raw["queue_index_after"]+consumed)
            steps.append(copied)
        assert len(steps)==15 and sum(len(s["cleared_rows"]) for s in steps)==6
        tail.update(steps=steps,target_lines=6,required_pieces=15,
                    queue_index=steps[-1]["queue_index_after"],dpc_setup=prefix[0].get("opener"),
                    initial_board=steps[0]["board_before"],total_cleared_lines=6,
                    message="DPC 首包结构与六行 PC 完成路径已验证。")
        return tail
    return find_pc(queue[current:cycle_end],hold=held,lines=6,mode="soft",path_mode="instant",
                   timeout=25,cancelled=cancelled)
