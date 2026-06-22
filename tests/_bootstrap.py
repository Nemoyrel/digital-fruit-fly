"""把 src/ 加入 sys.path，供各测试模块导入 digital_fruit_fly。"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
