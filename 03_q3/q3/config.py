"""题目给死的参数。改这里就等于改物理假设。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATTACH = ROOT / "附件"
OUTPUT = ROOT / "output"

N_SLOTS = 144          # 一天 24h × 每小时 6 个 10 分钟
DT_HOUR = 10 / 60      # 一个时段的长度（小时），功率 kW × DT = 电量 kWh

E_MAX = 12000.0        # 额定容量 kWh
E_MIN = 1200.0         # 运行下限
E_HIGH = 10800.0       # 运行上限
E_INIT = 6000.0        # 2025-01-01 0:00
P_MAX = 5000.0         # 最大充/放电功率 kW
ETA = 0.90             # 充电、放电效率

# 费用系数（相对当时电价）
EMERGENCY_MULT = 5.0
CUT_MULT = 0.50        # 计划买多了、后来少买：差额按 50% 付违约
EXTRA_MULT = 1.50      # 后来多买：超额按 1.5 倍

# 一天里可以拿到新光伏预报的时刻
ISSUE_HOURS = (0, 6, 12, 18)

# 论文指定展示日
PAPER_DAYS = ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")
RESULT_START = "2025-02-01"
RESULT_END = "2025-12-31"
