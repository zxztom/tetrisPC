"""Execution presets. PPS is a pacing target, never a promised measurement."""
import math

PRESETS={
    'extreme':dict(label='极限 · 无 PPS 限速',target_pps=0,operation_interval_ms=0,tap_ms=6,burst=True,projection_check=True,preview_stable_ms=0,capture_scale=.4,frame_wait_ms=8),
    'careful':dict(label='逐键核对',target_pps=1,operation_interval_ms=50,tap_ms=24,burst=False,preview_stable_ms=150,capture_scale=1),
    'steady':dict(label='稳定 · 目标 2 PPS',target_pps=2,operation_interval_ms=16,tap_ms=18,burst=True,preview_stable_ms=0,capture_scale=.5),
    'fast':dict(label='快速 · 目标 4 PPS',target_pps=4,operation_interval_ms=8,tap_ms=12,burst=True,preview_stable_ms=0,capture_scale=.5),
    'sprint':dict(label='冲刺 · 目标 6 PPS',target_pps=6,operation_interval_ms=3,tap_ms=6,burst=True,projection_check=False,preview_stable_ms=0,capture_scale=.5),
    'custom':dict(label='自定义间隔',target_pps=0,operation_interval_ms=20,tap_ms=24,burst=False,preview_stable_ms=150,capture_scale=1),
}

def speed_settings(name='custom',interval=None):
    if name not in PRESETS:raise ValueError('无法识别速度档位。')
    result=dict(PRESETS[name],speed_preset=name)
    if interval is not None:
        value=float(interval)
        if not math.isfinite(value) or not 0<=value<=2000:raise ValueError('操作间隔应为 0 至 2000 毫秒。')
        result['operation_interval_ms']=value
    return result
