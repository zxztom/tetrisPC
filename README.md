# TETR.IO 连续 PC 与 Blitz 实验室

Windows 单人模式自动玩家：从窗口截图识别棋盘、当前块、Hold 与 Next，使用有限预览搜索合法路线，再发送按键并核对实际落点。在线程序不读取游戏种子或录像未来来块。

## 没玩过现代块？从这里读起

**PC（全清）**是消行后棋盘一格不剩。**446**表示先后累计消4、4、6行并各做一次全清，共35块＝5袋；**连续纯四行**在七次全清后对齐七袋相位，即`4444444`，共70块＝10袋。六个4只有60块，还没有完成这一袋相位循环。循环不代表随机来块顺序会重复，也不保证每局都有同一套摆法。

先看[零基础图解：446与七次四行PC为什么能循环](docs/BEGINNER_PC_GUIDE.zh-CN.md)，里面有七种块、Hold、七袋、格数计算和真实十块PC的过程图。

## 当前实测

原版 SOLO → BLITZ 完整两分钟最高 **2,788,043 分**：749块、**6.24 PPS**、Level 17、57 PC、17 T-spin。最近四个独立随机完整局为2,709,575 / 2,186,726 / 2,788,043 / 2,783,717；三局过260万，四局都超过6 PPS。成绩有随机波动，进入Level 17不等于固定Level 17打满两分钟。

- [最高分原生录像](evidence/blitz-2788043.ttr)：拖进TETR.IO查看。
- [原生结果截图](ui/blitz-best-native.png)。
- [验收摘要](evidence/blitz-throughput-verification.json)、[原生统计审计](evidence/blitz-2788043-audit.json)。
- [冲分策略与实测](docs/260万验收与速度优先.md)。
- [理论分数与278万拆分](docs/Blitz理论与278万拆分.md)。

推荐默认 **PC搜索＋throughput（冲分与速度优先）＋extreme（极限）＋成对点按**。极限档没有PPS节拍限制；finesse faults仅用于诊断输入开销，不作为得分目标。纯四行七次PC、4＋4＋6 DPC及其他操作取舍仍保留。

## 安装与启动

需要Windows、Python 3.10+及TETR.IO桌面客户端。客户端、Java、求解器和本机配置不随仓库上传。

```powershell
python -m pip install -r requirements.txt
./scripts/setup.ps1
./scripts/launch.ps1
```

`setup.ps1`下载便携Java 17、solution-finder并编译Java搜索组件；下载内容留在本项目tools目录。使用[TETR.IO官方客户端](https://tetr.io/about/desktop/)，解压到`tetrio-desktop/`，确保主程序路径为`tetrio-desktop/TETR.IO.exe`。若使用Codex的Python环境，启动脚本也会检测其运行时。

打开实验室后：

1. 在TETR.IO的CONFIG → EXPORT SETTINGS导出当前`.TTC`，载入网页。
2. 选择Blitz、PC搜索、冲分与速度优先、极限档、成对点按。
3. 点击生成配置，下载并导入TETR.IO，再点击“已导入游戏，应用此配置”。推荐实测handling为ARR 0、DAS 1.5F、DCD 0、SDF ∞；180°需有键盘绑定。
4. 单局测试先打开SOLO → BLITZ；程序等待随机新局。自动刷分可从HOME、Blitz启动页或结果页开始。

本地界面：<http://127.0.0.1:8787/>。双击`启动PC实验室.cmd`也可启动。`开始随机PC.cmd`用于纯PC练习入口，和Blitz刷分入口分开。

**F8、Esc、失焦或画面与计划不一致时释放按键并停止。** 不一致后不补发修正或硬降。原始日志写入`output/`，不进入版本库。

## 连续刷分

勾选“自动刷分”和“每局打完后自动开始下一局”，尝试局数0表示持续。每局保存独立原生成绩和录像，再回HOME开新的随机队列；不用AGAIN / R重复同一队列。最高分只取一局完整分数，不跨局相加。提前放弃门槛尚未校准，界面暂不可用。

```powershell
python scripts/run-blitz.py --strategy pc --finesse throughput --speed extreme --pulse-ms 0 --farm --attempts 4
```

## PC方法与研究

- [不知道种子的连续PC说明](docs/不知道种子的连续PC说明.md)。
- 网页`/manual`为4＋4＋6图解，`/pure4-manual`为七次纯四行方法。
- `/blitz-manual`为当前原版成绩与推荐配置，`/blitz-research`为历史纪录研究，`/blitz-bounds`为理论比较。
- [TETR.IO规则核查与旋转策略](docs/TETR.IO规则核查与旋转策略.md)。
- [持续DPC理论分数区间](docs/连续DPC理论分数区间.md)。

理论上界只约束计分事件、格数和T库存，没有证明所有地形、随机来块和输入时间可达。纪录效率外推约350万也不是当前程序的实测成绩或保证。

## 开发与依赖

```powershell
python -m unittest discover -s tests
./scripts/build-bridge.ps1
```

最近完整检查208项通过。Python负责图像识别、规划、输入和本地界面；Java桥接solution-finder。部分回归需要先安装求解器依赖。复算特定历史局的脚本需要对应原始`output/`，完整开发日志未随仓库上传。

第三方资料与组件：[solution-finder](https://github.com/knewjade/solution-finder)、[Best Chance Field](https://knewjade.github.io/best-chance-field/)、[Hard Drop PC与DPC](https://harddrop.com/wiki/DPC_Setups)。它们各自的许可与署名保持独立；TETR.IO客户端不包含在本仓库中。

历史开发阶段的说明与旧成绩保留在[早期使用与验证记录](docs/早期使用与验证记录.md)，当前配置与结果以本文及最新验收说明为准。
