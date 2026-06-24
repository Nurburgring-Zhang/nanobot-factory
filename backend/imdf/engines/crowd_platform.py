"""众包团队管理+人员统计引擎"""
from __future__ import annotations
import time
import statistics
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class CrowdWorker:
    """众包人员"""
    id: str
    name: str
    skills: List[str] = field(default_factory=list)
    workload: int = 0  # current assigned tasks count
    quality_score: float = 0.0
    status: str = "idle"  # idle, busy, offline
    earnings: float = 0.0
    _completed_tasks: int = 0
    _total_quality_sum: float = 0.0
    _quality_count: int = 0

    def update_quality(self, score: float):
        self._total_quality_sum += score
        self._quality_count += 1
        self.quality_score = round(self._total_quality_sum / self._quality_count, 2)

    def add_earnings(self, amount: float):
        self.earnings = round(self.earnings + amount, 2)


@dataclass
class CrowdTeam:
    """众包团队"""
    id: str
    name: str
    leader: Optional[CrowdWorker] = None
    members: List[CrowdWorker] = field(default_factory=list)
    active_projects: List[str] = field(default_factory=list)

    def add_member(self, worker: CrowdWorker):
        if worker not in self.members:
            self.members.append(worker)

    def remove_member(self, worker_id: str):
        self.members = [m for m in self.members if m.id != worker_id]


class CrowdPlatform:
    """众包平台 - 管理人员注册、任务分配、质量评分、薪酬计算
    高级功能: 金标准混入检测 / 多数表决 / 质检系数自动调整
    """

    def __init__(self):
        self.workers: Dict[str, CrowdWorker] = {}
        self.teams: Dict[str, CrowdTeam] = {}
        self.tasks: Dict[str, dict] = {}
        self._task_log: List[dict] = []
        # F5.3: 高级质检数据
        self._golden_items: Dict[str, dict] = {}  # golden_id -> {answer, ...}
        self._golden_responses: Dict[str, List[dict]] = {}  # golden_id -> [{worker_id, answer, correct}]
        self._votes: Dict[str, Dict[str, List[str]]] = {}  # task_id -> {field -> [answers]}
        self._quality_coefficients: Dict[str, float] = {}  # worker_id -> dynamic coefficient

    # ── worker management ──

    def register_worker(self, worker_id: str, name: str, skills: List[str]) -> CrowdWorker:
        w = CrowdWorker(id=worker_id, name=name, skills=skills)
        self.workers[worker_id] = w
        return w

    def get_worker(self, worker_id: str) -> Optional[CrowdWorker]:
        return self.workers.get(worker_id)

    # ── team management ──

    def create_team(self, team_id: str, name: str, leader_id: str) -> CrowdTeam:
        leader = self.workers.get(leader_id)
        t = CrowdTeam(id=team_id, name=name, leader=leader)
        if leader:
            t.add_member(leader)
        self.teams[team_id] = t
        return t

    # ── auto skill-based task assignment ──

    def assign_task(self, task_id: str, required_skills: List[str],
                    max_workers: int = 1) -> List[CrowdWorker]:
        """自动按技能分配任务：找到匹配技能且负载最低的 worker"""
        candidates: List[Tuple[int, CrowdWorker]] = []
        for w in self.workers.values():
            if w.status == "offline":
                continue
            if not required_skills:
                # 如果没有技能要求，所有空闲worker都可选
                candidates.append((w.workload, w, 0))
                continue
            match_count = len(set(required_skills) & set(w.skills))
            if match_count > 0:
                candidates.append((w.workload, w, match_count))
        candidates.sort(key=lambda x: (x[0], -x[2]))

        assigned = []
        for _, w in candidates[:max_workers]:
            w.workload += 1
            w.status = "busy"
            assigned.append(w)

        self.tasks[task_id] = {
            "task_id": task_id,
            "required_skills": required_skills,
            "assigned_workers": [w.id for w in assigned],
            "status": "assigned",
            "created_at": time.time(),
        }
        return assigned

    # ── progress tracking ──

    def track_progress(self, task_id: str, worker_id: str,
                       status: str, note: str = ""):
        """记录单个 worker 的任务进度"""
        self._task_log.append({
            "task_id": task_id,
            "worker_id": worker_id,
            "status": status,
            "note": note,
            "timestamp": time.time(),
        })
        if status in ("completed", "done"):
            w = self.workers.get(worker_id)
            if w:
                w.workload = max(0, w.workload - 1)
                if w.workload == 0:
                    w.status = "idle"
                w._completed_tasks += 1
            # 任务所有 assigned worker 都完成则标记 done
            task = self.tasks.get(task_id)
            if task:
                task["status"] = "in_progress"
                all_done = all(
                    any(
                        e["worker_id"] == wid and e["status"] in ("completed", "done")
                        for e in self._task_log if e["task_id"] == task_id
                    )
                    for wid in task["assigned_workers"]
                )
                if all_done:
                    task["status"] = "completed"

    # ── quality evaluation ──

    def evaluate_quality(self, worker_id: str, score: float):
        w = self.workers.get(worker_id)
        if w:
            w.update_quality(score)

    # ── payment calculation ──

    def calculate_payment(self, worker_id: str, base_rate: float = 10.0,
                          quality_bonus: float = 5.0) -> float:
        """薪酬 = 基础费率 * 任务数 + 质量奖金 (分数>=80)"""
        w = self.workers.get(worker_id)
        if not w:
            return 0.0
        bonus = quality_bonus if w.quality_score >= 80 else 0.0
        payment = base_rate * w._completed_tasks + bonus
        w.add_earnings(payment)
        return payment

    # ── F5.3: 金标准混入检测 ──

    def add_golden_item(self, golden_id: str, task_id: str,
                         correct_answer: str, field_name: str = "label",
                         metadata: dict = None) -> dict:
        """添加金标准数据 - 混入众包任务流中检测标注质量

        Args:
            golden_id: 金标准条目唯一ID
            task_id: 关联的任务ID (用于混入)
            correct_answer: 正确答案
            field_name: 标注字段名
            metadata: 额外元数据

        Returns:
            金标准条目信息
        """
        item = {
            "golden_id": golden_id,
            "task_id": task_id,
            "correct_answer": correct_answer,
            "field_name": field_name,
            "metadata": metadata or {},
            "created_at": time.time(),
            "response_count": 0,
            "correct_count": 0,
        }
        self._golden_items[golden_id] = item
        if golden_id not in self._golden_responses:
            self._golden_responses[golden_id] = []
        return item

    def check_golden(self, golden_id: str, worker_id: str,
                     worker_answer: str) -> dict:
        """检测单个worker对金标准条目的回答是否正确

        Returns:
            {correct: bool, golden_answer: str, worker_answer: str, adjusted_quality: float}
        """
        item = self._golden_items.get(golden_id)
        if not item:
            return {"error": "Golden item not found", "golden_id": golden_id}

        correct = (worker_answer.strip().lower() == item["correct_answer"].strip().lower())
        item["response_count"] += 1
        if correct:
            item["correct_count"] += 1

        response = {
            "golden_id": golden_id,
            "worker_id": worker_id,
            "answer": worker_answer,
            "correct": correct,
            "timestamp": time.time(),
        }
        self._golden_responses[golden_id].append(response)

        # 自动调整质检系数
        adjusted = self._adjust_quality_from_golden(worker_id, correct)

        return {
            "correct": correct,
            "golden_answer": item["correct_answer"],
            "worker_answer": worker_answer,
            "golden_accuracy": round(item["correct_count"] / max(item["response_count"], 1), 3),
            "adjusted_quality_coefficient": adjusted,
        }

    def get_golden_stats(self, golden_id: str = None) -> dict:
        """获取金标准检测统计"""
        if golden_id:
            item = self._golden_items.get(golden_id)
            if not item:
                return {}
            responses = self._golden_responses.get(golden_id, [])
            return {
                "golden_id": golden_id,
                "correct_answer": item["correct_answer"],
                "response_count": item["response_count"],
                "correct_count": item["correct_count"],
                "accuracy": round(item["correct_count"] / max(item["response_count"], 1), 3),
                "responses": responses,
            }

        items = []
        for gid, item in self._golden_items.items():
            items.append({
                "golden_id": gid,
                "correct_answer": item["correct_answer"],
                "response_count": item["response_count"],
                "correct_count": item["correct_count"],
                "accuracy": round(item["correct_count"] / max(item["response_count"], 1), 3),
            })
        return {"total_golden_items": len(items), "items": items}

    # ── F5.3: 质检系数自动调整 ──

    def _adjust_quality_from_golden(self, worker_id: str, correct: bool) -> float:
        """基于金标准表现自动调整质检系数

        答对: 系数+0.05 (最高1.5)
        答错: 系数-0.15 (最低0.3)
        """
        current = self._quality_coefficients.get(worker_id, 1.0)
        if correct:
            new_coef = min(1.5, current + 0.05)
        else:
            new_coef = max(0.3, current - 0.15)
        self._quality_coefficients[worker_id] = round(new_coef, 2)
        return new_coef

    def get_quality_coefficient(self, worker_id: str) -> float:
        """获取worker当前的质检系数"""
        return self._quality_coefficients.get(worker_id, 1.0)

    def set_quality_coefficient(self, worker_id: str, coefficient: float):
        """手动设置质检系数"""
        self._quality_coefficients[worker_id] = max(0.1, min(2.0, coefficient))

    # ── F5.3: 多数表决机制 ──

    def cast_vote(self, task_id: str, worker_id: str,
                  field_name: str, answer: str):
        """记录一个worker对某个任务字段的投票"""
        if task_id not in self._votes:
            self._votes[task_id] = {}
        if field_name not in self._votes[task_id]:
            self._votes[task_id][field_name] = []
        self._votes[task_id][field_name].append(answer)

    def majority_vote(self, task_id: str, field_name: str = None,
                      min_voters: int = 2) -> dict:
        """执行多数表决

        Args:
            task_id: 任务ID
            field_name: 字段名 (None表示返回所有字段)
            min_voters: 最少投票人数 (低于此数不产生结果)

        Returns:
            {consensus: str/None, confidence: float, votes: dict, disputed: bool}
        """
        task_votes = self._votes.get(task_id, {})
        if not task_votes:
            return {"consensus": None, "confidence": 0.0, "votes": {}, "disputed": True, "reason": "no votes"}

        fields_to_check = [field_name] if field_name else list(task_votes.keys())

        results = {}
        for field in fields_to_check:
            answers = task_votes.get(field, [])
            if len(answers) < min_voters:
                results[field] = {
                    "consensus": None,
                    "confidence": 0.0,
                    "vote_count": len(answers),
                    "disputed": True,
                    "reason": f"insufficient votes ({len(answers)} < {min_voters})",
                }
                continue

            # 计票
            from collections import Counter
            tally = Counter(answers)
            total_votes = sum(tally.values())
            top_answer, top_count = tally.most_common(1)[0]
            confidence = top_count / total_votes

            # 如果有并列最高票，标记为争议
            disputed = False
            if len(tally) > 1:
                second_count = tally.most_common(2)[1][1]
                if second_count == top_count:
                    disputed = True

            results[field] = {
                "consensus": top_answer,
                "confidence": round(confidence, 3),
                "vote_count": total_votes,
                "distribution": dict(tally),
                "disputed": disputed,
            }

        if field_name:
            return results[field_name]
        return results

    def get_all_majority_results(self, task_id: str) -> dict:
        """获取任务所有字段的多数表决结果"""
        return self.majority_vote(task_id)

    # ── F5.3: 综合质检评分 ──

    def get_advanced_quality_report(self, worker_id: str) -> dict:
        """获取worker的高级质检报告 (包含金标准+质检系数)"""
        w = self.workers.get(worker_id)
        if not w:
            return {}

        # 统计金标准正确率
        golden_correct = 0
        golden_total = 0
        for responses in self._golden_responses.values():
            for r in responses:
                if r["worker_id"] == worker_id:
                    golden_total += 1
                    if r["correct"]:
                        golden_correct += 1

        golden_accuracy = round(golden_correct / max(golden_total, 1), 3)
        coefficient = self._quality_coefficients.get(worker_id, 1.0)
        effective_quality = round(w.quality_score * coefficient, 2)

        return {
            "worker_id": worker_id,
            "name": w.name,
            "base_quality_score": w.quality_score,
            "quality_coefficient": coefficient,
            "effective_quality_score": effective_quality,
            "golden_accuracy": golden_accuracy,
            "golden_items_completed": golden_total,
            "golden_items_correct": golden_correct,
            "completed_tasks": w._completed_tasks,
            "earnings": w.earnings,
        }

    # ── statistics ──

    def get_worker_stats(self, worker_id: str) -> dict:
        w = self.workers.get(worker_id)
        if not w:
            return {}
        return {
            "id": w.id,
            "name": w.name,
            "skills": w.skills,
            "workload": w.workload,
            "quality_score": w.quality_score,
            "status": w.status,
            "earnings": w.earnings,
            "completed_tasks": w._completed_tasks,
        }

    def get_team_stats(self, team_id: str) -> dict:
        t = self.teams.get(team_id)
        if not t:
            return {}
        scores = [m.quality_score for m in t.members if m.quality_score > 0]
        workloads = [m.workload for m in t.members]
        earnings = [m.earnings for m in t.members]
        return {
            "team_id": t.id,
            "team_name": t.name,
            "member_count": len(t.members),
            "active_projects": t.active_projects,
            "avg_quality": round(statistics.mean(scores), 2) if scores else 0.0,
            "total_workload": sum(workloads),
            "avg_workload": round(statistics.mean(workloads), 2) if workloads else 0,
            "total_earnings": round(sum(earnings), 2),
        }
