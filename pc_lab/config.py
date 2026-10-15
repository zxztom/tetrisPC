"""TETR.IO's exported JSON .TTC configuration; never read login storage."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

ACTION_NAMES={'left':'moveLeft','right':'moveRight','down':'softDrop','hard_drop':'hardDrop',
              'ccw':'rotateCCW','cw':'rotateCW','hold':'hold','retry':'retry','forfeit':'exit'}
GUIDELINE={'moveLeft':['ARROWLEFT'],'moveRight':['ARROWRIGHT'],'softDrop':['ARROWDOWN'],
           'hardDrop':['SPACE'],'rotateCCW':['CONTROLLEFT','KEYZ'],'rotateCW':['ARROWUP','KEYX'],
           'rotate180':['KEYA'],'hold':['SHIFTLEFT','KEYC'],'exit':['ESCAPE'],'retry':['KEYR']}
WASD=dict(GUIDELINE,moveLeft=['KEYA'],moveRight=['KEYD'],softDrop=['KEYW'],
          rotateCW=['ARROWRIGHT'],rotateCCW=['ARROWLEFT'],rotate180=['ARROWUP'],hardDrop=['KEYS'])
SPECIAL={'ARROWLEFT':0x25,'ARROWRIGHT':0x27,'ARROWDOWN':0x28,'ARROWUP':0x26,
         'SPACE':0x20,'ENTER':0x0D,'TAB':9,'BACKSPACE':8,'ESCAPE':0x1B,'CAPSLOCK':0x14,
         'SHIFTLEFT':0xA0,'SHIFTRIGHT':0xA1,'CONTROLLEFT':0xA2,'CONTROLRIGHT':0xA3,
         'ALTLEFT':0xA4,'ALTRIGHT':0xA5,'HOME':0x24,'END':0x23,'INSERT':0x2D,'DELETE':0x2E,
         'PAGEUP':0x21,'PAGEDOWN':0x22,'SEMICOLON':0xBA,'EQUAL':0xBB,'COMMA':0xBC,
         'MINUS':0xBD,'PERIOD':0xBE,'SLASH':0xBF,'BACKQUOTE':0xC0,'BRACKETLEFT':0xDB,
         'BACKSLASH':0xDC,'BRACKETRIGHT':0xDD,'QUOTE':0xDE,'NUMPADADD':0x6B,
         'NUMPADSUBTRACT':0x6D,'NUMPADMULTIPLY':0x6A,'NUMPADDIVIDE':0x6F,'NUMPADDECIMAL':0x6E,'NUMPADENTER':0x10D}

def key_code(code):
    if not isinstance(code,str):raise ValueError('按键名必须为 TETR.IO 的键盘代码。')
    code=code.upper()
    if code in SPECIAL:return SPECIAL[code]
    if len(code)==4 and code.startswith('KEY') and 'A'<=code[-1]<='Z':return ord(code[-1])
    if len(code)==6 and code.startswith('DIGIT') and code[-1].isdigit():return ord(code[-1])
    if len(code)==7 and code.startswith('NUMPAD') and code[-1].isdigit():return 0x60+int(code[-1])
    if code.startswith('F') and code[1:].isdigit() and 1<=int(code[1:])<=24:return 0x70+int(code[1:])-1
    raise ValueError(f'暂不支持此键盘绑定：{code}；控制器绑定不能用于自动按键。')

def parse_config(raw):
    if isinstance(raw,(str,bytes)):raw=json.loads(raw)
    if not isinstance(raw,dict) or not isinstance(raw.get('controls'),dict) or not isinstance(raw.get('handling'),dict):
        raise ValueError('请选择 CONFIG → EXPORT SETTINGS 导出的 .TTC；CUSTOM 的房间设置不是操作配置。')
    controls=raw['controls'];style=controls.get('style')
    if style=='guideline':bindings=GUIDELINE
    elif style=='wasd':bindings=WASD
    elif style=='custom':bindings=controls.get('custom',{})
    else:raise ValueError('无法识别控制方案。')
    keys={};chosen={}
    for action,name in ACTION_NAMES.items():
        choices=bindings.get(name,[])
        if not isinstance(choices,list):raise ValueError(f'{name} 绑定格式无效。')
        for code in choices:
            try:vk=key_code(code)
            except ValueError:continue
            if action!='forfeit' and vk in (0x77,0x1B):continue
            keys[action]=vk;chosen[action]=code;break
        if action not in keys:raise ValueError(f'{name} 没有可用的键盘绑定。')
    if len(set(v for k,v in keys.items() if k!='forfeit'))!=len(keys)-1:
        raise ValueError('多个游戏动作共用按键，无法可靠执行。')
    handling={}
    for name,default,maximum in (('arr',2,5),('das',10,20),('dcd',2,20),('sdf',6,41)):
        value=float(raw['handling'].get(name,default))
        if not math.isfinite(value) or not 0<=value<=maximum:raise ValueError(f'{name} 参数无效。')
        handling[name]=value
    canonical=json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return {'keys':keys,'bindings':chosen,'handling':handling,'style':style,
            'sha256':hashlib.sha256(canonical.encode()).hexdigest()}

def optimize_config(raw,speed_preset='steady',paired_taps=False):
    parse_config(raw)
    from .speed import speed_settings
    speed_settings(speed_preset)
    result=deepcopy(raw)
    # Preserve the user's bindings, display, sound, account preferences.
    result['handling'].update(arr=0,das={'careful':10,'steady':6,'fast':4,'sprint':3,'extreme':3,'custom':6}[speed_preset],dcd=0,sdf=41)
    if speed_preset=='extreme' and paired_taps:
        result['handling']['das']=1.5
    if speed_preset in ('fast','sprint','extreme'):
        result['handling']['safelock']=False
        # Native keyup latency can stretch a nominal 6ms tap past 25ms.
        # Keep a 50ms DAS margin and reset charge when reversing direction.
        result['handling']['cancel']=True
        # These effects move/cover cells and delay pixel verification.
        result.setdefault('video',{}).update(graphics='minimal',actiontext='off',bounciness=0,shakiness=0,particles=0)
    return result

def load_profile(path=None):
    from .solver import ROOT
    path=Path(path) if path else ROOT/'output/current-config.ttc'
    if not path.is_file():return None
    if path.stat().st_size>1024*1024:raise ValueError('配置文件过大。')
    profile=parse_config(path.read_text(encoding='utf-8-sig'))
    profile['path']=str(path.resolve())
    return profile

def save_current(raw):
    from .solver import ROOT
    profile=parse_config(raw)
    folder=ROOT/'output';folder.mkdir(exist_ok=True)
    target=folder/'current-config.ttc'
    if target.exists():
        old=target.read_bytes();digest=hashlib.sha256(old).hexdigest()[:12]
        backup=folder/f'config-backup-{digest}.ttc'
        if not backup.exists():backup.write_bytes(old)
    target.write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
    profile['path']=str(target)
    return profile
