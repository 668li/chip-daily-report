"""
chip-daily-report scripts 模块

提供芯片行业日报的自动化校验工具。

用法:
    from scripts import validate_report
    validate_report.main()

命令行:
    python scripts/validate_report.py <日报文件路径>
"""

from . import validate_report

__all__ = ['validate_report']
__version__ = '5.0.0'
