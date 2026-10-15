"""Cycle definitions; piece sources are tracked separately from Hold."""

def cycle_spec(name='dpc'):
    if name=='dpc':return (4,4,6),35
    if name=='pure4':return (4,4,4,4,4,4,4),70
    raise ValueError('循环方式须为 dpc 或 pure4。')


PURE4_BAG_GROUPS=('7+3','4+6','1+7+2','5+5','2+7+1','6+4','3+7')
