"""One periodic import/evaluation/export, suitable for an IT-managed scheduler."""
import argparse
import json
from pathlib import Path

from . import storage
from .importer import import_excel
from .report import build_pdf
from .service import generate_report


def main():
    parser = argparse.ArgumentParser(description="周期仓库评估")
    parser.add_argument("--warehouse", required=True, help="网页中仓库的ID")
    parser.add_argument("--excel", type=Path, help="可选：先导入新的现有格式Excel")
    parser.add_argument("--cycle", choices=["week", "month"], default="week")
    parser.add_argument("--cutoff", help="YYYY-MM-DD，默认最新数据日期")
    parser.add_argument("--output", type=Path, default=storage.ROOT / "output" / "pdf" / "periodic-report.pdf")
    args = parser.parse_args()
    storage.initialize()
    try:
        summary = import_excel(args.warehouse, args.excel.name, args.excel.read_bytes()) if args.excel else None
        report = generate_report(args.warehouse, args.cycle, args.cutoff)
        content = build_pdf(report)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps({"report_id": report["id"], "output": str(args.output.resolve()), "import": summary}, ensure_ascii=True))


if __name__ == "__main__":
    main()
