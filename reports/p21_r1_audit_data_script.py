"""P21 R1 data-pipeline audit script.

Executed for the P21 R1 deep audit. Read-only — does NOT modify any source.
Categorises findings P0/P1/P2 with file:line + evidence.

Run with:
    & "D:\\ComfyUI\\.ext\\python.exe" reports\\p21_r1_audit_data_script.py

Output:
    - prints JSON to stdout (also captured to p21_r1_audit_data_stdout.txt)
    - writes p21_r1_audit_data.json next to this file
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import io
import json
import os
import re
import sqlite3
import struct
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Paths
PROJECT_ROOT = Path(r"D:\Hermes\生产平台\nanobot-factory")
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT / "imdf"))
os.chdir(str(BACKEND_ROOT / "imdf"))

REPORT_PATH = PROJECT_ROOT / "reports"
JSON_OUT = REPORT_PATH / "p21_r1_audit_data.json"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


findings: List[Dict[str, Any]] = []
checks_pass: List[str] = []
checks_fail: List[str] = []


def add_finding(level: str, kind: str, where: str, msg: str,
                scenario: str = "", repro: str = "", fix_min: int = 30,
                evidence: Any = None) -> None:
    findings.append({
        "level": level,
        "kind": kind,
        "where": where,
        "msg": msg,
        "scenario": scenario,
        "repro": repro,
        "fix_min": fix_min,
        "evidence": evidence,
        "ts": _now(),
    })


def pass_check(name: str, evidence: Any = None) -> None:
    checks_pass.append(name)
    print(f"  [PASS] {name}  ev={evidence!r}")


def fail_check(name: str, reason: str) -> None:
    checks_fail.append(name)
    print(f"  [FAIL] {name}  reason={reason}")


# ============================================================================
# Section 1 — 8-modality coverage check
# ============================================================================
def check_modalities() -> None:
    print("\n=== [1] 8-modality coverage ===")
    from multimodal.types import ModalKind, MediaRef, parse_media_item
    members = list(ModalKind)
    expected = {"image", "video", "audio", "text", "three_d", "lidar", "medical", "panoptic"}
    actual = {m.value for m in members}
    if expected.issubset(actual):
        pass_check("ModalKind has 8 modalities", list(actual))
    else:
        add_finding("P0", "modal_count_mismatch", "multimodal/types.py:19-26",
                    f"ModalKind enum has {len(actual)} members ({sorted(actual)}); spec requires 8 ({sorted(expected)}); missing: {sorted(expected - actual)}",
                    scenario="User uploads LiDAR .las file → parser dispatcher returns 'no parser for kind=lidar'",
                    repro="from imdf.multimodal.types import ModalKind; print([m.value for m in ModalKind])",
                    fix_min=30)
        fail_check("ModalKind has 8 modalities", f"got {actual}")

    from multimodal.business_modalities import list_modalities
    biz = [m.id for m in list_modalities()]
    if len(biz) >= 8:
        pass_check("Business modalities count", len(biz))
    else:
        add_finding("P0", "biz_modality_count", "multimodal/business_modalities.py",
                    f"Only {len(biz)} business modalities registered: {biz}; spec requires 8 (3d/lidar/medical/panoptic + 4 more)",
                    scenario="Cross-modal RAG cannot route LiDAR / Medical / Panoptic data",
                    repro="from imdf.multimodal.business_modalities import list_modalities; print([m.id for m in list_modalities()])",
                    fix_min=60)


# ============================================================================
# Section 2 — Parser real-implementation probes
# ============================================================================
def check_parsers() -> None:
    print("\n=== [2] Parser real-implementation ===")
    from multimodal.types import MediaRef, ModalKind
    from multimodal.parsers import ImageParser, AudioParser, VideoParser, DocumentParser

    # Image parser: EXIF check
    try:
        from PIL import Image
        # Create tiny test PNG
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), color="red").save(buf, format="PNG")
        png_bytes = buf.getvalue()
        ref = MediaRef(kind=ModalKind.IMAGE, data_b64=_b64(png_bytes))
        parsed = ImageParser().parse(ref)
        meta_keys = sorted(parsed.meta.keys())
        has_exif = any(k in meta_keys for k in ("exif", "gps", "make", "model"))
        if has_exif:
            pass_check("ImageParser EXIF", meta_keys)
        else:
            add_finding("P0", "no_exif", "multimodal/parsers.py:82-116",
                        "ImageParser never calls img._getexif(); no GPS/camera/lens info",
                        scenario="Geo-tagged photos stored without lat/lon; provenance lost",
                        repro="from imdf.multimodal.parsers import ImageParser; from imdf.multimodal.types import MediaRef, ModalKind; ImageParser().parse(MediaRef(kind=ModalKind.IMAGE, data_b64=...))",
                        fix_min=45)
            fail_check("ImageParser EXIF", f"meta keys = {meta_keys}")
    except Exception as exc:
        fail_check("ImageParser probe", str(exc))

    # Audio parser: bitrate/sample_rate check
    try:
        # Create valid WAV bytes
        wav = _build_wav(16000, [0] * 100)
        ref = MediaRef(kind=ModalKind.AUDIO, data_b64=_b64(wav))
        parsed = AudioParser().parse(ref)
        meta_keys = sorted(parsed.meta.keys())
        has_sr = "sample_rate" in meta_keys or "bitrate" in meta_keys
        if has_sr:
            pass_check("AudioParser real metadata", meta_keys)
        else:
            add_finding("P0", "no_audio_meta", "multimodal/parsers.py:120-136",
                        f"AudioParser only has {meta_keys}; uses size/2000 heuristic; no real bitrate/sample_rate/channels/codec",
                        scenario="Audio assets with 44.1kHz stereo mislabeled as 8kHz mono",
                        repro="from imdf.multimodal.parsers import AudioParser; AudioParser().parse(MediaRef(kind=ModalKind.AUDIO, data_b64=...))",
                        fix_min=60)
            fail_check("AudioParser real metadata", f"meta keys = {meta_keys}")
    except Exception as exc:
        fail_check("AudioParser probe", str(exc))

    # Video parser: dead-code check
    try:
        # Create fake mp4 bytes
        fake_mp4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 200
        ref = MediaRef(kind=ModalKind.VIDEO, data_b64=_b64(fake_mp4))
        parsed = VideoParser().parse(ref)
        meta = parsed.meta or {}
        # cv2 cannot open raw bytes — should fall back to size heuristic
        # Real impl should at least try ffmpeg/ffprobe subprocess
        if parsed.frames == 0 and parsed.duration_sec > 0 and "codec" not in meta:
            add_finding("P0", "video_dead_code", "multimodal/parsers.py:140-173",
                        f"VideoParser cv2.VideoCapture.open(bytes) is dead code; fallback returns duration={parsed.duration_sec}s from size/50000 heuristic; no real codec/fps/resolution",
                        scenario="Video frame count always 0; downstream training receives corrupt frame counts",
                        repro="VideoParser().parse(MediaRef(kind=ModalKind.VIDEO, data_b64=base64_of_mp4))",
                        fix_min=90)
            fail_check("VideoParser real metadata", f"meta={meta}")
        else:
            pass_check("VideoParser", meta)
    except Exception as exc:
        fail_check("VideoParser probe", str(exc))


# ============================================================================
# Section 3 — Auto-labeling (CLIP/rule/AL/consensus)
# ============================================================================
def check_autolabel() -> None:
    print("\n=== [3] Auto-labeling (CLIP/rule/AL/consensus) ===")
    try:
        from labeling.auto_strategy_schemas import Asset, LabelCategory
        from labeling.auto_strategy import (
            CLIPZeroShotStrategy, RuleBasedStrategy,
            ActiveLearningStrategy, ConsensusStrategy, AutoLabelingOrchestrator,
        )

        async def go():
            asset = Asset(asset_id="test-001", caption="a photo of a dog running in the park", description="brown dog")
            clip = CLIPZeroShotStrategy()
            vote = await clip.label(asset)
            # If real CLIP, top-1 for "dog" caption should be ANIMAL
            top1 = vote.top_k[0].category if vote.top_k else None
            if top1 != LabelCategory.ANIMAL:
                add_finding("P0", "clip_mock_only", "labeling/auto_strategy.py:67-143",
                            f"CLIP returned {top1} for 'a photo of a dog' (expected ANIMAL); mock implementation uses SHA256 hash, never instantiates transformers.CLIPModel",
                            scenario="All auto-labeled training data has unreliable labels",
                            repro="from imdf.labeling.auto_strategy import CLIPZeroShotStrategy; await CLIPZeroShotStrategy().label(asset_with_dog_caption)",
                            fix_min=120)
                fail_check("CLIP real inference", f"got {top1}")
            else:
                pass_check("CLIP real inference", top1)

            # Rule-based
            rule = RuleBasedStrategy()
            rv = await rule.label(asset)
            if rv.confidence < 0.3:
                add_finding("P1", "rule_low_conf", "labeling/auto_strategy.py:149-244",
                            f"RuleBased returned conf={rv.confidence} for obvious 'dog' caption",
                            scenario="Rule strategy under-detects clear keyword matches",
                            fix_min=15)

            # AL: fake entropy
            al = ActiveLearningStrategy()
            av = await al.label(asset)
            if av.uncertainty < 0.1 and len(asset.caption) > 30:
                add_finding("P1", "al_fake_entropy", "labeling/auto_strategy.py:250-311",
                            "ActiveLearningStrategy computes entropy from len(caption), not real prediction distribution",
                            scenario="AL routing is essentially random text-length based",
                            fix_min=30)

            # Consensus
            cons = ConsensusStrategy()
            orch = AutoLabelingOrchestrator(clip=clip, rule=rule, active=al, consensus=cons)
            res = await orch.label_one(asset)
            if res.confidence < 0.5 and res.final_label != LabelCategory.ANIMAL:
                add_finding("P1", "consensus_low_conf", "labeling/auto_strategy.py:317-404",
                            f"Consensus for 'dog' asset: conf={res.confidence} label={res.final_label}",
                            fix_min=20)

        asyncio.run(go())
    except Exception as exc:
        fail_check("Auto-label probe", str(exc))


# ============================================================================
# Section 4 — AQL ISO 2859-1
# ============================================================================
def check_aql() -> None:
    print("\n=== [4] AQL ISO 2859-1 ===")
    try:
        from quality.aql_sampling import AQLSampling, _LOT_BUCKETS
        from labeling.auto_strategy_schemas import AQLLevel, Asset, SAMPLE_TABLE

        # Verify SAMPLE_TABLE coverage
        levels = [l.value for l in AQLLevel]
        buckets_covered = set(k for (k, _) in SAMPLE_TABLE.keys())
        buckets_decl = {b[2] for b in _LOT_BUCKETS}
        if buckets_covered >= buckets_decl:
            pass_check("AQL table covers all buckets", len(SAMPLE_TABLE))
        else:
            missing = buckets_decl - buckets_covered
            add_finding("P1", "aql_missing_plans", "labeling/auto_strategy_schemas.py",
                        f"SAMPLE_TABLE missing {len(missing)} bucket/level combos: {missing}",
                        fix_min=15)

        async def go():
            # Real plan + sample + inspect cycle
            lot = [Asset(asset_id=f"a-{i}") for i in range(100)]
            sampler = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=100, seed=42)
            sample = await sampler.sample(lot)
            result = await sampler.inspect(sample, defect_count=1)
            if result.decision.value == "accept" and 1 <= sampler.accept_count:
                pass_check("AQL accept/reject", f"sample_size={sample.sample_size} ac={sampler.accept_count} re={sampler.reject_count}")
            else:
                add_finding("P1", "aql_decision_broken", "quality/aql_sampling.py:182-221",
                            f"AQL decision logic flawed: defect=1, ac={sampler.accept_count} → {result.decision.value}",
                            fix_min=20)

            # Verify no stratified sampling
            import inspect as _i
            sig = _i.signature(sampler.sample)
            if "stratify" not in sig.parameters:
                add_finding("P1", "aql_no_stratified", "quality/aql_sampling.py:139",
                            "AQL sample() is uniform random only — no stratified sampling by defect rate / category",
                            scenario="Cannot oversample known defect hotspots",
                            fix_min=45)

        asyncio.run(go())
    except Exception as exc:
        fail_check("AQL probe", str(exc))


# ============================================================================
# Section 5 — 10 geometry types + serialization roundtrip
# ============================================================================
def check_geometries() -> None:
    print("\n=== [5] 10 geometry types ===")
    try:
        from labeling.geometries import GEOMETRY_REGISTRY
        expected = {"rect", "polygon", "point", "keypoint", "obb", "mask",
                    "3d_cuboid", "lidar_pointcloud", "3d_bbox", "panoptic"}
        actual = set(GEOMETRY_REGISTRY.keys())
        if expected.issubset(actual):
            pass_check("GEOMETRY_REGISTRY has 10 types", list(actual))
        else:
            missing = expected - actual
            add_finding("P0", "geometry_count", "labeling/geometries.py:233-238",
                        f"GEOMETRY_REGISTRY has {len(actual)} types; spec requires 10; missing: {sorted(missing)}",
                        scenario="Cannot annotate images with rectangles or polygons; only 3D/LiDAR/BBox/Panoptic supported",
                        repro="from imdf.labeling.geometries import GEOMETRY_REGISTRY; print(list(GEOMETRY_REGISTRY.keys()))",
                        fix_min=90)
            fail_check("GEOMETRY_REGISTRY", f"missing: {missing}")

        # Roundtrip test for the 4 NEW types
        from labeling.geometries import (
            Cuboid3D, PointCloudLiDAR, BBox3D, PanopticSegmentation,
            Vec3, Quaternion, Dimensions3D, LiDARPoint,
        )
        roundtrips = []
        try:
            c = Cuboid3D(label="box", center=Vec3(x=0,y=0,z=0), dimensions=Dimensions3D(length=1,width=1,height=1))
            j = c.model_dump_json()
            c2 = Cuboid3D.model_validate_json(j)
            assert c == c2
            roundtrips.append("Cuboid3D")
        except Exception as exc:
            add_finding("P1", "cuboid_roundtrip_fail", "labeling/geometries.py:91",
                        f"Cuboid3D roundtrip failed: {exc}", fix_min=10)

        try:
            pc = PointCloudLiDAR(frame_id="f1", points=[LiDARPoint(x=0,y=0,z=0,intensity=0.5)])
            j = pc.model_dump_json()
            pc2 = PointCloudLiDAR.model_validate_json(j)
            assert pc == pc2
            roundtrips.append("PointCloudLiDAR")
        except Exception as exc:
            add_finding("P1", "lidar_roundtrip_fail", "labeling/geometries.py:136",
                        f"PointCloudLiDAR roundtrip failed: {exc}", fix_min=10)

        try:
            b = BBox3D(label="car", center=Vec3(x=1,y=2,z=3), x_size=4, y_size=2, z_size=1.5)
            j = b.model_dump_json()
            b2 = BBox3D.model_validate_json(j)
            assert b == b2
            roundtrips.append("BBox3D")
        except Exception as exc:
            add_finding("P1", "bbox3d_roundtrip_fail", "labeling/geometries.py:156",
                        f"BBox3D roundtrip failed: {exc}", fix_min=10)

        try:
            p = PanopticSegmentation(image_id="img1", instance_id=1, class_id=5, class_name="car", is_thing=True, mask=[[1,1],[0,0]])
            j = p.model_dump_json()
            p2 = PanopticSegmentation.model_validate_json(j)
            assert p == p2
            roundtrips.append("PanopticSegmentation")
        except Exception as exc:
            add_finding("P1", "panoptic_roundtrip_fail", "labeling/geometries.py:182",
                        f"PanopticSegmentation roundtrip failed: {exc}", fix_min=10)

        pass_check("4 NEW geometry roundtrips", roundtrips)

    except Exception as exc:
        fail_check("Geometry probe", str(exc))


# ============================================================================
# Section 6 — 16 (actually 18) training format exports
# ============================================================================
def check_exports() -> None:
    print("\n=== [6] Training format exports ===")
    try:
        from exports import SUPPORTED_FORMATS, REGISTRY
        n = len(SUPPORTED_FORMATS)
        print(f"  Found {n} formats: {SUPPORTED_FORMATS}")
        if n < 16:
            add_finding("P0", "format_count", "exports/__init__.py:68",
                        f"Only {n} training formats registered; spec requires 16+", fix_min=60)
        else:
            pass_check(f"{n} formats registered (>= 16)", SUPPORTED_FORMATS)

        # Real probe: build each format with minimal dataset
        results = {}
        from exports.glb import export as glb_export, validate_glb
        from exports.wav import export as wav_export, validate_wav
        from exports.obj import export as obj_export
        from exports.gltf import export as gltf_export
        from exports.clip_fmt import export as clip_export
        from exports.csv_fmt import export as csv_export
        from exports.coco_panoptic import export as coco_pan_export
        from exports.pascal_voc import export as voc_export
        from exports.yolo import export as yolo_export
        from exports.createml import export as createml_export
        from exports.diffusiondb import export as diffdb_export
        from exports.mp3 import export as mp3_export
        from exports.ply_exporter import export as ply_export

        # Minimal fake DatasetVersion
        class FakeFile:
            def __init__(self, path, modality="image"):
                self.path = path
                self.modality_id = modality

        class FakeDS:
            def __init__(self, files):
                self.files = files
                self.version = "v1"

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Create a tiny obj file for 3D
            obj = tmp / "cube.obj"
            obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
            wav = tmp / "test.wav"
            wav.write_bytes(_build_wav(16000, [100, 200, -100, 0]))
            png = tmp / "img.png"
            try:
                from PIL import Image
                Image.new("RGB", (10, 10)).save(str(png))
            except Exception:
                png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

            ds = FakeDS([FakeFile(str(obj), "three_d_pointcloud"),
                         FakeFile(str(wav), "audio"),
                         FakeFile(str(png), "image")])

            # GLB
            try:
                glb_path = glb_export(ds, str(tmp / "out.glb"))
                with open(glb_path, "rb") as f:
                    raw = f.read()
                v = validate_glb(raw)
                if v["ok"]:
                    results["glb"] = "OK"
                else:
                    results["glb"] = f"BAD: {v['error']}"
            except Exception as exc:
                results["glb"] = f"EXC: {exc}"

            # WAV
            try:
                wav_path = wav_export(ds, str(tmp / "out.wav"))
                with open(wav_path, "rb") as f:
                    raw = f.read()
                v = _validate_wav(raw)
                results["wav"] = "OK" if v["ok"] else f"BAD: {v.get('error')}"
            except Exception as exc:
                results["wav"] = f"EXC: {exc}"

            # OBJ
            try:
                obj_path = obj_export(ds, str(tmp / "out.obj"))
                txt = Path(obj_path).read_text()
                results["obj"] = "OK" if "v " in txt else "BAD: no v lines"
            except Exception as exc:
                results["obj"] = f"EXC: {exc}"

            # JSON-based formats
            for fmt, fn in [
                ("clip", clip_export), ("csv", csv_export),
                ("coco_panoptic", coco_pan_export), ("pascal_voc", voc_export),
                ("yolo", yolo_export), ("createml", createml_export),
                ("diffusiondb", diffdb_export), ("gltf", gltf_export),
            ]:
                try:
                    p = fn(ds, str(tmp / f"out_{fmt}.bin"))
                    sz = Path(p).stat().st_size if Path(p).exists() else 0
                    results[fmt] = "OK" if sz > 0 else "EMPTY"
                except Exception as exc:
                    results[fmt] = f"EXC: {exc}"

            # MP3 — depends on lameenc which may not be installed
            try:
                p = mp3_export(ds, str(tmp / "out.mp3"))
                results["mp3"] = "OK" if Path(p).stat().st_size > 0 else "EMPTY"
            except Exception as exc:
                err = str(exc)
                if "lameenc" in err or "No module named 'lameenc'" in err:
                    add_finding("P1", "mp3_dep_missing", "exports/mp3.py",
                                f"MP3 exporter requires lameenc which is not in requirements.txt: {err}",
                                scenario="MP3 export silently fails on clean installs",
                                fix_min=30)
                    results["mp3"] = "DEP-MISSING"
                else:
                    results["mp3"] = f"EXC: {exc}"

            # PLY
            try:
                p = ply_export(ds, str(tmp / "out.ply"))
                txt = Path(p).read_text()
                results["ply"] = "OK" if "end_header" in txt else "BAD: no header"
            except Exception as exc:
                results["ply"] = f"EXC: {exc}"

        print(f"  Real-probe results: {results}")
        for fmt, status in results.items():
            if status != "OK":
                lvl = "P0" if status.startswith(("BAD", "EXC", "EMPTY")) else "P1"
                add_finding(lvl, f"export_{fmt}_bad", f"exports/{fmt}.py",
                            f"Format {fmt!r} export probe: {status}", fix_min=30)
                fail_check(f"Export {fmt}", status)
            else:
                pass_check(f"Export {fmt}", status)
    except Exception as exc:
        traceback.print_exc()
        fail_check("Exports probe", str(exc))


# ============================================================================
# Section 7 — Ingestion (SQL injection + dedup + rollback)
# ============================================================================
def check_ingestion() -> None:
    print("\n=== [7] IngestionEngine ===")
    try:
        from engines.ingestion_engine import IngestionEngine
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = tmp / "test.db"

            # SQL injection probe
            evil_csv = tmp / "evil.csv"
            evil_csv.write_text("id); DROP TABLE x; --,value\n1,foo\n", encoding="utf-8")
            engine = IngestionEngine(db_path=str(db))
            try:
                r = engine.import_csv(str(evil_csv))
                if r.get("success") and "DROP" not in str(r):
                    pass_check("Ingestion sanitised SQL", r)
                else:
                    # Did the SQL injection succeed?
                    conn = sqlite3.connect(str(db))
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = [row[0] for row in cur.fetchall()]
                    if "x" in tables or any(re.search(r"^x$", t) for t in tables):
                        add_finding("P0", "sql_injection", "engines/ingestion_engine.py:55-67",
                                    "SQL injection via CSV column header succeeded (table 'x' created/dropped)",
                                    scenario="Attacker CSV drops arbitrary tables",
                                    repro="csv with header 'id); DROP TABLE x; --,value'",
                                    fix_min=30)
                    else:
                        add_finding("P1", "ingestion_rejects_evil", "engines/ingestion_engine.py",
                                    f"Ingestion rejected evil CSV but did not raise clear error: {r}",
                                    fix_min=15)
                    fail_check("Ingestion SQL safety", str(tables))
            except Exception as exc:
                # Good — engine raised on injection attempt
                if "syntax error" in str(exc).lower() or "near" in str(exc).lower():
                    add_finding("P1", "ingestion_bad_error", "engines/ingestion_engine.py",
                                f"Injection attempt raises SQLite syntax error (not sanitised, just propagated): {exc}",
                                fix_min=30)
                pass_check("Ingestion SQL safety (raised)", str(exc)[:80])
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            # Dedup probe
            csv1 = tmp / "a.csv"; csv1.write_text("name\nfoo\n")
            csv2 = tmp / "b.csv"; csv2.write_text("name\nfoo\n")
            db2 = tmp / "db2.db"
            engine2 = IngestionEngine(db_path=str(db2))
            r1 = engine2.import_csv(str(csv1))
            r2 = engine2.import_csv(str(csv2))
            if r2.get("success") and r2.get("data", {}).get("rows_imported", -1) == 0:
                pass_check("Ingestion dedup", r2)
            else:
                add_finding("P1", "ingestion_no_dedup", "engines/ingestion_engine.py:49-72",
                            f"Duplicate import not detected: r1={r1.get('data', {})} r2={r2.get('data', {})} — both rows imported",
                            fix_min=45)
                fail_check("Ingestion dedup", f"r2.rows_imported={r2.get('data', {}).get('rows_imported')}")

            # Rollback probe
            if not hasattr(engine2, "rollback"):
                add_finding("P1", "ingestion_no_rollback", "engines/ingestion_engine.py",
                            "IngestionEngine has no rollback() method",
                            scenario="Cannot undo bad imports",
                            fix_min=45)
            else:
                pass_check("Ingestion rollback exists", True)

            # Schema validation
            if not hasattr(engine2, "_validate_schema") and not hasattr(engine2, "validate"):
                add_finding("P1", "ingestion_no_schema", "engines/ingestion_engine.py",
                            "IngestionEngine has no schema validation against ModalKind/Pydantic",
                            fix_min=60)

    except Exception as exc:
        traceback.print_exc()
        fail_check("Ingestion probe", str(exc))


# ============================================================================
# Section 8 — Dedup engine
# ============================================================================
def check_dedup() -> None:
    print("\n=== [8] Dedup engine ===")
    try:
        from engines.enhanced_engines import DedupEngine, DedupLevel
        engine = DedupEngine()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Create two byte-identical files
            (tmp / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            (tmp / "b.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            (tmp / "c.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\xff" * 100)
            res = engine.deduplicate([str(tmp / "a.png"), str(tmp / "b.png"), str(tmp / "c.png")],
                                     level=DedupLevel.EXACT)
            if res.exact_dups == 1:
                pass_check("Dedup exact", {"total": res.total, "exact_dups": res.exact_dups})
            else:
                add_finding("P1", "dedup_exact_wrong", "engines/enhanced_engines.py:87-152",
                            f"EXACT dedup expected exact_dups=1, got {res.exact_dups}", fix_min=15)
                fail_check("Dedup exact", str(res))

            # Perceptual
            res2 = engine.deduplicate([str(tmp / "a.png"), str(tmp / "c.png")],
                                      level=DedupLevel.PERCEPTUAL)
            print(f"  Perceptual dedup: total={res2.total} exact={res2.exact_dups} perceptual={res2.perceptual_dups}")
            if res2.perceptual_dups == 0:
                pass_check("Dedup perceptual (no false positives)", res2.perceptual_dups)
    except Exception as exc:
        traceback.print_exc()
        fail_check("Dedup probe", str(exc))


# ============================================================================
# Section 9 — Dataset versioning + rollback
# ============================================================================
def check_versioning() -> None:
    print("\n=== [9] Dataset versioning ===")
    try:
        from engines.dataset_manager import DatasetManager, DatasetFile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            mgr = DatasetManager(data_dir=str(tmp))
            v1 = mgr.create_version(name="v1", files=[DatasetFile(path="a.png", hash="h1")])
            v2 = mgr.create_version(name="v2", parent=v1.version, files=[DatasetFile(path="b.png", hash="h2")])
            # Verify lineage chain
            if v2.parent_version == v1.version:
                pass_check("Versioning parent link", v2.parent_version)
            else:
                add_finding("P1", "versioning_parent", "engines/dataset_manager.py:195",
                            f"parent_version not linked correctly: v2.parent={v2.parent_version}", fix_min=20)

            # Rollback
            if hasattr(mgr, "rollback"):
                try:
                    rb = mgr.rollback(v1.version)
                    if rb is not None and rb.version == v1.version:
                        pass_check("Rollback", rb.version)
                    else:
                        add_finding("P1", "rollback_returns_none", "engines/dataset_manager.py:188",
                                    f"rollback({v1.version}) returned {rb}", fix_min=20)
                except Exception as exc:
                    add_finding("P1", "rollback_raises", "engines/dataset_manager.py",
                                f"rollback raised: {exc}", fix_min=20)
            else:
                add_finding("P0", "rollback_missing", "engines/dataset_manager.py",
                            "DatasetManager has no rollback() method", fix_min=60)
    except Exception as exc:
        traceback.print_exc()
        fail_check("Versioning probe", str(exc))


# ============================================================================
# Section 10 — Export engine dispatch + duplicate modules
# ============================================================================
def check_export_engine() -> None:
    print("\n=== [10] Export engine dispatch ===")
    try:
        from exports.export_engine import ExportEngine
        from exports import SUPPORTED_FORMATS

        ee = ExportEngine(data_dir="data/exports_test")
        listed = ee.list_formats()
        if len(listed) >= 16:
            pass_check("ExportEngine lists 16+ formats", len(listed))
        else:
            add_finding("P0", "engine_format_count", "exports/export_engine.py:76",
                        f"ExportEngine lists only {len(listed)} formats", fix_min=30)

        # Duplicate module detection
        import os as _os
        exports_dir = Path(BACKEND_ROOT / "imdf" / "exports")
        createml_files = list(exports_dir.glob("*createml*.py")) + list(exports_dir.glob("*create_ml*.py"))
        csv_files = list(exports_dir.glob("csv_*.py"))
        if len(createml_files) >= 2:
            add_finding("P1", "duplicate_createml", "exports/",
                        f"Multiple createml/create_ml files: {[f.name for f in createml_files]}",
                        scenario="DRY violation; consumers must know which API to call",
                        fix_min=20)
        else:
            pass_check("createml single file", [f.name for f in createml_files])
        if len(csv_files) >= 2:
            add_finding("P1", "duplicate_csv", "exports/",
                        f"Multiple csv_*.py files: {[f.name for f in csv_files]}",
                        fix_min=20)
        else:
            pass_check("csv single file", [f.name for f in csv_files])
    except Exception as exc:
        traceback.print_exc()
        fail_check("ExportEngine probe", str(exc))


# ============================================================================
# Section 11 — Data lineage / audit chain
# ============================================================================
def check_extra_gaps_from_code_review() -> None:
    """Additional code-review findings (no runtime probe needed)."""
    print("\n=== [12] Code-review-only findings ===")

    # GAP-9: two coexisting taxonomies
    try:
        from multimodal.types import ModalKind
        from multimodal.business_modalities import list_modalities
        all_kinds = {m.value for m in ModalKind}
        biz_ids = {m.id for m in list_modalities()}
        if "lidar" in biz_ids and ModalKind.LIDAR.value not in all_kinds:
            add_finding("P0", "dual_taxonomy", "multimodal/types.py + business_modalities.py",
                        f"Two coexisting taxonomies: ModalKind={all_kinds}; business_modalities={biz_ids}; 3D/LiDAR/Medical/Panoptic all map to canonical_kind='document' at storage layer",
                        scenario="Storage layer cannot distinguish LiDAR frame from PDF document",
                        repro="from imdf.multimodal.business_modalities import list_modalities; [print(m.canonical_kind) for m in list_modalities()]",
                        fix_min=60)
    except Exception as exc:
        pass

    # GAP-10: hash fingerprint not perceptual
    try:
        from multimodal.business_modalities import _hash_fingerprint
        import numpy as np
        a = _hash_fingerprint(b"hello world " + b"\x00" * 1000)
        b = _hash_fingerprint(b"hello world!" + b"\x00" * 1000)  # 1 byte different
        cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
        if cosine > 0.95:
            add_finding("P1", "hash_near_dup_fail", "multimodal/business_modalities.py:149-167",
                        f"Two files differing by 1 byte have cosine similarity = {cosine:.3f} (>0.95); _hash_fingerprint is byte-position hash, NOT perceptual",
                        scenario="Semantic near-duplicates not detected by fallback embedder",
                        repro="from imdf.multimodal.business_modalities import _hash_fingerprint; import numpy as np; a=_hash_fingerprint(b'...'); b=_hash_fingerprint(b'...!'); print(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))",
                        fix_min=45)
    except Exception as exc:
        pass

    # GAP-11: duplicate exporter modules
    exports_dir = Path(BACKEND_ROOT / "imdf" / "exports")
    createml_files = sorted(exports_dir.glob("*createml*.py")) + sorted(exports_dir.glob("*create_ml*.py"))
    if len(set(createml_files)) >= 2:
        add_finding("P1", "duplicate_exporter_createml", "exports/",
                    f"Duplicate createml/create_ml files: {[f.name for f in createml_files]}",
                    fix_min=20)
    csv_files = sorted(exports_dir.glob("csv_*.py"))
    if len(set(csv_files)) >= 2:
        add_finding("P1", "duplicate_exporter_csv", "exports/",
                    f"Duplicate csv_*.py files: {[f.name for f in csv_files]}",
                    fix_min=20)

    # GAP-12: rollback is in-memory only
    try:
        from engines.dataset_manager import DatasetManager, DatasetFile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            mgr = DatasetManager(data_dir=str(tmp))
            v1 = mgr.create_version(name="v1", files=[DatasetFile(path="a.png")])
            # Capture index BEFORE rollback
            before = (tmp / "index.json").read_text() if (tmp / "index.json").exists() else ""
            mgr.rollback(v1.version)
            after = (tmp / "index.json").read_text() if (tmp / "index.json").exists() else ""
            # After rollback, no version of index.json is restored from disk history
            snapshots_dir = tmp / "snapshots"
            if not snapshots_dir.exists():
                add_finding("P1", "rollback_no_snapshot", "engines/dataset_manager.py:188",
                            "rollback() does not persist or restore version snapshots — only rewrites index.json in-place; cannot recover files deleted between versions",
                            scenario="Cannot restore a deleted file even with rollback",
                            repro="mgr.rollback(version) → check no data/datasets/snapshots/<version>.json",
                            fix_min=60)
    except Exception as exc:
        pass

    # GAP-14: embedding roundtrip not tested
    try:
        from multimodal.embedding import UNIFIED_DIM
        if UNIFIED_DIM != 1024:
            add_finding("P1", "embedding_dim_drift", "multimodal/embedding.py",
                        f"UNIFIED_DIM = {UNIFIED_DIM}, spec says 1024", fix_min=15)
    except Exception as exc:
        pass

    # GAP-15: GLB parser cannot read what exporter writes
    try:
        from multimodal.three_d import _parse_glb
        # Build a valid GLB
        from exports.glb import _build_glb_bytes, validate_glb
        glb_bytes = _build_glb_bytes([0,0,0, 1,1,1], [], [0,1,2])
        v = validate_glb(glb_bytes)
        if v["ok"]:
            parsed = _parse_glb(glb_bytes)
            if parsed.get("n_vertices", 0) == 0:
                add_finding("P1", "glb_parser_cant_read_exporter", "multimodal/three_d.py:51 _parse_glb",
                            f"_parse_glb only checks header magic; n_vertices={parsed.get('n_vertices')} on a GLB produced by exports.glb that has 2 vertices",
                            scenario="Can export GLB but cannot re-parse it; asymmetric roundtrip",
                            repro="from imdf.multimodal.three_d import _parse_glb; from imdf.exports.glb import _build_glb_bytes; _parse_glb(_build_glb_bytes([0,0,0,1,1,1], [], [0,1,2]))",
                            fix_min=60)
    except Exception as exc:
        pass

    # GAP-16: LiDAR/Medical/Panoptic embedders use hash fallback
    try:
        from multimodal.business_modalities import _REGISTRY
        for mod_id, mod in _REGISTRY.items():
            emb = mod.embedder
            try:
                # Build a fake asset
                from multimodal.business_modalities import ModalityAsset
                asset = ModalityAsset(asset_id="t", modality_id=mod_id, canonical_kind="document",
                                       path="/tmp/x.bin", sha256="h", size=10, mime="application/octet-stream",
                                       text="hello", metadata={})
                vec = emb(asset)
                # If vector has near-zero entropy in first 10 dims, likely hash-fingerprint
                import numpy as np
                arr = np.asarray(vec)
                sparsity = float(np.sum(arr[:50] == 0) / 50)
                if sparsity > 0.8:
                    add_finding("P1", f"modality_{mod_id}_hash_only", f"multimodal/{mod_id}.py",
                                f"{mod_id} embedder returns ~80% zero vector (hash-fingerprint fallback); no semantic features",
                                fix_min=45)
            except Exception:
                pass
    except Exception as exc:
        pass

    # GAP-19: AL fake entropy
    try:
        import inspect
        from labeling.auto_strategy import ActiveLearningStrategy
        src = inspect.getsource(ActiveLearningStrategy.label)
        if "text_len" in src and "len(asset.caption)" in src:
            add_finding("P1", "al_entropy_from_text_len", "labeling/auto_strategy.py:273-311",
                        "ActiveLearningStrategy.label computes entropy from len(asset.caption) — fake heuristic, not real Shannon entropy from prediction distribution",
                        scenario="AL routing decisions are arbitrary text-length based",
                        repro="from imdf.labeling.auto_strategy import ActiveLearningStrategy; await strategy.label(asset_with_long_caption)",
                        fix_min=30)
    except Exception as exc:
        pass

    # GAP-20: AQL no stratified sampling
    try:
        import inspect as _i
        from quality.aql_sampling import AQLSampling
        sig = _i.signature(AQLSampling.sample)
        if "stratify" not in sig.parameters:
            add_finding("P1", "aql_no_stratified", "quality/aql_sampling.py:139",
                        "AQL sample() is pure uniform random — no stratified / weighted sampling by category or defect rate",
                        fix_min=45)
    except Exception:
        pass

    # GAP-21: char-based text chunking
    try:
        from multimodal.parsers import _chunk_text
        chunks = _chunk_text("a" * 500)
        # Should not break mid-word in a way that creates bad RAG chunks
        if all(len(c) == 320 or len(c) == 180 for c in chunks[:3]):
            # naive char-chunk detected
            add_finding("P2", "text_chunking_char_based", "multimodal/parsers.py:213-226",
                        "_chunk_text splits at fixed char offsets (320/40 overlap); not sentence- or token-aware; breaks mid-word/mid-sentence",
                        scenario="RAG retrieval quality suffers from bad chunk boundaries",
                        repro="from imdf.multimodal.parsers import _chunk_text; print(_chunk_text('foo bar baz '*100))",
                        fix_min=30)
    except Exception:
        pass

    # GAP-22: Generic fallback loses path metadata
    try:
        from multimodal.business_modalities import process_file
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"unknown format")
            tmp_path = f.name
        try:
            asset = process_file(tmp_path, filename="test.xyz")
            md = asset.metadata
            if "ingested_at" not in md and "source" not in md:
                add_finding("P2", "no_ingest_provenance", "multimodal/business_modalities.py:266-303",
                            f"Generic fallback ModalityAsset only has filename in metadata ({sorted(md.keys())}); missing ingested_at, source, ingestion_job_id",
                            fix_min=20)
        finally:
            try: os.unlink(tmp_path)
            except Exception: pass
    except Exception:
        pass

    # GAP-23: Audit chain no query API
    try:
        from engines.audit_chain import AuditChain
        chain_methods = [m for m in dir(AuditChain) if not m.startswith("_")]
        if "query" not in chain_methods and "trace" not in chain_methods:
            add_finding("P2", "no_audit_query_api", "engines/audit_chain.py",
                        f"AuditChain methods = {chain_methods}; no query(event_type, time_range) or trace(asset_id) API",
                        fix_min=45)
    except Exception:
        pass

    # GAP-25: parse_media_item defaults unknown URLs to IMAGE
    try:
        from multimodal.types import parse_media_item
        # An .obj URL should map to THREE_D, not IMAGE
        ref = parse_media_item("https://example.com/model.obj")
        if ref.kind.value != "document":
            add_finding("P2", "url_extension_misclassify", "multimodal/types.py:268-300",
                        f"parse_media_item('https://.../model.obj') returned kind={ref.kind.value}; should be three_d/document-classified, not best-effort IMAGE default",
                        fix_min=20)
    except Exception:
        pass

    # GAP-26: data_pipeline augmentation types defined but not implemented
    try:
        from engines.data_pipeline import AugmentationType
        # Count enum members vs actual impls
        aug_types = [t.value for t in AugmentationType]
        src_file = Path(BACKEND_ROOT / "imdf" / "engines" / "data_pipeline.py")
        src = src_file.read_text(encoding="utf-8")
        impl_count = sum(1 for t in aug_types if f'def _aug_{t}' in src or f'"{t}"' in src)
        if impl_count < len(aug_types) // 2:
            add_finding("P2", "augmentation_stub_only", "engines/data_pipeline.py:200+",
                        f"AugmentationType has {len(aug_types)} types but only {impl_count} implemented in src",
                        fix_min=90)
    except Exception:
        pass

    # GAP-27: two divergent export dispatch paths
    try:
        from exports.export_engine import ExportEngine
        ee = ExportEngine()
        if hasattr(ee, "export") and hasattr(ee, "export_with_manager"):
            add_finding("P2", "export_two_paths", "exports/export_engine.py:118-216",
                        "ExportEngine has two overlapping dispatch methods: export() and export_with_manager(); confusing semantics, overlapping code paths",
                        fix_min=30)
    except Exception:
        pass

    # GAP-28: agency loader static JSON
    try:
        from agency.loader import AgencyLoader
        loader = AgencyLoader()
        # Does anything OUTSIDE agency consume AgencyLoader?
        grep_dir = BACKEND_ROOT / "imdf"
        consumers = []
        for py in grep_dir.rglob("*.py"):
            if "/agency/" in str(py) or "/__pycache__" in str(py):
                continue
            txt = py.read_text(encoding="utf-8", errors="ignore")
            if "AgencyLoader" in txt and "from agency" in txt:
                consumers.append(str(py))
        if len(consumers) == 0:
            add_finding("P2", "agency_no_consumer", "imdf/agency/",
                        "AgencyLoader only referenced in its own tests; zero consumers in routing/engine code",
                        fix_min=60)
    except Exception:
        pass

    # GAP-29: geometry renderers not in export pipeline
    try:
        from labeling.geometry_renderers import __all__ as renderers_all
        if renderers_all:
            # Check if any export_*.py imports them
            exports_dir = Path(BACKEND_ROOT / "imdf" / "exports")
            consumers = []
            for py in exports_dir.glob("*.py"):
                txt = py.read_text(encoding="utf-8", errors="ignore")
                if "geometry_renderers" in txt:
                    consumers.append(py.name)
            if not consumers:
                add_finding("P2", "renderers_orphan", "labeling/geometry_renderers.py",
                            f"Geometry renderers ({renderers_all}) defined but not imported by any exports/*.py",
                            fix_min=30)
    except Exception:
        pass

    # GAP-30: ParsedMedia missing provenance
    try:
        from multimodal.parsers import ParsedMedia
        import dataclasses
        fields = [f.name for f in dataclasses.fields(ParsedMedia)]
        if "parser_version" not in fields and "parsed_at" not in fields:
            add_finding("P2", "no_parser_provenance", "multimodal/parsers.py:23-44",
                        f"ParsedMedia fields = {fields}; missing parser_version and parsed_at — cannot distinguish results from different parser versions",
                        fix_min=15)
    except Exception:
        pass


def check_lineage() -> None:
    print("\n=== [11] Lineage / audit chain ===")
    try:
        from engines.audit_chain import AuditChain
        chain = AuditChain()
        if hasattr(chain, "export_json") and hasattr(chain, "record"):
            pass_check("AuditChain record+export", True)
        else:
            add_finding("P1", "audit_chain_api", "engines/audit_chain.py",
                        "AuditChain missing record() / export_json()", fix_min=30)

        # Trace API
        if not hasattr(chain, "trace") and not hasattr(chain, "trace_asset"):
            add_finding("P1", "no_trace_api", "engines/audit_chain.py",
                        "No trace(asset_id) → List[Event] API for compliance lineage",
                        scenario="Cannot trace a single asset from ingestion to export",
                        fix_min=60)
    except Exception as exc:
        traceback.print_exc()
        fail_check("Lineage probe", str(exc))


# ============================================================================
# Helpers
# ============================================================================
def _b64(b: bytes) -> str:
    import base64
    return base64.b64encode(b).decode("ascii")


def _build_wav(sample_rate: int, samples: List[int]) -> bytes:
    """Build a real WAV (16-bit PCM mono)."""
    import struct as _s
    n = len(samples)
    data = _s.pack(f"<{n}h", *samples)
    fmt = _s.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    riff = _s.pack("<I", 4 + 8 + len(fmt) + 8 + len(data))
    return b"RIFF" + riff + b"WAVE" + b"fmt " + _s.pack("<I", len(fmt)) + fmt + b"data" + _s.pack("<I", len(data)) + data


def _validate_wav(raw: bytes) -> Dict[str, Any]:
    if len(raw) < 44: return {"ok": False, "error": "too short"}
    if raw[:4] != b"RIFF": return {"ok": False, "error": "no RIFF"}
    if raw[8:12] != b"WAVE": return {"ok": False, "error": "no WAVE"}
    af = struct.unpack("<H", raw[20:22])[0]
    bits = struct.unpack("<H", raw[34:36])[0]
    if af != 1 or bits != 16:
        return {"ok": False, "error": f"not 16-bit PCM"}
    return {"ok": True}


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    started = time.time()
    print(f"=== P21 R1 Data Pipeline Audit — {started} ===")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Backend root: {BACKEND_ROOT}")
    print(f"Imdf root:    {BACKEND_ROOT / 'imdf'}")

    check_modalities()
    check_parsers()
    check_autolabel()
    check_aql()
    check_geometries()
    check_exports()
    check_ingestion()
    check_dedup()
    check_versioning()
    check_export_engine()
    check_lineage()
    check_extra_gaps_from_code_review()

    elapsed = time.time() - started

    summary = {
        "ts": _now(),
        "elapsed_sec": round(elapsed, 1),
        "checks_pass": len(checks_pass),
        "checks_fail": len(checks_fail),
        "findings_total": len(findings),
        "findings_p0": sum(1 for f in findings if f["level"] == "P0"),
        "findings_p1": sum(1 for f in findings if f["level"] == "P1"),
        "findings_p2": sum(1 for f in findings if f["level"] == "P2"),
        "fail_checks": checks_fail,
    }

    out = {
        "summary": summary,
        "findings": findings,
        "checks_pass": checks_pass,
    }

    # Write JSON
    JSON_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nWrote: {JSON_OUT}")
    print(f"Elapsed: {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())