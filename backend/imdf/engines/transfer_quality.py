"""
商用级传输质量控制引擎 v1.0
===========================
- 传输完整性验证 (SHA256/MD5)
- 断点续传 + 校验
- 传输速度监控
- 签名URL安全审计
- 行业对标 (Data Transfer Standards)
"""
import os
import hashlib
import hmac
import time
import json
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================
# 1. Integrity Verification Engine (传输完整性验证)
# ============================================================

class IntegrityVerifier:
    """传输完整性验证引擎"""

    @staticmethod
    def compute_sha256(file_path: str, chunk_size: int = 8192) -> str:
        """计算文件SHA256哈希"""
        sha = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(chunk_size):
                    sha.update(chunk)
            return sha.hexdigest()
        except Exception as e:
            logger.error(f"SHA256 computation failed for {file_path}: {e}")
            return ""

    @staticmethod
    def compute_md5(file_path: str, chunk_size: int = 8192) -> str:
        """计算文件MD5哈希"""
        md5 = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(chunk_size):
                    md5.update(chunk)
            return md5.hexdigest()
        except Exception as e:
            logger.error(f"MD5 computation failed for {file_path}: {e}")
            return ""

    @staticmethod
    def compute_multi_hash(file_path: str) -> Dict[str, str]:
        """同时计算多种哈希"""
        hashers = {
            "sha256": hashlib.sha256(),
            "md5": hashlib.md5(),
            "sha1": hashlib.sha1(),
        }
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    for h in hashers.values():
                        h.update(chunk)
            return {name: h.hexdigest() for name, h in hashers.items()}
        except Exception as e:
            logger.error(f"Multi-hash failed: {e}")
            return {name: "" for name in hashers}

    @staticmethod
    def verify_file(source_path: str, dest_path: str,
                     hash_type: str = "sha256") -> Dict:
        """验证两个文件是否一致"""
        source_hash = ""
        dest_hash = ""

        if hash_type == "sha256":
            source_hash = IntegrityVerifier.compute_sha256(source_path)
            dest_hash = IntegrityVerifier.compute_sha256(dest_path)
        elif hash_type == "md5":
            source_hash = IntegrityVerifier.compute_md5(source_path)
            dest_hash = IntegrityVerifier.compute_md5(dest_path)

        source_size = os.path.getsize(source_path) if os.path.exists(source_path) else 0
        dest_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0

        hash_match = hmac.compare_digest(source_hash, dest_hash)
        size_match = source_size == dest_size

        integrity_errors = []
        if not hash_match:
            integrity_errors.append("hash_mismatch")
        if not size_match:
            integrity_errors.append("size_mismatch")

        return {
            "source_path": source_path,
            "dest_path": dest_path,
            "source_hash": source_hash,
            "dest_hash": dest_hash,
            "hash_type": hash_type,
            "hash_match": hash_match,
            "source_size": source_size,
            "dest_size": dest_size,
            "size_match": size_match,
            "integrity_verified": hash_match and size_match,
            "integrity_errors": integrity_errors,
            "verdict": "PASS" if hash_match and size_match else "FAIL",
        }

    @staticmethod
    def batch_verify(file_pairs: List[Tuple[str, str]],
                     hash_type: str = "sha256") -> Dict:
        """批量验证文件传输完整性"""
        results = []
        passed = 0
        failed = 0
        total_size = 0

        for source, dest in file_pairs:
            result = IntegrityVerifier.verify_file(source, dest, hash_type)
            results.append(result)
            if result["integrity_verified"]:
                passed += 1
                total_size += result["source_size"]
            else:
                failed += 1

        return {
            "total_files": len(file_pairs),
            "passed": passed,
            "failed": failed,
            "integrity_rate": round(passed / max(len(file_pairs), 1), 4),
            "total_size_bytes": total_size,
            "total_size_human": IntegrityVerifier._format_size(total_size),
            "details": results,
            "status": "PASS" if failed == 0 else "PARTIAL" if passed > 0 else "FAIL",
        }

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / 1024 / 1024:.1f} MB"
        else:
            return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"


# ============================================================
# 2. Resume Transfer Engine (断点续传)
# ============================================================

@dataclass
class TransferCheckpoint:
    """传输检查点"""
    file_path: str
    dest_path: str
    total_size: int
    transferred_size: int = 0
    chunk_size: int = 1024 * 1024  # 1MB
    checksum: str = ""
    last_chunk_hash: str = ""
    started_at: str = ""
    last_updated: str = ""

    def progress_pct(self) -> float:
        return self.transferred_size / max(self.total_size, 1) * 100

    def is_complete(self) -> bool:
        return self.transferred_size >= self.total_size

    def remaining_chunks(self) -> int:
        remaining = self.total_size - self.transferred_size
        return (remaining + self.chunk_size - 1) // self.chunk_size


class ResumeTransferEngine:
    """断点续传引擎"""

    def __init__(self, checkpoint_dir: str = "data/transfer_checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.active_transfers: Dict[str, TransferCheckpoint] = {}

    def init_transfer(self, file_path: str, dest_path: str,
                      chunk_size: int = 1024 * 1024) -> TransferCheckpoint:
        """初始化传输检查点"""
        total_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        ck = TransferCheckpoint(
            file_path=file_path,
            dest_path=dest_path,
            total_size=total_size,
            chunk_size=chunk_size,
            started_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
        )
        self.active_transfers[file_path] = ck
        self._save_checkpoint(ck)
        return ck

    def update_checkpoint(self, checkpoint: TransferCheckpoint,
                          chunk_data: bytes, chunk_hash: str):
        """更新检查点"""
        checkpoint.transferred_size += len(chunk_data)
        checkpoint.last_chunk_hash = chunk_hash
        checkpoint.last_updated = datetime.now().isoformat()
        self._save_checkpoint(checkpoint)

    def resume_checkpoint(self, file_path: str) -> Optional[TransferCheckpoint]:
        """恢复检查点"""
        ck_path = self._checkpoint_path(file_path)
        if ck_path.exists():
            try:
                data = json.loads(ck_path.read_text())
                ck = TransferCheckpoint(**data)
                # Verify partial file size matches
                if os.path.exists(ck.dest_path):
                    actual_size = os.path.getsize(ck.dest_path)
                    if actual_size != ck.transferred_size:
                        logger.warning(
                            f"Checkpoint size mismatch for {file_path}: "
                            f"expected {ck.transferred_size}, actual {actual_size}"
                        )
                        ck.transferred_size = actual_size
                else:
                    ck.transferred_size = 0
                self.active_transfers[file_path] = ck
                return ck
            except Exception as e:
                logger.error(f"Failed to load checkpoint: {e}")
        return None

    def verify_chunk(self, chunk_data: bytes, expected_hash: str) -> bool:
        """验证数据块完整性"""
        actual_hash = hashlib.sha256(chunk_data).hexdigest()
        return hmac.compare_digest(actual_hash, expected_hash)

    def _checkpoint_path(self, file_path: str) -> Path:
        """获取检查点文件路径"""
        safe_name = hashlib.md5(file_path.encode()).hexdigest()[:16]
        return self.checkpoint_dir / f"{safe_name}.json"

    def _save_checkpoint(self, ck: TransferCheckpoint):
        """保存检查点到磁盘"""
        ck_path = self._checkpoint_path(ck.file_path)
        ck_path.write_text(json.dumps({
            "file_path": ck.file_path,
            "dest_path": ck.dest_path,
            "total_size": ck.total_size,
            "transferred_size": ck.transferred_size,
            "chunk_size": ck.chunk_size,
            "checksum": ck.checksum,
            "last_chunk_hash": ck.last_chunk_hash,
            "started_at": ck.started_at,
            "last_updated": ck.last_updated,
        }, indent=2))

    def list_checkpoints(self) -> List[Dict]:
        """列出所有检查点"""
        checkpoints = []
        for ck_file in self.checkpoint_dir.glob("*.json"):
            try:
                data = json.loads(ck_file.read_text())
                data["progress_pct"] = (
                    data["transferred_size"] / max(data["total_size"], 1) * 100
                )
                checkpoints.append(data)
            except Exception as e:
                logger.error(f"Operation failed: {e}")
        return checkpoints

    def clear_checkpoint(self, file_path: str):
        """清除检查点"""
        ck_path = self._checkpoint_path(file_path)
        if ck_path.exists():
            ck_path.unlink()
        self.active_transfers.pop(file_path, None)


# ============================================================
# 3. Transfer Speed Monitor (传输速度监控)
# ============================================================

@dataclass
class SpeedRecord:
    """单次传输速度记录"""
    source: str
    dest: str
    file_size: int
    duration_ms: float
    speed_mbps: float
    timestamp: float = field(default_factory=time.time)
    protocol: str = "http"


class TransferSpeedMonitor:
    """传输速度监控引擎"""

    def __init__(self, window_size: int = 500):
        self.window_size = window_size
        self.records: List[SpeedRecord] = []
        self._recent_speeds: List[float] = []

    def record(self, record: SpeedRecord):
        """记录一次传输"""
        self.records.append(record)
        self._recent_speeds.append(record.speed_mbps)
        if len(self._recent_speeds) > self.window_size:
            self._recent_speeds.pop(0)

    def get_stats(self) -> Dict:
        """获取传输速度统计"""
        import numpy as np

        if not self._recent_speeds:
            return {"error": "无传输记录", "status": "no_data"}

        arr = np.array(self._recent_speeds)
        speeds = float(np.mean(arr))

        # 按协议分组
        by_protocol = {}
        for record in self.records[-self.window_size:]:
            p = record.protocol
            if p not in by_protocol:
                by_protocol[p] = []
            by_protocol[p].append(record.speed_mbps)

        protocol_stats = {}
        for p, spds in by_protocol.items():
            sarr = np.array(spds)
            protocol_stats[p] = {
                "count": len(spds),
                "avg_mbps": round(float(np.mean(sarr)), 2),
                "p50_mbps": round(float(np.percentile(sarr, 50)), 2),
                "p95_mbps": round(float(np.percentile(sarr, 95)), 2),
                "max_mbps": round(float(np.max(sarr)), 2),
                "total_gb": round(sum(
                    r.file_size for r in self.records[-self.window_size:]
                    if r.protocol == p
                ) / (1024**3), 3),
            }

        # 速度评级
        if speeds >= 100:
            tier = "excellent"
        elif speeds >= 50:
            tier = "good"
        elif speeds >= 10:
            tier = "acceptable"
        elif speeds >= 1:
            tier = "slow"
        else:
            tier = "very_slow"

        return {
            "total_records": len(self.records),
            "window_size": self.window_size,
            "avg_speed_mbps": round(float(np.mean(arr)), 2),
            "p50_mbps": round(float(np.percentile(arr, 50)), 2),
            "p95_mbps": round(float(np.percentile(arr, 95)), 2),
            "p99_mbps": round(float(np.percentile(arr, 99)), 2),
            "min_mbps": round(float(np.min(arr)), 2),
            "max_mbps": round(float(np.max(arr)), 2),
            "speed_tier": tier,
            "by_protocol": protocol_stats,
            "total_data_transferred_gb": round(
                sum(r.file_size for r in self.records[-self.window_size:]) / (1024**3), 3
            ),
        }

    def estimate_transfer_time(self, file_size_bytes: int, protocol: str = "http") -> Dict:
        """预估传输时间"""
        import numpy as np

        # 按协议计算平均速度
        speeds = [
            r.speed_mbps for r in self.records[-self.window_size:]
            if r.protocol == protocol
        ]
        if not speeds:
            speeds = self._recent_speeds or [10.0]  # default 10 Mbps

        avg_speed_mbps = float(np.mean(speeds))
        p50_speed_mbps = float(np.percentile(speeds, 50)) if len(speeds) > 1 else avg_speed_mbps

        size_mb = file_size_bytes / (1024 * 1024)
        est_seconds_avg = size_mb / avg_speed_mbps if avg_speed_mbps > 0 else float('inf')
        est_seconds_p50 = size_mb / p50_speed_mbps if p50_speed_mbps > 0 else float('inf')

        return {
            "file_size_bytes": file_size_bytes,
            "file_size_mb": round(size_mb, 2),
            "avg_speed_mbps": round(avg_speed_mbps, 2),
            "p50_speed_mbps": round(p50_speed_mbps, 2),
            "estimated_time_avg_seconds": round(est_seconds_avg, 1),
            "estimated_time_p50_seconds": round(est_seconds_p50, 1),
            "estimated_time_avg_human": TransferSpeedMonitor._format_duration(est_seconds_avg),
            "estimated_time_p50_human": TransferSpeedMonitor._format_duration(est_seconds_p50),
        }

    @staticmethod
    def _format_duration(seconds: float) -> str:
        if seconds == float('inf'):
            return "无法预估"
        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}min"
        else:
            return f"{seconds/3600:.1f}h"

    def reset(self):
        """重置监控"""
        self.records.clear()
        self._recent_speeds.clear()


# ============================================================
# 4. Signed URL Security Audit (签名URL安全审计)
# ============================================================

class SignedURLAuditor:
    """签名URL安全审计引擎"""

    # URL安全模式
    SECURITY_PATTERNS = {
        "exposed_token": r"token=([a-zA-Z0-9_\-]+)",
        "exposed_key": r"(api[_-]?key|apikey|secret)=([a-zA-Z0-9_\-]+)",
        "expired_sig": r"expires?=\d{10}",  # Unix timestamp
        "missing_signature": None,
        "weak_signature": r"sig=[a-f0-9]{1,7}$",  # 短签名
        "http_not_https": r"^http://",
        "path_traversal": r"\.\./|%2e%2e%2f",
        "injection_attempt": r"[<>'\"(){};]",
    }

    @staticmethod
    def audit_url(url: str, expected_expiry: Optional[int] = None) -> Dict:
        """审计单个签名URL的安全性"""
        findings = []
        severity = "low"

        # 检查HTTPS
        if url.startswith("http://"):
            findings.append({
                "type": "http_not_https",
                "severity": "high",
                "detail": "签名URL未使用HTTPS,存在中间人攻击风险",
                "remediation": "使用HTTPS协议传输所有签名URL",
            })
            severity = "high"

        # 检查令牌泄露
        token_match = re.search(SignedURLAuditor.SECURITY_PATTERNS["exposed_token"], url)
        if token_match:
            # Token在URL中是可预期的,但检查是否过于暴露
            if len(token_match.group(1)) < 8:
                findings.append({
                    "type": "short_token",
                    "severity": "medium",
                    "detail": f"Token过短 ({len(token_match.group(1))} chars),易被暴力破解",
                    "remediation": "使用至少16字符的随机token",
                })

        # 检查API Key泄露
        key_match = re.search(SignedURLAuditor.SECURITY_PATTERNS["exposed_key"], url, re.IGNORECASE)
        if key_match:
            findings.append({
                "type": "exposed_key",
                "severity": "critical",
                "detail": "URL中包含可能的API Key/Secret",
                "remediation": "立即吊销该key,API key绝不应出现在URL中",
            })
            severity = "critical"

        # 检查签名强度
        sig_match = re.search(r"sig(?:nature)?=([a-fA-F0-9]+)", url)
        if sig_match:
            sig = sig_match.group(1)
            if len(sig) < 16:
                findings.append({
                    "type": "weak_signature",
                    "severity": "medium",
                    "detail": f"签名长度不足 ({len(sig)} hex chars),建议>=32",
                    "remediation": "使用HMAC-SHA256全长度(64 hex chars)签名",
                })
        else:
            findings.append({
                "type": "missing_signature",
                "severity": "high",
                "detail": "URL缺少签名参数,无法防篡改",
                "remediation": "对所有分享URL添加HMAC签名",
            })

        # 检查过期时间
        exp_match = re.search(r"exp(?:ires?)?=(\d+)", url)
        if exp_match:
            exp_ts = int(exp_match.group(1))
            now = int(time.time())
            if exp_ts < now:
                findings.append({
                    "type": "expired_url",
                    "severity": "info",
                    "detail": "URL已过期",
                    "remediation": "生成新的签名URL",
                })
            elif exp_ts - now > 365 * 86400:
                findings.append({
                    "type": "excessive_validity",
                    "severity": "medium",
                    "detail": f"URL有效期过长 ({(exp_ts-now)/86400:.0f}天)",
                    "remediation": "建议有效期不超过30天",
                })
        elif url not in ["", None]:
            findings.append({
                "type": "no_expiry",
                "severity": "medium",
                "detail": "URL缺少过期时间参数",
                "remediation": "添加过期时间限制",
            })

        # 路径遍历
        if re.search(SignedURLAuditor.SECURITY_PATTERNS["path_traversal"], url):
            findings.append({
                "type": "path_traversal",
                "severity": "critical",
                "detail": "检测到路径遍历尝试",
                "remediation": "验证并清理资源路径",
            })
            severity = "critical"

        return {
            "url": url,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "findings_count": len(findings),
            "severity": severity,
            "findings": findings,
            "secure": severity != "critical" and len([f for f in findings if f["severity"] in ("high", "critical")]) == 0,
            "recommendation": (
                "URL安全合规" if not findings else
                f"发现{len(findings)}个安全问题,最高严重度: {severity}"
            ),
        }

    @staticmethod
    def batch_audit(urls: List[str], expected_expiry: Optional[int] = None) -> Dict:
        """批量审计URL"""
        results = [SignedURLAuditor.audit_url(url, expected_expiry) for url in urls]
        secure_count = sum(1 for r in results if r["secure"])
        critical_count = sum(1 for r in results if r["severity"] == "critical")

        return {
            "total_urls": len(urls),
            "secure_count": secure_count,
            "insecure_count": len(urls) - secure_count,
            "critical_count": critical_count,
            "security_score": round(secure_count / max(len(urls), 1) * 100, 1),
            "results": results,
            "status": "PASS" if critical_count == 0 and secure_count == len(urls) else
                      "WARNING" if critical_count == 0 else "FAIL",
        }


# ============================================================
# 5. Transfer Quality Reporter
# ============================================================

class TransferQualityReporter:
    """传输质量综合报告"""

    @staticmethod
    def generate_report(
        integrity_results: Optional[Dict] = None,
        speed_stats: Optional[Dict] = None,
        url_audit_results: Optional[Dict] = None,
        resume_stats: Optional[Dict] = None,
    ) -> Dict:
        """生成综合传输质量报告"""
        report = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        # 完整性
        if integrity_results:
            report["integrity"] = integrity_results

        # 速度
        if speed_stats:
            report["speed"] = speed_stats

        # URL安全
        if url_audit_results:
            report["url_security"] = url_audit_results

        # 断点续传
        if resume_stats:
            report["resume_transfer"] = resume_stats

        # 综合评分
        integrity_score = 0
        if integrity_results:
            integrity_score = integrity_results.get("integrity_rate", 0) * 100

        speed_score = 0
        if speed_stats:
            tier = speed_stats.get("speed_tier", "slow")
            speed_score = {
                "excellent": 100, "good": 80, "acceptable": 60, "slow": 35, "very_slow": 15
            }.get(tier, 30)

        security_score = 0
        if url_audit_results:
            security_score = url_audit_results.get("security_score", 0)

        scores = []
        if integrity_results:
            scores.append((integrity_score, 0.4))
        if speed_stats:
            scores.append((speed_score, 0.25))
        if url_audit_results:
            scores.append((security_score, 0.35))

        overall = sum(s * w for s, w in scores) if scores else 0

        report["overall_quality_score"] = round(overall, 1)
        report["quality_tier"] = (
            "S-Tier (企业级)" if overall >= 90 else
            "A-Tier (生产级)" if overall >= 75 else
            "B-Tier (可用)" if overall >= 55 else
            "C-Tier (需改进)" if overall >= 35 else
            "D-Tier (不合规)"
        )

        return report


# ============================================================
# Industry Benchmarks
# ============================================================

INDUSTRY_TRANSFER = {
    "cdn_delivery": {
        "name": "CDN分发",
        "standards": ["HTTP/2", "TLS 1.3", "OCSP Stapling"],
        "quality_targets": "可用性 >= 99.95%, P99延迟 < 100ms, 完整性 >= 99.999%",
    },
    "enterprise_transfer": {
        "name": "企业传输",
        "standards": ["SFTP", "HTTPS with mTLS"],
        "quality_targets": "加密: AES-256, 签名: HMAC-SHA256, 审计: 全链路",
    },
    "cloud_storage": {
        "name": "云存储传输",
        "standards": ["AWS S3", "GCS", "Azure Blob"],
        "quality_targets": "断点续传, 多部分上传, 服务端加密, 版本控制",
    },
    "secure_sharing": {
        "name": "安全分享",
        "standards": ["Signed URL", "Pre-signed URL", "Temporary Credentials"],
        "quality_targets": "URL有效期 <= 7天, 签名算法: HMAC-SHA256, 下载限制: 强制实施",
    },
}

# 单例
_integrity_verifier: IntegrityVerifier = None
_resume_engine: ResumeTransferEngine = None
_speed_monitor: TransferSpeedMonitor = None
_url_auditor: SignedURLAuditor = None
_transfer_reporter: TransferQualityReporter = None

def get_integrity_verifier():
    global _integrity_verifier
    _integrity_verifier = _integrity_verifier or IntegrityVerifier()
    return _integrity_verifier

def get_resume_engine():
    global _resume_engine
    _resume_engine = _resume_engine or ResumeTransferEngine()
    return _resume_engine

def get_speed_monitor():
    global _speed_monitor
    _speed_monitor = _speed_monitor or TransferSpeedMonitor()
    return _speed_monitor

def get_url_auditor():
    global _url_auditor
    _url_auditor = _url_auditor or SignedURLAuditor()
    return _url_auditor

def get_transfer_reporter():
    global _transfer_reporter
    _transfer_reporter = _transfer_reporter or TransferQualityReporter()
    return _transfer_reporter
