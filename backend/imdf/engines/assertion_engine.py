"""
P0-6: Quality Assertion Framework
==================================
Lightweight Great Expectations-style data quality assertions.
Supports ColumnExpectation, TableExpectation, and RowExpectation.
"""

from typing import List, Dict, Any, Optional, Callable, Union
import sqlite3
import operator


class Expectation:
    """Base expectation class"""
    def __init__(self, name: str):
        self.name = name

    def validate(self, data: Any) -> bool:
        raise NotImplementedError


class ColumnExpectation(Expectation):
    """列级断言: 对指定列执行操作符检查

    Examples:
        ColumnExpectation("not_null", "label", "is_not_null")
        ColumnExpectation("min_value", "age", ">=", 0)
        ColumnExpectation("unique", "id", "is_unique")
    """

    SUPPORTED_OPS = {
        "is_not_null": lambda col: col is not None,
        "is_null": lambda col: col is None,
        "is_unique": lambda col: True,  # handled at column level
        ">": operator.gt,
        ">=": operator.ge,
        "<": operator.lt,
        "<=": operator.le,
        "==": operator.eq,
        "!=": operator.ne,
        "in": lambda col, vals: col in vals,
        "not_in": lambda col, vals: col not in vals,
    }

    def __init__(self, name: str, column: str, operator: str, value: Any = None):
        super().__init__(name)
        self.column = column
        self.operator = operator
        self.value = value

    def validate(self, data: Union[List[Dict], List[List]]) -> Dict[str, Any]:
        """验证列级断言

        Args:
            data: 可迭代的行数据

        Returns:
            {"passed": int, "failed": int, "total": int, "detail": str}
        """
        total = len(data)
        passed = 0
        failed_rows = []

        if self.operator == "is_unique":
            # Check uniqueness across all rows
            seen = set()
            for row in data:
                val = row.get(self.column) if isinstance(row, dict) else row
                if val in seen:
                    failed_rows.append(("duplicate", val))
                seen.add(val)
            passed = total - len(failed_rows)
            failed = len(failed_rows)
            return {
                "passed": passed,
                "failed": failed,
                "total": total,
                "detail": f"unique check on '{self.column}': {failed} duplicates"
            }

        op_fn = self.SUPPORTED_OPS.get(self.operator)
        if op_fn is None:
            return {"passed": 0, "failed": total, "total": total, "detail": f"Unknown operator: {self.operator}"}

        for row in data:
            col_val = row.get(self.column) if isinstance(row, dict) else row
            try:
                if self.value is not None:
                    if op_fn(col_val, self.value):
                        passed += 1
                    else:
                        failed_rows.append(col_val)
                else:
                    if op_fn(col_val):
                        passed += 1
                    else:
                        failed_rows.append(col_val)
            except Exception:
                failed_rows.append(col_val)

        failed = total - passed
        sample = failed_rows[:5]
        return {
            "passed": passed,
            "failed": failed,
            "total": total,
            "detail": f"column='{self.column}', op={self.operator}, val={self.value}: "
                      f"passed={passed}/{total}, samples={sample}"
        }


class TableExpectation(Expectation):
    """表级断言: 对整张表进行统计检查

    Examples:
        TableExpectation("min_rows", ">=", 100)
        TableExpectation("max_columns", "<=", 50)
    """

    def __init__(self, name: str, operator: str, value: Any):
        super().__init__(name)
        self.operator = operator
        self.value = value

    def validate(self, data: List) -> Dict[str, Any]:
        """验证表级断言

        Args:
            data: 表数据 (list of rows or dicts)

        Returns:
            {"passed": int, "failed": int, "total": int, "detail": str}
        """
        total_rows = len(data)
        op_map = {
            ">=": operator.ge,
            ">": operator.gt,
            "<=": operator.le,
            "<": operator.lt,
            "==": operator.eq,
            "!=": operator.ne,
        }
        op_fn = op_map.get(self.operator)
        if op_fn is None:
            return {"passed": 0, "failed": 1, "total": 1, "detail": f"Unknown operator: {self.operator}"}

        if self.name == "min_rows":
            result = op_fn(total_rows, self.value)
            return {
                "passed": 1 if result else 0,
                "failed": 0 if result else 1,
                "total": 1,
                "detail": f"min_rows: rows={total_rows} {self.operator} {self.value} => {result}"
            }
        elif self.name == "max_rows":
            result = op_fn(total_rows, self.value)
            return {
                "passed": 1 if result else 0,
                "failed": 0 if result else 1,
                "total": 1,
                "detail": f"max_rows: rows={total_rows} {self.operator} {self.value} => {result}"
            }
        else:
            return {"passed": 0, "failed": 1, "total": 1, "detail": f"Unknown table expectation: {self.name}"}


class RowExpectation(Expectation):
    """行级断言: 对每行执行条件检查

    Examples:
        RowExpectation("valid_label", "label IN ('cat','dog')")
        RowExpectation("positive_age", "age > 0")
    """

    def __init__(self, name: str, condition: str):
        super().__init__(name)
        self.condition = condition
        # Parse condition into column, operator, value
        self._parsed = self._parse_condition(condition)

    def _parse_condition(self, cond: str) -> Optional[Dict]:
        """Simple condition parser: 'col OP value' or 'col IN (vals)'"""
        cond = cond.strip()
        if " IN " in cond:
            parts = cond.split(" IN ")
            col = parts[0].strip()
            return {"type": "in", "column": col, "values": parts[1].strip()}
        op_candidates = [">=", "<=", "!=", ">", "<", "==", "="]
        for op in sorted(op_candidates, key=len, reverse=True):
            if op in cond:
                parts = cond.split(op, 1)
                col = parts[0].strip()
                val_str = parts[1].strip()
                try:
                    val = int(val_str)
                except ValueError:
                    try:
                        val = float(val_str)
                    except ValueError:
                        val = val_str.strip("'\"")
                return {"type": "op", "column": col, "operator": op, "value": val}
        return None

    def validate(self, data: Union[List[Dict], List[List]]) -> Dict[str, Any]:
        """验证行级断言

        Args:
            data: 可迭代的行数据

        Returns:
            {"passed": int, "failed": int, "total": int, "detail": str}
        """
        total = len(data)
        if self._parsed is None:
            return {"passed": 0, "failed": total, "total": total, "detail": f"Cannot parse condition: {self.condition}"}

        passed = 0
        failed_rows = []

        op_map = {
            ">=": operator.ge,
            ">": operator.gt,
            "<=": operator.le,
            "<": operator.lt,
            "==": operator.eq,
            "=": operator.eq,
            "!=": operator.ne,
        }

        for row in data:
            col_val = row.get(self._parsed["column"]) if isinstance(row, dict) else row
            try:
                if self._parsed["type"] == "in":
                    # Parse values: ('cat','dog') -> ['cat', 'dog']
                    vals_str = self._parsed["values"].strip("()")
                    allowed = [v.strip().strip("'\"") for v in vals_str.split(",")]
                    if col_val in allowed:
                        passed += 1
                    else:
                        failed_rows.append(col_val)
                else:
                    op_fn = op_map.get(self._parsed["operator"])
                    if op_fn and op_fn(col_val, self._parsed["value"]):
                        passed += 1
                    else:
                        failed_rows.append(col_val)
            except Exception:
                failed_rows.append(col_val)

        failed = total - passed
        return {
            "passed": passed,
            "failed": failed,
            "total": total,
            "detail": f"condition='{self.condition}': passed={passed}/{total}, samples={failed_rows[:5]}"
        }


class ExpectationSuite:
    """断言套件: 包含多个Expectation"""

    def __init__(self, name: str, expectations: List[Expectation] = None):
        self.name = name
        self.expectations = expectations or []

    def add(self, expectation: Expectation) -> None:
        self.expectations.append(expectation)

    def remove(self, name: str) -> None:
        self.expectations = [e for e in self.expectations if e.name != name]


class Validator:
    """验证器: 对数据执行断言套件"""

    @staticmethod
    def validate(suite: ExpectationSuite, data: Any) -> Dict[str, Any]:
        """执行验证

        Args:
            suite: ExpectationSuite
            data: 待验证数据

        Returns:
            {"passed": N, "failed": N, "total": N, "results": [...]}
        """
        results = []
        total_passed = 0
        total_failed = 0

        for exp in suite.expectations:
            try:
                result = exp.validate(data)
                results.append({
                    "name": exp.name,
                    "type": type(exp).__name__,
                    "passed": result["passed"],
                    "failed": result["failed"],
                    "total": result["total"],
                    "detail": result["detail"],
                })
                total_passed += result["passed"]
                total_failed += result["failed"]
            except Exception as e:
                results.append({
                    "name": exp.name,
                    "type": type(exp).__name__,
                    "passed": 0,
                    "failed": 1,
                    "total": 1,
                    "detail": f"Error: {str(e)}",
                })
                total_failed += 1

        return {
            "passed": total_passed,
            "failed": total_failed,
            "total": total_passed + total_failed,
            "results": results,
        }
