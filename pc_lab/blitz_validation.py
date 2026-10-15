"""Side-effect-free Blitz preflight, shared by one-game and farming jobs."""
import math
from .speed import speed_settings


def validate_blitz(request,profile,timing=None):
    if request.get('seed') is not None:raise ValueError('Blitz 策略只读取实际来块，不接受种子。')
    if request.get('live_mode','visible')!='visible':raise ValueError('Blitz 只支持实际可见来块。')
    if request.get('rotation_rules','SRS+')!='SRS+':raise ValueError('Blitz 策略使用 TETR.IO SRS+，请将 CUSTOM 设为 SRS+。')
    if request.get('simulation_profile','blitz') not in ('blitz','level10','level15','20g'):raise ValueError('无法识别模拟条件。')
    if request.get('blitz_strategy','pc') not in ('pc','dpc','opportunistic','score'):raise ValueError('无法识别 Blitz 得分策略。')
    policy=request.get('finesse_policy','throughput')
    pulse=request.get('blitz_pulse_ms')
    if pulse is not None:
        if isinstance(pulse,bool) or not isinstance(pulse,(int,float)) or not math.isfinite(pulse) or not (pulse==0 or .5<=pulse<=24):
            raise ValueError('点按须为 0ms 成对发送，或 0.5 至 24ms 保持。')
        if request.get('speed_preset','custom')!='extreme':raise ValueError('短点按实验只用于极限档。')
    weight=float(request.get('setup_finesse_weight',.5))
    if not math.isfinite(weight) or not 0<=weight<=100:raise ValueError('地形按键权重须为 0 至 100。')
    if policy not in ('balanced','strict','adaptive','gravity','throughput'):raise ValueError('无法识别按键策略。')
    if not profile or profile['handling']['sdf']!=41:raise ValueError('Blitz 地面策略需要实际游戏配置 SDF=∞；请导出并载入当前 .TTC。')
    if policy in ('strict','adaptive','gravity') and profile['handling']['arr']!=0:raise ValueError('少按键优先需要游戏当前配置 ARR=0，请导出并载入已应用的 .TTC。')
    if timing is None:
        timing=request.get('timing')
        if timing is None:timing=speed_settings(request.get('speed_preset','custom'),request.get('operation_interval_ms'))
    interval=float(timing.get('operation_interval_ms',75))
    if not math.isfinite(interval) or not 0<=interval<=40:raise ValueError('Blitz 操作间隔须为 0 至 40ms，以保留锁定时间。')
    seconds=float(request.get('blitz_seconds',120));pieces=request.get('max_pieces',0)
    if not math.isfinite(seconds) or not 1<=seconds<=120:raise ValueError('Blitz 时长须为 1 至 120 秒。')
    if isinstance(pieces,bool) or not isinstance(pieces,(int,float)) or not math.isfinite(pieces) or int(pieces)!=pieces or not 0<=pieces<=2000:
        raise ValueError('Blitz 块数须为 0 至 2000 的整数。')
    return seconds,int(pieces)
