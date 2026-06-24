"""统计报告生成器 — PDF/Excel/CSV"""
import json, os, csv
from typing import Dict, Any, List

class ReportGenerator:
    def __init__(self, output_dir: str = "/tmp/reports"):
        self._output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def export_csv(self, data: List[Dict], filename: str) -> str:
        path = os.path.join(self._output_dir, filename)
        if not data: return ""
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
        return path
    
    def export_json(self, data: Any, filename: str) -> str:
        path = os.path.join(self._output_dir, filename)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path
    
    def generate_user_report(self, user_stats: List[Dict]) -> str:
        return self.export_csv(user_stats, "user_report.csv")
    
    def generate_project_report(self, project_stats: Dict) -> str:
        return self.export_json(project_stats, "project_report.json")
    
    def generate_weekly_report(self, stats: Dict) -> str:
        return self.export_json(stats, f"weekly_{stats.get('week','')}.json")
