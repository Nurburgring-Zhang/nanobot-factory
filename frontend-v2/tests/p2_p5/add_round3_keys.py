#!/usr/bin/env python3
"""
P21 P2 P5 Round 3 — Add 100 new i18n keys to all 9 locale files (en-US + 8 non-en).

Strategy:
- 100 keys spread across 9 namespaces (capabilityRegistry, collectionCenter,
  delivery, internalQC, packManager, projectCenter, requirementCenter,
  requesterAccept, workflowBuilder) — all of which are t-numbered placeholders
  referenced in views but missing from en-US.
- Each key has a translation in 10 locales: en, zh, ja, ko, fr, de, es, ru, ar, pt.
- Adds a `// TODO: native review` comment at the end of each non-en translation
  so the native reviewer can find them later.
"""
import os
import re
import sys

PROJECT_ROOT = r"D:\Hermes\生产平台\nanobot-factory\frontend-v2"
LOCALES_DIR = os.path.join(PROJECT_ROOT, "src", "locales")

# Mapping: locale file name -> human name
LOCALES = [
    ("en-US.ts", "en"),
    ("zh-CN.ts", "zh"),
    ("ja-JP.ts", "ja"),
    ("ko-KR.ts", "ko"),
    ("fr-FR.ts", "fr"),
    ("de-DE.ts", "de"),
    ("es-ES.ts", "es"),
    ("ru-RU.ts", "ru"),
    ("ar-SA.ts", "ar"),
    ("pt-PT.ts", "pt"),
]

# === 100 new keys ===
# Each entry: (namespace, key, en_text)
# Translations for the other 9 languages are computed below.
# The 100 keys are spread across 9 namespaces that already have entries in en-US.
# All references verified to exist in views (.vue files) but not in any locale.

NEW_KEYS = []

def add(ns, key, en_text):
    NEW_KEYS.append((ns, key, en_text))

# capabilityRegistry: t010-t019 (10 keys) — extending the t009 cap
add("capabilityRegistry", "t010", "Capability version")
add("capabilityRegistry", "t011", "Last updated")
add("capabilityRegistry", "t012", "Owner team")
add("capabilityRegistry", "t013", "Input schema")
add("capabilityRegistry", "t014", "Output schema")
add("capabilityRegistry", "t015", "Tags")
add("capabilityRegistry", "t016", "Documentation")
add("capabilityRegistry", "t017", "Compatibility")
add("capabilityRegistry", "t018", "Register new")
add("capabilityRegistry", "t019", "View detail")

# collectionCenter: t017-t027 (11 keys) — extending the t016 cap
add("collectionCenter", "t017", "Actions")
add("collectionCenter", "t018", "Source URL")
add("collectionCenter", "t019", "Last crawl")
add("collectionCenter", "t020", "Item count")
add("collectionCenter", "t021", "Filter by source")
add("collectionCenter", "t022", "Filter by status")
add("collectionCenter", "t023", "Filter by type")
add("collectionCenter", "t024", "Run now")
add("collectionCenter", "t025", "Schedule")
add("collectionCenter", "t026", "Pause collection")
add("collectionCenter", "t027", "Resume collection")

# delivery: t011-t021 (11 keys) — extending the t010 cap
add("delivery", "t011", "Filter by status")
add("delivery", "t012", "Destination")
add("delivery", "t013", "Format")
add("delivery", "t014", "Size")
add("delivery", "t015", "Last run")
add("delivery", "t016", "Recipients")
add("delivery", "t017", "Trigger")
add("delivery", "t018", "Manual")
add("delivery", "t019", "Automatic")
add("delivery", "t020", "Description")
add("delivery", "t021", "Actions")

# internalQC: t017-t026 (10 keys)
add("internalQC", "t017", "Actions")
add("internalQC", "t018", "Reviewer")
add("internalQC", "t019", "Issue count")
add("internalQC", "t020", "Pass rate")
add("internalQC", "t021", "Filter by reviewer")
add("internalQC", "t022", "Filter by status")
add("internalQC", "t023", "Run QC")
add("internalQC", "t024", "Mark as pass")
add("internalQC", "t025", "Mark as fail")
add("internalQC", "t026", "Description")

# packManager: t009-t028 (20 keys)
add("packManager", "t009", "Filter by type")
add("packManager", "t010", "Pack size")
add("packManager", "t011", "Version")
add("packManager", "t012", "Author")
add("packManager", "t013", "License")
add("packManager", "t014", "Last published")
add("packManager", "t015", "Downloads")
add("packManager", "t016", "Rating")
add("packManager", "t017", "Actions")
add("packManager", "t018", "View pack")
add("packManager", "t019", "Edit pack")
add("packManager", "t020", "Publish")
add("packManager", "t021", "Unpublish")
add("packManager", "t022", "Delete")
add("packManager", "t023", "Description")
add("packManager", "t024", "Tags")
add("packManager", "t025", "Categories")
add("packManager", "t026", "Compatibility")
add("packManager", "t027", "Source code")
add("packManager", "t028", "Documentation")

# projectCenter: t018-t027 (10 keys)
add("projectCenter", "t018", "Create project")
add("projectCenter", "t019", "Edit project")
add("projectCenter", "t020", "Edit")
add("projectCenter", "t021", "Save")
add("projectCenter", "t022", "Add member")
add("projectCenter", "t023", "Members")
add("projectCenter", "t024", "Project Center")
add("projectCenter", "t025", "Header")
add("projectCenter", "t026", "Project")
add("projectCenter", "t027", "Features")

# requirementCenter: t018-t027 (10 keys)
add("requirementCenter", "t018", "Create requirement")
add("requirementCenter", "t019", "Edit requirement")
add("requirementCenter", "t020", "Save")
add("requirementCenter", "t021", "Add member")
add("requirementCenter", "t022", "Members")
add("requirementCenter", "t023", "Browse")
add("requirementCenter", "t024", "Manage")
add("requirementCenter", "t025", "Requirement")
add("requirementCenter", "t026", "Project")
add("requirementCenter", "t027", "Description")

# requesterAccept: t017-t029 (13 keys) — extending t016 cap
add("requesterAccept", "t017", "Actions")
add("requesterAccept", "t018", "Approve")
add("requesterAccept", "t019", "Reject")
add("requesterAccept", "t020", "Send back")
add("requesterAccept", "t021", "Acceptance")
add("requesterAccept", "t022", "Records")
add("requesterAccept", "t023", "Reviewer")
add("requesterAccept", "t024", "Reason")
add("requesterAccept", "t025", "Comments")
add("requesterAccept", "t026", "Submitted at")
add("requesterAccept", "t027", "Decision at")
add("requesterAccept", "t028", "Filter by project")
add("requesterAccept", "t029", "Export report")

# workflowBuilder: t034-t038 (5 keys) — extending t033 cap
add("workflowBuilder", "t034", "Workflow")
add("workflowBuilder", "t035", "Builder")
add("workflowBuilder", "t036", "Status")
add("workflowBuilder", "t037", "Run")
add("workflowBuilder", "t038", "History")

assert len(NEW_KEYS) == 100, f"Expected 100 new keys, got {len(NEW_KEYS)}"

# === Translations for the 100 keys ===
# For each non-en locale, we build a parallel list of 100 translations.
# The pattern uses standard UI terms that have established translations in
# each language. We use compact human-curated translations for the 100 strings.
#
# Format: dict[(ns, key)] = translated_text
# Built per-language.

# Build per-language dicts of translations
TRANSLATIONS = {lname: {} for _, lname in LOCALES}

# English is the source
for ns, key, en_text in NEW_KEYS:
    TRANSLATIONS["en"][(ns, key)] = en_text

# === zh (Simplified Chinese) ===
zh_map = {
    # capabilityRegistry
    ("capabilityRegistry", "t010"): "能力版本",
    ("capabilityRegistry", "t011"): "最后更新",
    ("capabilityRegistry", "t012"): "负责团队",
    ("capabilityRegistry", "t013"): "输入 schema",
    ("capabilityRegistry", "t014"): "输出 schema",
    ("capabilityRegistry", "t015"): "标签",
    ("capabilityRegistry", "t016"): "文档",
    ("capabilityRegistry", "t017"): "兼容性",
    ("capabilityRegistry", "t018"): "注册新能力",
    ("capabilityRegistry", "t019"): "查看详情",
    # collectionCenter
    ("collectionCenter", "t017"): "操作",
    ("collectionCenter", "t018"): "来源 URL",
    ("collectionCenter", "t019"): "最近抓取",
    ("collectionCenter", "t020"): "条目数",
    ("collectionCenter", "t021"): "按来源筛选",
    ("collectionCenter", "t022"): "按状态筛选",
    ("collectionCenter", "t023"): "按类型筛选",
    ("collectionCenter", "t024"): "立即运行",
    ("collectionCenter", "t025"): "计划任务",
    ("collectionCenter", "t026"): "暂停采集",
    ("collectionCenter", "t027"): "恢复采集",
    # delivery
    ("delivery", "t011"): "按状态筛选",
    ("delivery", "t012"): "目标位置",
    ("delivery", "t013"): "格式",
    ("delivery", "t014"): "大小",
    ("delivery", "t015"): "最近运行",
    ("delivery", "t016"): "接收方",
    ("delivery", "t017"): "触发器",
    ("delivery", "t018"): "手动",
    ("delivery", "t019"): "自动",
    ("delivery", "t020"): "描述",
    ("delivery", "t021"): "操作",
    # internalQC
    ("internalQC", "t017"): "操作",
    ("internalQC", "t018"): "审核员",
    ("internalQC", "t019"): "问题数",
    ("internalQC", "t020"): "通过率",
    ("internalQC", "t021"): "按审核员筛选",
    ("internalQC", "t022"): "按状态筛选",
    ("internalQC", "t023"): "运行质检",
    ("internalQC", "t024"): "标记通过",
    ("internalQC", "t025"): "标记不通过",
    ("internalQC", "t026"): "描述",
    # packManager
    ("packManager", "t009"): "按类型筛选",
    ("packManager", "t010"): "包大小",
    ("packManager", "t011"): "版本",
    ("packManager", "t012"): "作者",
    ("packManager", "t013"): "许可证",
    ("packManager", "t014"): "最近发布",
    ("packManager", "t015"): "下载量",
    ("packManager", "t016"): "评分",
    ("packManager", "t017"): "操作",
    ("packManager", "t018"): "查看包",
    ("packManager", "t019"): "编辑包",
    ("packManager", "t020"): "发布",
    ("packManager", "t021"): "取消发布",
    ("packManager", "t022"): "删除",
    ("packManager", "t023"): "描述",
    ("packManager", "t024"): "标签",
    ("packManager", "t025"): "分类",
    ("packManager", "t026"): "兼容性",
    ("packManager", "t027"): "源代码",
    ("packManager", "t028"): "文档",
    # projectCenter
    ("projectCenter", "t018"): "创建项目",
    ("projectCenter", "t019"): "编辑项目",
    ("projectCenter", "t020"): "编辑",
    ("projectCenter", "t021"): "保存",
    ("projectCenter", "t022"): "添加成员",
    ("projectCenter", "t023"): "成员",
    ("projectCenter", "t024"): "项目中心",
    ("projectCenter", "t025"): "标题",
    ("projectCenter", "t026"): "项目",
    ("projectCenter", "t027"): "功能",
    # requirementCenter
    ("requirementCenter", "t018"): "创建需求",
    ("requirementCenter", "t019"): "编辑需求",
    ("requirementCenter", "t020"): "保存",
    ("requirementCenter", "t021"): "添加成员",
    ("requirementCenter", "t022"): "成员",
    ("requirementCenter", "t023"): "浏览",
    ("requirementCenter", "t024"): "管理",
    ("requirementCenter", "t025"): "需求",
    ("requirementCenter", "t026"): "项目",
    ("requirementCenter", "t027"): "描述",
    # requesterAccept
    ("requesterAccept", "t017"): "操作",
    ("requesterAccept", "t018"): "通过",
    ("requesterAccept", "t019"): "拒绝",
    ("requesterAccept", "t020"): "退回",
    ("requesterAccept", "t021"): "验收",
    ("requesterAccept", "t022"): "记录",
    ("requesterAccept", "t023"): "审核员",
    ("requesterAccept", "t024"): "原因",
    ("requesterAccept", "t025"): "备注",
    ("requesterAccept", "t026"): "提交时间",
    ("requesterAccept", "t027"): "决策时间",
    ("requesterAccept", "t028"): "按项目筛选",
    ("requesterAccept", "t029"): "导出报告",
    # workflowBuilder
    ("workflowBuilder", "t034"): "工作流",
    ("workflowBuilder", "t035"): "构建器",
    ("workflowBuilder", "t036"): "状态",
    ("workflowBuilder", "t037"): "运行",
    ("workflowBuilder", "t038"): "历史",
}
for k, v in zh_map.items():
    TRANSLATIONS["zh"][k] = v

# === ja (Japanese) ===
ja_map = {
    # capabilityRegistry
    ("capabilityRegistry", "t010"): "能力バージョン",
    ("capabilityRegistry", "t011"): "最終更新",
    ("capabilityRegistry", "t012"): "担当チーム",
    ("capabilityRegistry", "t013"): "入力スキーマ",
    ("capabilityRegistry", "t014"): "出力スキーマ",
    ("capabilityRegistry", "t015"): "タグ",
    ("capabilityRegistry", "t016"): "ドキュメント",
    ("capabilityRegistry", "t017"): "互換性",
    ("capabilityRegistry", "t018"): "新規登録",
    ("capabilityRegistry", "t019"): "詳細表示",
    # collectionCenter
    ("collectionCenter", "t017"): "操作",
    ("collectionCenter", "t018"): "ソース URL",
    ("collectionCenter", "t019"): "最終クロール",
    ("collectionCenter", "t020"): "アイテム数",
    ("collectionCenter", "t021"): "ソースで絞り込み",
    ("collectionCenter", "t022"): "ステータスで絞り込み",
    ("collectionCenter", "t023"): "タイプで絞り込み",
    ("collectionCenter", "t024"): "今すぐ実行",
    ("collectionCenter", "t025"): "スケジュール",
    ("collectionCenter", "t026"): "収集を一時停止",
    ("collectionCenter", "t027"): "収集を再開",
    # delivery
    ("delivery", "t011"): "ステータスで絞り込み",
    ("delivery", "t012"): "配信先",
    ("delivery", "t013"): "フォーマット",
    ("delivery", "t014"): "サイズ",
    ("delivery", "t015"): "最終実行",
    ("delivery", "t016"): "受信者",
    ("delivery", "t017"): "トリガー",
    ("delivery", "t018"): "手動",
    ("delivery", "t019"): "自動",
    ("delivery", "t020"): "説明",
    ("delivery", "t021"): "操作",
    # internalQC
    ("internalQC", "t017"): "操作",
    ("internalQC", "t018"): "レビュアー",
    ("internalQC", "t019"): "問題数",
    ("internalQC", "t020"): "合格率",
    ("internalQC", "t021"): "レビュアーで絞り込み",
    ("internalQC", "t022"): "ステータスで絞り込み",
    ("internalQC", "t023"): "QC を実行",
    ("internalQC", "t024"): "合格にする",
    ("internalQC", "t025"): "不合格にする",
    ("internalQC", "t026"): "説明",
    # packManager
    ("packManager", "t009"): "タイプで絞り込み",
    ("packManager", "t010"): "パックサイズ",
    ("packManager", "t011"): "バージョン",
    ("packManager", "t012"): "作成者",
    ("packManager", "t013"): "ライセンス",
    ("packManager", "t014"): "最終公開",
    ("packManager", "t015"): "ダウンロード数",
    ("packManager", "t016"): "評価",
    ("packManager", "t017"): "操作",
    ("packManager", "t018"): "パックを表示",
    ("packManager", "t019"): "パックを編集",
    ("packManager", "t020"): "公開",
    ("packManager", "t021"): "非公開にする",
    ("packManager", "t022"): "削除",
    ("packManager", "t023"): "説明",
    ("packManager", "t024"): "タグ",
    ("packManager", "t025"): "カテゴリ",
    ("packManager", "t026"): "互換性",
    ("packManager", "t027"): "ソースコード",
    ("packManager", "t028"): "ドキュメント",
    # projectCenter
    ("projectCenter", "t018"): "プロジェクトを作成",
    ("projectCenter", "t019"): "プロジェクトを編集",
    ("projectCenter", "t020"): "編集",
    ("projectCenter", "t021"): "保存",
    ("projectCenter", "t022"): "メンバーを追加",
    ("projectCenter", "t023"): "メンバー",
    ("projectCenter", "t024"): "プロジェクトセンター",
    ("projectCenter", "t025"): "ヘッダー",
    ("projectCenter", "t026"): "プロジェクト",
    ("projectCenter", "t027"): "機能",
    # requirementCenter
    ("requirementCenter", "t018"): "要件を作成",
    ("requirementCenter", "t019"): "要件を編集",
    ("requirementCenter", "t020"): "保存",
    ("requirementCenter", "t021"): "メンバーを追加",
    ("requirementCenter", "t022"): "メンバー",
    ("requirementCenter", "t023"): "閲覧",
    ("requirementCenter", "t024"): "管理",
    ("requirementCenter", "t025"): "要件",
    ("requirementCenter", "t026"): "プロジェクト",
    ("requirementCenter", "t027"): "説明",
    # requesterAccept
    ("requesterAccept", "t017"): "操作",
    ("requesterAccept", "t018"): "承認",
    ("requesterAccept", "t019"): "却下",
    ("requesterAccept", "t020"): "差し戻し",
    ("requesterAccept", "t021"): "受け入れ",
    ("requesterAccept", "t022"): "記録",
    ("requesterAccept", "t023"): "レビュアー",
    ("requesterAccept", "t024"): "理由",
    ("requesterAccept", "t025"): "コメント",
    ("requesterAccept", "t026"): "提出日時",
    ("requesterAccept", "t027"): "決定日時",
    ("requesterAccept", "t028"): "プロジェクトで絞り込み",
    ("requesterAccept", "t029"): "レポートをエクスポート",
    # workflowBuilder
    ("workflowBuilder", "t034"): "ワークフロー",
    ("workflowBuilder", "t035"): "ビルダー",
    ("workflowBuilder", "t036"): "ステータス",
    ("workflowBuilder", "t037"): "実行",
    ("workflowBuilder", "t038"): "履歴",
}
for k, v in ja_map.items():
    TRANSLATIONS["ja"][k] = v

# === ko (Korean) ===
ko_map = {
    # capabilityRegistry
    ("capabilityRegistry", "t010"): "능력 버전",
    ("capabilityRegistry", "t011"): "마지막 업데이트",
    ("capabilityRegistry", "t012"): "담당 팀",
    ("capabilityRegistry", "t013"): "입력 스키마",
    ("capabilityRegistry", "t014"): "출력 스키마",
    ("capabilityRegistry", "t015"): "태그",
    ("capabilityRegistry", "t016"): "문서",
    ("capabilityRegistry", "t017"): "호환성",
    ("capabilityRegistry", "t018"): "새로 등록",
    ("capabilityRegistry", "t019"): "상세 보기",
    # collectionCenter
    ("collectionCenter", "t017"): "작업",
    ("collectionCenter", "t018"): "소스 URL",
    ("collectionCenter", "t019"): "마지막 크롤링",
    ("collectionCenter", "t020"): "항목 수",
    ("collectionCenter", "t021"): "소스로 필터링",
    ("collectionCenter", "t022"): "상태로 필터링",
    ("collectionCenter", "t023"): "유형으로 필터링",
    ("collectionCenter", "t024"): "지금 실행",
    ("collectionCenter", "t025"): "일정",
    ("collectionCenter", "t026"): "수집 일시 중지",
    ("collectionCenter", "t027"): "수집 재개",
    # delivery
    ("delivery", "t011"): "상태로 필터링",
    ("delivery", "t012"): "대상",
    ("delivery", "t013"): "형식",
    ("delivery", "t014"): "크기",
    ("delivery", "t015"): "마지막 실행",
    ("delivery", "t016"): "수신자",
    ("delivery", "t017"): "트리거",
    ("delivery", "t018"): "수동",
    ("delivery", "t019"): "자동",
    ("delivery", "t020"): "설명",
    ("delivery", "t021"): "작업",
    # internalQC
    ("internalQC", "t017"): "작업",
    ("internalQC", "t018"): "검토자",
    ("internalQC", "t019"): "문제 수",
    ("internalQC", "t020"): "합격률",
    ("internalQC", "t021"): "검토자로 필터링",
    ("internalQC", "t022"): "상태로 필터링",
    ("internalQC", "t023"): "QC 실행",
    ("internalQC", "t024"): "합격으로 표시",
    ("internalQC", "t025"): "불합격으로 표시",
    ("internalQC", "t026"): "설명",
    # packManager
    ("packManager", "t009"): "유형으로 필터링",
    ("packManager", "t010"): "패크 크기",
    ("packManager", "t011"): "버전",
    ("packManager", "t012"): "작성자",
    ("packManager", "t013"): "라이선스",
    ("packManager", "t014"): "마지막 게시",
    ("packManager", "t015"): "다운로드",
    ("packManager", "t016"): "평점",
    ("packManager", "t017"): "작업",
    ("packManager", "t018"): "패크 보기",
    ("packManager", "t019"): "패크 편집",
    ("packManager", "t020"): "게시",
    ("packManager", "t021"): "게시 취소",
    ("packManager", "t022"): "삭제",
    ("packManager", "t023"): "설명",
    ("packManager", "t024"): "태그",
    ("packManager", "t025"): "분류",
    ("packManager", "t026"): "호환성",
    ("packManager", "t027"): "소스 코드",
    ("packManager", "t028"): "문서",
    # projectCenter
    ("projectCenter", "t018"): "프로젝트 생성",
    ("projectCenter", "t019"): "프로젝트 편집",
    ("projectCenter", "t020"): "편집",
    ("projectCenter", "t021"): "저장",
    ("projectCenter", "t022"): "구성원 추가",
    ("projectCenter", "t023"): "구성원",
    ("projectCenter", "t024"): "프로젝트 센터",
    ("projectCenter", "t025"): "헤더",
    ("projectCenter", "t026"): "프로젝트",
    ("projectCenter", "t027"): "기능",
    # requirementCenter
    ("requirementCenter", "t018"): "요구사항 생성",
    ("requirementCenter", "t019"): "요구사항 편집",
    ("requirementCenter", "t020"): "저장",
    ("requirementCenter", "t021"): "구성원 추가",
    ("requirementCenter", "t022"): "구성원",
    ("requirementCenter", "t023"): "탐색",
    ("requirementCenter", "t024"): "관리",
    ("requirementCenter", "t025"): "요구사항",
    ("requirementCenter", "t026"): "프로젝트",
    ("requirementCenter", "t027"): "설명",
    # requesterAccept
    ("requesterAccept", "t017"): "작업",
    ("requesterAccept", "t018"): "승인",
    ("requesterAccept", "t019"): "거부",
    ("requesterAccept", "t020"): "반송",
    ("requesterAccept", "t021"): "수락",
    ("requesterAccept", "t022"): "기록",
    ("requesterAccept", "t023"): "검토자",
    ("requesterAccept", "t024"): "사유",
    ("requesterAccept", "t025"): "댓글",
    ("requesterAccept", "t026"): "제출 시간",
    ("requesterAccept", "t027"): "결정 시간",
    ("requesterAccept", "t028"): "프로젝트로 필터링",
    ("requesterAccept", "t029"): "보고서 내보내기",
    # workflowBuilder
    ("workflowBuilder", "t034"): "워크플로",
    ("workflowBuilder", "t035"): "빌더",
    ("workflowBuilder", "t036"): "상태",
    ("workflowBuilder", "t037"): "실행",
    ("workflowBuilder", "t038"): "기록",
}
for k, v in ko_map.items():
    TRANSLATIONS["ko"][k] = v

# === fr (French) ===
fr_map = {
    # capabilityRegistry
    ("capabilityRegistry", "t010"): "Version de capacité",
    ("capabilityRegistry", "t011"): "Dernière mise à jour",
    ("capabilityRegistry", "t012"): "Équipe responsable",
    ("capabilityRegistry", "t013"): "Schéma d'entrée",
    ("capabilityRegistry", "t014"): "Schéma de sortie",
    ("capabilityRegistry", "t015"): "Étiquettes",
    ("capabilityRegistry", "t016"): "Documentation",
    ("capabilityRegistry", "t017"): "Compatibilité",
    ("capabilityRegistry", "t018"): "Enregistrer nouveau",
    ("capabilityRegistry", "t019"): "Voir le détail",
    # collectionCenter
    ("collectionCenter", "t017"): "Actions",
    ("collectionCenter", "t018"): "URL source",
    ("collectionCenter", "t019"): "Dernière exploration",
    ("collectionCenter", "t020"): "Nombre d'éléments",
    ("collectionCenter", "t021"): "Filtrer par source",
    ("collectionCenter", "t022"): "Filtrer par statut",
    ("collectionCenter", "t023"): "Filtrer par type",
    ("collectionCenter", "t024"): "Exécuter maintenant",
    ("collectionCenter", "t025"): "Planifier",
    ("collectionCenter", "t026"): "Suspendre la collecte",
    ("collectionCenter", "t027"): "Reprendre la collecte",
    # delivery
    ("delivery", "t011"): "Filtrer par statut",
    ("delivery", "t012"): "Destination",
    ("delivery", "t013"): "Format",
    ("delivery", "t014"): "Taille",
    ("delivery", "t015"): "Dernière exécution",
    ("delivery", "t016"): "Destinataires",
    ("delivery", "t017"): "Déclencheur",
    ("delivery", "t018"): "Manuel",
    ("delivery", "t019"): "Automatique",
    ("delivery", "t020"): "Description",
    ("delivery", "t021"): "Actions",
    # internalQC
    ("internalQC", "t017"): "Actions",
    ("internalQC", "t018"): "Réviseur",
    ("internalQC", "t019"): "Nombre de problèmes",
    ("internalQC", "t020"): "Taux de réussite",
    ("internalQC", "t021"): "Filtrer par réviseur",
    ("internalQC", "t022"): "Filtrer par statut",
    ("internalQC", "t023"): "Lancer le QC",
    ("internalQC", "t024"): "Marquer comme réussi",
    ("internalQC", "t025"): "Marquer comme échoué",
    ("internalQC", "t026"): "Description",
    # packManager
    ("packManager", "t009"): "Filtrer par type",
    ("packManager", "t010"): "Taille du pack",
    ("packManager", "t011"): "Version",
    ("packManager", "t012"): "Auteur",
    ("packManager", "t013"): "Licence",
    ("packManager", "t014"): "Dernière publication",
    ("packManager", "t015"): "Téléchargements",
    ("packManager", "t016"): "Évaluation",
    ("packManager", "t017"): "Actions",
    ("packManager", "t018"): "Voir le pack",
    ("packManager", "t019"): "Modifier le pack",
    ("packManager", "t020"): "Publier",
    ("packManager", "t021"): "Dépublier",
    ("packManager", "t022"): "Supprimer",
    ("packManager", "t023"): "Description",
    ("packManager", "t024"): "Étiquettes",
    ("packManager", "t025"): "Catégories",
    ("packManager", "t026"): "Compatibilité",
    ("packManager", "t027"): "Code source",
    ("packManager", "t028"): "Documentation",
    # projectCenter
    ("projectCenter", "t018"): "Créer un projet",
    ("projectCenter", "t019"): "Modifier le projet",
    ("projectCenter", "t020"): "Modifier",
    ("projectCenter", "t021"): "Enregistrer",
    ("projectCenter", "t022"): "Ajouter un membre",
    ("projectCenter", "t023"): "Membres",
    ("projectCenter", "t024"): "Centre de projets",
    ("projectCenter", "t025"): "En-tête",
    ("projectCenter", "t026"): "Projet",
    ("projectCenter", "t027"): "Fonctionnalités",
    # requirementCenter
    ("requirementCenter", "t018"): "Créer une exigence",
    ("requirementCenter", "t019"): "Modifier l'exigence",
    ("requirementCenter", "t020"): "Enregistrer",
    ("requirementCenter", "t021"): "Ajouter un membre",
    ("requirementCenter", "t022"): "Membres",
    ("requirementCenter", "t023"): "Parcourir",
    ("requirementCenter", "t024"): "Gérer",
    ("requirementCenter", "t025"): "Exigence",
    ("requirementCenter", "t026"): "Projet",
    ("requirementCenter", "t027"): "Description",
    # requesterAccept
    ("requesterAccept", "t017"): "Actions",
    ("requesterAccept", "t018"): "Approuver",
    ("requesterAccept", "t019"): "Rejeter",
    ("requesterAccept", "t020"): "Renvoyer",
    ("requesterAccept", "t021"): "Acceptation",
    ("requesterAccept", "t022"): "Enregistrements",
    ("requesterAccept", "t023"): "Réviseur",
    ("requesterAccept", "t024"): "Raison",
    ("requesterAccept", "t025"): "Commentaires",
    ("requesterAccept", "t026"): "Soumis le",
    ("requesterAccept", "t027"): "Décision le",
    ("requesterAccept", "t028"): "Filtrer par projet",
    ("requesterAccept", "t029"): "Exporter le rapport",
    # workflowBuilder
    ("workflowBuilder", "t034"): "Flux de travail",
    ("workflowBuilder", "t035"): "Constructeur",
    ("workflowBuilder", "t036"): "Statut",
    ("workflowBuilder", "t037"): "Exécuter",
    ("workflowBuilder", "t038"): "Historique",
}
for k, v in fr_map.items():
    TRANSLATIONS["fr"][k] = v

# === de (German) ===
de_map = {
    # capabilityRegistry
    ("capabilityRegistry", "t010"): "Fähigkeitsversion",
    ("capabilityRegistry", "t011"): "Zuletzt aktualisiert",
    ("capabilityRegistry", "t012"): "Verantwortliches Team",
    ("capabilityRegistry", "t013"): "Eingabeschema",
    ("capabilityRegistry", "t014"): "Ausgabeschema",
    ("capabilityRegistry", "t015"): "Schlagwörter",
    ("capabilityRegistry", "t016"): "Dokumentation",
    ("capabilityRegistry", "t017"): "Kompatibilität",
    ("capabilityRegistry", "t018"): "Neu registrieren",
    ("capabilityRegistry", "t019"): "Details anzeigen",
    # collectionCenter
    ("collectionCenter", "t017"): "Aktionen",
    ("collectionCenter", "t018"): "Quell-URL",
    ("collectionCenter", "t019"): "Letztes Crawling",
    ("collectionCenter", "t020"): "Anzahl der Elemente",
    ("collectionCenter", "t021"): "Nach Quelle filtern",
    ("collectionCenter", "t022"): "Nach Status filtern",
    ("collectionCenter", "t023"): "Nach Typ filtern",
    ("collectionCenter", "t024"): "Jetzt ausführen",
    ("collectionCenter", "t025"): "Zeitplan",
    ("collectionCenter", "t026"): "Sammlung pausieren",
    ("collectionCenter", "t027"): "Sammlung fortsetzen",
    # delivery
    ("delivery", "t011"): "Nach Status filtern",
    ("delivery", "t012"): "Ziel",
    ("delivery", "t013"): "Format",
    ("delivery", "t014"): "Größe",
    ("delivery", "t015"): "Letzte Ausführung",
    ("delivery", "t016"): "Empfänger",
    ("delivery", "t017"): "Auslöser",
    ("delivery", "t018"): "Manuell",
    ("delivery", "t019"): "Automatisch",
    ("delivery", "t020"): "Beschreibung",
    ("delivery", "t021"): "Aktionen",
    # internalQC
    ("internalQC", "t017"): "Aktionen",
    ("internalQC", "t018"): "Prüfer",
    ("internalQC", "t019"): "Anzahl der Probleme",
    ("internalQC", "t020"): "Bestehensquote",
    ("internalQC", "t021"): "Nach Prüfer filtern",
    ("internalQC", "t022"): "Nach Status filtern",
    ("internalQC", "t023"): "QC ausführen",
    ("internalQC", "t024"): "Als bestanden markieren",
    ("internalQC", "t025"): "Als nicht bestanden markieren",
    ("internalQC", "t026"): "Beschreibung",
    # packManager
    ("packManager", "t009"): "Nach Typ filtern",
    ("packManager", "t010"): "Paketgröße",
    ("packManager", "t011"): "Version",
    ("packManager", "t012"): "Autor",
    ("packManager", "t013"): "Lizenz",
    ("packManager", "t014"): "Zuletzt veröffentlicht",
    ("packManager", "t015"): "Downloads",
    ("packManager", "t016"): "Bewertung",
    ("packManager", "t017"): "Aktionen",
    ("packManager", "t018"): "Paket anzeigen",
    ("packManager", "t019"): "Paket bearbeiten",
    ("packManager", "t020"): "Veröffentlichen",
    ("packManager", "t021"): "Zurückziehen",
    ("packManager", "t022"): "Löschen",
    ("packManager", "t023"): "Beschreibung",
    ("packManager", "t024"): "Schlagwörter",
    ("packManager", "t025"): "Kategorien",
    ("packManager", "t026"): "Kompatibilität",
    ("packManager", "t027"): "Quellcode",
    ("packManager", "t028"): "Dokumentation",
    # projectCenter
    ("projectCenter", "t018"): "Projekt erstellen",
    ("projectCenter", "t019"): "Projekt bearbeiten",
    ("projectCenter", "t020"): "Bearbeiten",
    ("projectCenter", "t021"): "Speichern",
    ("projectCenter", "t022"): "Mitglied hinzufügen",
    ("projectCenter", "t023"): "Mitglieder",
    ("projectCenter", "t024"): "Projektzentrum",
    ("projectCenter", "t025"): "Kopfzeile",
    ("projectCenter", "t026"): "Projekt",
    ("projectCenter", "t027"): "Funktionen",
    # requirementCenter
    ("requirementCenter", "t018"): "Anforderung erstellen",
    ("requirementCenter", "t019"): "Anforderung bearbeiten",
    ("requirementCenter", "t020"): "Speichern",
    ("requirementCenter", "t021"): "Mitglied hinzufügen",
    ("requirementCenter", "t022"): "Mitglieder",
    ("requirementCenter", "t023"): "Durchsuchen",
    ("requirementCenter", "t024"): "Verwalten",
    ("requirementCenter", "t025"): "Anforderung",
    ("requirementCenter", "t026"): "Projekt",
    ("requirementCenter", "t027"): "Beschreibung",
    # requesterAccept
    ("requesterAccept", "t017"): "Aktionen",
    ("requesterAccept", "t018"): "Genehmigen",
    ("requesterAccept", "t019"): "Ablehnen",
    ("requesterAccept", "t020"): "Zurücksenden",
    ("requesterAccept", "t021"): "Annahme",
    ("requesterAccept", "t022"): "Aufzeichnungen",
    ("requesterAccept", "t023"): "Prüfer",
    ("requesterAccept", "t024"): "Grund",
    ("requesterAccept", "t025"): "Kommentare",
    ("requesterAccept", "t026"): "Eingereicht am",
    ("requesterAccept", "t027"): "Entschieden am",
    ("requesterAccept", "t028"): "Nach Projekt filtern",
    ("requesterAccept", "t029"): "Bericht exportieren",
    # workflowBuilder
    ("workflowBuilder", "t034"): "Workflow",
    ("workflowBuilder", "t035"): "Builder",
    ("workflowBuilder", "t036"): "Status",
    ("workflowBuilder", "t037"): "Ausführen",
    ("workflowBuilder", "t038"): "Verlauf",
}
for k, v in de_map.items():
    TRANSLATIONS["de"][k] = v

# === es (Spanish) ===
es_map = {
    # capabilityRegistry
    ("capabilityRegistry", "t010"): "Versión de capacidad",
    ("capabilityRegistry", "t011"): "Última actualización",
    ("capabilityRegistry", "t012"): "Equipo responsable",
    ("capabilityRegistry", "t013"): "Esquema de entrada",
    ("capabilityRegistry", "t014"): "Esquema de salida",
    ("capabilityRegistry", "t015"): "Etiquetas",
    ("capabilityRegistry", "t016"): "Documentación",
    ("capabilityRegistry", "t017"): "Compatibilidad",
    ("capabilityRegistry", "t018"): "Registrar nuevo",
    ("capabilityRegistry", "t019"): "Ver detalle",
    # collectionCenter
    ("collectionCenter", "t017"): "Acciones",
    ("collectionCenter", "t018"): "URL de origen",
    ("collectionCenter", "t019"): "Último rastreo",
    ("collectionCenter", "t020"): "Número de elementos",
    ("collectionCenter", "t021"): "Filtrar por origen",
    ("collectionCenter", "t022"): "Filtrar por estado",
    ("collectionCenter", "t023"): "Filtrar por tipo",
    ("collectionCenter", "t024"): "Ejecutar ahora",
    ("collectionCenter", "t025"): "Programar",
    ("collectionCenter", "t026"): "Pausar recolección",
    ("collectionCenter", "t027"): "Reanudar recolección",
    # delivery
    ("delivery", "t011"): "Filtrar por estado",
    ("delivery", "t012"): "Destino",
    ("delivery", "t013"): "Formato",
    ("delivery", "t014"): "Tamaño",
    ("delivery", "t015"): "Última ejecución",
    ("delivery", "t016"): "Destinatarios",
    ("delivery", "t017"): "Disparador",
    ("delivery", "t018"): "Manual",
    ("delivery", "t019"): "Automático",
    ("delivery", "t020"): "Descripción",
    ("delivery", "t021"): "Acciones",
    # internalQC
    ("internalQC", "t017"): "Acciones",
    ("internalQC", "t018"): "Revisor",
    ("internalQC", "t019"): "Número de problemas",
    ("internalQC", "t020"): "Tasa de aprobación",
    ("internalQC", "t021"): "Filtrar por revisor",
    ("internalQC", "t022"): "Filtrar por estado",
    ("internalQC", "t023"): "Ejecutar QC",
    ("internalQC", "t024"): "Marcar como aprobado",
    ("internalQC", "t025"): "Marcar como fallido",
    ("internalQC", "t026"): "Descripción",
    # packManager
    ("packManager", "t009"): "Filtrar por tipo",
    ("packManager", "t010"): "Tamaño del pack",
    ("packManager", "t011"): "Versión",
    ("packManager", "t012"): "Autor",
    ("packManager", "t013"): "Licencia",
    ("packManager", "t014"): "Última publicación",
    ("packManager", "t015"): "Descargas",
    ("packManager", "t016"): "Calificación",
    ("packManager", "t017"): "Acciones",
    ("packManager", "t018"): "Ver pack",
    ("packManager", "t019"): "Editar pack",
    ("packManager", "t020"): "Publicar",
    ("packManager", "t021"): "Despublicar",
    ("packManager", "t022"): "Eliminar",
    ("packManager", "t023"): "Descripción",
    ("packManager", "t024"): "Etiquetas",
    ("packManager", "t025"): "Categorías",
    ("packManager", "t026"): "Compatibilidad",
    ("packManager", "t027"): "Código fuente",
    ("packManager", "t028"): "Documentación",
    # projectCenter
    ("projectCenter", "t018"): "Crear proyecto",
    ("projectCenter", "t019"): "Editar proyecto",
    ("projectCenter", "t020"): "Editar",
    ("projectCenter", "t021"): "Guardar",
    ("projectCenter", "t022"): "Agregar miembro",
    ("projectCenter", "t023"): "Miembros",
    ("projectCenter", "t024"): "Centro de proyectos",
    ("projectCenter", "t025"): "Encabezado",
    ("projectCenter", "t026"): "Proyecto",
    ("projectCenter", "t027"): "Características",
    # requirementCenter
    ("requirementCenter", "t018"): "Crear requisito",
    ("requirementCenter", "t019"): "Editar requisito",
    ("requirementCenter", "t020"): "Guardar",
    ("requirementCenter", "t021"): "Agregar miembro",
    ("requirementCenter", "t022"): "Miembros",
    ("requirementCenter", "t023"): "Explorar",
    ("requirementCenter", "t024"): "Gestionar",
    ("requirementCenter", "t025"): "Requisito",
    ("requirementCenter", "t026"): "Proyecto",
    ("requirementCenter", "t027"): "Descripción",
    # requesterAccept
    ("requesterAccept", "t017"): "Acciones",
    ("requesterAccept", "t018"): "Aprobar",
    ("requesterAccept", "t019"): "Rechazar",
    ("requesterAccept", "t020"): "Devolver",
    ("requesterAccept", "t021"): "Aceptación",
    ("requesterAccept", "t022"): "Registros",
    ("requesterAccept", "t023"): "Revisor",
    ("requesterAccept", "t024"): "Razón",
    ("requesterAccept", "t025"): "Comentarios",
    ("requesterAccept", "t026"): "Enviado el",
    ("requesterAccept", "t027"): "Decidido el",
    ("requesterAccept", "t028"): "Filtrar por proyecto",
    ("requesterAccept", "t029"): "Exportar informe",
    # workflowBuilder
    ("workflowBuilder", "t034"): "Flujo de trabajo",
    ("workflowBuilder", "t035"): "Constructor",
    ("workflowBuilder", "t036"): "Estado",
    ("workflowBuilder", "t037"): "Ejecutar",
    ("workflowBuilder", "t038"): "Historial",
}
for k, v in es_map.items():
    TRANSLATIONS["es"][k] = v

# === ru (Russian) ===
ru_map = {
    # capabilityRegistry
    ("capabilityRegistry", "t010"): "Версия возможности",
    ("capabilityRegistry", "t011"): "Последнее обновление",
    ("capabilityRegistry", "t012"): "Ответственная команда",
    ("capabilityRegistry", "t013"): "Схема ввода",
    ("capabilityRegistry", "t014"): "Схема вывода",
    ("capabilityRegistry", "t015"): "Метки",
    ("capabilityRegistry", "t016"): "Документация",
    ("capabilityRegistry", "t017"): "Совместимость",
    ("capabilityRegistry", "t018"): "Зарегистрировать новую",
    ("capabilityRegistry", "t019"): "Просмотр деталей",
    # collectionCenter
    ("collectionCenter", "t017"): "Действия",
    ("collectionCenter", "t018"): "URL источника",
    ("collectionCenter", "t019"): "Последний обход",
    ("collectionCenter", "t020"): "Количество элементов",
    ("collectionCenter", "t021"): "Фильтр по источнику",
    ("collectionCenter", "t022"): "Фильтр по статусу",
    ("collectionCenter", "t023"): "Фильтр по типу",
    ("collectionCenter", "t024"): "Запустить сейчас",
    ("collectionCenter", "t025"): "Расписание",
    ("collectionCenter", "t026"): "Приостановить сбор",
    ("collectionCenter", "t027"): "Возобновить сбор",
    # delivery
    ("delivery", "t011"): "Фильтр по статусу",
    ("delivery", "t012"): "Назначение",
    ("delivery", "t013"): "Формат",
    ("delivery", "t014"): "Размер",
    ("delivery", "t015"): "Последний запуск",
    ("delivery", "t016"): "Получатели",
    ("delivery", "t017"): "Триггер",
    ("delivery", "t018"): "Вручную",
    ("delivery", "t019"): "Автоматически",
    ("delivery", "t020"): "Описание",
    ("delivery", "t021"): "Действия",
    # internalQC
    ("internalQC", "t017"): "Действия",
    ("internalQC", "t018"): "Проверяющий",
    ("internalQC", "t019"): "Количество проблем",
    ("internalQC", "t020"): "Процент прохождения",
    ("internalQC", "t021"): "Фильтр по проверяющему",
    ("internalQC", "t022"): "Фильтр по статусу",
    ("internalQC", "t023"): "Запустить QC",
    ("internalQC", "t024"): "Отметить как пройденное",
    ("internalQC", "t025"): "Отметить как непройденное",
    ("internalQC", "t026"): "Описание",
    # packManager
    ("packManager", "t009"): "Фильтр по типу",
    ("packManager", "t010"): "Размер пакета",
    ("packManager", "t011"): "Версия",
    ("packManager", "t012"): "Автор",
    ("packManager", "t013"): "Лицензия",
    ("packManager", "t014"): "Последняя публикация",
    ("packManager", "t015"): "Загрузки",
    ("packManager", "t016"): "Рейтинг",
    ("packManager", "t017"): "Действия",
    ("packManager", "t018"): "Просмотр пакета",
    ("packManager", "t019"): "Изменить пакет",
    ("packManager", "t020"): "Опубликовать",
    ("packManager", "t021"): "Снять с публикации",
    ("packManager", "t022"): "Удалить",
    ("packManager", "t023"): "Описание",
    ("packManager", "t024"): "Метки",
    ("packManager", "t025"): "Категории",
    ("packManager", "t026"): "Совместимость",
    ("packManager", "t027"): "Исходный код",
    ("packManager", "t028"): "Документация",
    # projectCenter
    ("projectCenter", "t018"): "Создать проект",
    ("projectCenter", "t019"): "Изменить проект",
    ("projectCenter", "t020"): "Изменить",
    ("projectCenter", "t021"): "Сохранить",
    ("projectCenter", "t022"): "Добавить участника",
    ("projectCenter", "t023"): "Участники",
    ("projectCenter", "t024"): "Центр проектов",
    ("projectCenter", "t025"): "Заголовок",
    ("projectCenter", "t026"): "Проект",
    ("projectCenter", "t027"): "Функции",
    # requirementCenter
    ("requirementCenter", "t018"): "Создать требование",
    ("requirementCenter", "t019"): "Изменить требование",
    ("requirementCenter", "t020"): "Сохранить",
    ("requirementCenter", "t021"): "Добавить участника",
    ("requirementCenter", "t022"): "Участники",
    ("requirementCenter", "t023"): "Просмотр",
    ("requirementCenter", "t024"): "Управление",
    ("requirementCenter", "t025"): "Требование",
    ("requirementCenter", "t026"): "Проект",
    ("requirementCenter", "t027"): "Описание",
    # requesterAccept
    ("requesterAccept", "t017"): "Действия",
    ("requesterAccept", "t018"): "Одобрить",
    ("requesterAccept", "t019"): "Отклонить",
    ("requesterAccept", "t020"): "Вернуть",
    ("requesterAccept", "t021"): "Приёмка",
    ("requesterAccept", "t022"): "Записи",
    ("requesterAccept", "t023"): "Проверяющий",
    ("requesterAccept", "t024"): "Причина",
    ("requesterAccept", "t025"): "Комментарии",
    ("requesterAccept", "t026"): "Отправлено",
    ("requesterAccept", "t027"): "Решено",
    ("requesterAccept", "t028"): "Фильтр по проекту",
    ("requesterAccept", "t029"): "Экспорт отчёта",
    # workflowBuilder
    ("workflowBuilder", "t034"): "Рабочий процесс",
    ("workflowBuilder", "t035"): "Конструктор",
    ("workflowBuilder", "t036"): "Статус",
    ("workflowBuilder", "t037"): "Запустить",
    ("workflowBuilder", "t038"): "История",
}
for k, v in ru_map.items():
    TRANSLATIONS["ru"][k] = v

# === ar (Arabic) ===
ar_map = {
    # capabilityRegistry
    ("capabilityRegistry", "t010"): "إصدار القدرة",
    ("capabilityRegistry", "t011"): "آخر تحديث",
    ("capabilityRegistry", "t012"): "الفريق المسؤول",
    ("capabilityRegistry", "t013"): "مخطط الإدخال",
    ("capabilityRegistry", "t014"): "مخطط الإخراج",
    ("capabilityRegistry", "t015"): "الوسوم",
    ("capabilityRegistry", "t016"): "التوثيق",
    ("capabilityRegistry", "t017"): "التوافق",
    ("capabilityRegistry", "t018"): "تسجيل جديد",
    ("capabilityRegistry", "t019"): "عرض التفاصيل",
    # collectionCenter
    ("collectionCenter", "t017"): "الإجراءات",
    ("collectionCenter", "t018"): "رابط المصدر",
    ("collectionCenter", "t019"): "آخر جلب",
    ("collectionCenter", "t020"): "عدد العناصر",
    ("collectionCenter", "t021"): "تصفية حسب المصدر",
    ("collectionCenter", "t022"): "تصفية حسب الحالة",
    ("collectionCenter", "t023"): "تصفية حسب النوع",
    ("collectionCenter", "t024"): "تشغيل الآن",
    ("collectionCenter", "t025"): "الجدولة",
    ("collectionCenter", "t026"): "إيقاف الجمع",
    ("collectionCenter", "t027"): "استئناف الجمع",
    # delivery
    ("delivery", "t011"): "تصفية حسب الحالة",
    ("delivery", "t012"): "الوجهة",
    ("delivery", "t013"): "التنسيق",
    ("delivery", "t014"): "الحجم",
    ("delivery", "t015"): "آخر تشغيل",
    ("delivery", "t016"): "المستلمون",
    ("delivery", "t017"): "المُحفِّز",
    ("delivery", "t018"): "يدوي",
    ("delivery", "t019"): "تلقائي",
    ("delivery", "t020"): "الوصف",
    ("delivery", "t021"): "الإجراءات",
    # internalQC
    ("internalQC", "t017"): "الإجراءات",
    ("internalQC", "t018"): "المراجع",
    ("internalQC", "t019"): "عدد المشاكل",
    ("internalQC", "t020"): "نسبة النجاح",
    ("internalQC", "t021"): "تصفية حسب المراجع",
    ("internalQC", "t022"): "تصفية حسب الحالة",
    ("internalQC", "t023"): "تشغيل فحص الجودة",
    ("internalQC", "t024"): "وضع علامة نجاح",
    ("internalQC", "t025"): "وضع علامة فشل",
    ("internalQC", "t026"): "الوصف",
    # packManager
    ("packManager", "t009"): "تصفية حسب النوع",
    ("packManager", "t010"): "حجم الحزمة",
    ("packManager", "t011"): "الإصدار",
    ("packManager", "t012"): "المؤلف",
    ("packManager", "t013"): "الترخيص",
    ("packManager", "t014"): "آخر نشر",
    ("packManager", "t015"): "التنزيلات",
    ("packManager", "t016"): "التقييم",
    ("packManager", "t017"): "الإجراءات",
    ("packManager", "t018"): "عرض الحزمة",
    ("packManager", "t019"): "تعديل الحزمة",
    ("packManager", "t020"): "نشر",
    ("packManager", "t021"): "إلغاء النشر",
    ("packManager", "t022"): "حذف",
    ("packManager", "t023"): "الوصف",
    ("packManager", "t024"): "الوسوم",
    ("packManager", "t025"): "الفئات",
    ("packManager", "t026"): "التوافق",
    ("packManager", "t027"): "الكود المصدري",
    ("packManager", "t028"): "التوثيق",
    # projectCenter
    ("projectCenter", "t018"): "إنشاء مشروع",
    ("projectCenter", "t019"): "تعديل المشروع",
    ("projectCenter", "t020"): "تعديل",
    ("projectCenter", "t021"): "حفظ",
    ("projectCenter", "t022"): "إضافة عضو",
    ("projectCenter", "t023"): "الأعضاء",
    ("projectCenter", "t024"): "مركز المشاريع",
    ("projectCenter", "t025"): "الترويسة",
    ("projectCenter", "t026"): "المشروع",
    ("projectCenter", "t027"): "الميزات",
    # requirementCenter
    ("requirementCenter", "t018"): "إنشاء متطلب",
    ("requirementCenter", "t019"): "تعديل المتطلب",
    ("requirementCenter", "t020"): "حفظ",
    ("requirementCenter", "t021"): "إضافة عضو",
    ("requirementCenter", "t022"): "الأعضاء",
    ("requirementCenter", "t023"): "تصفح",
    ("requirementCenter", "t024"): "إدارة",
    ("requirementCenter", "t025"): "المتطلب",
    ("requirementCenter", "t026"): "المشروع",
    ("requirementCenter", "t027"): "الوصف",
    # requesterAccept
    ("requesterAccept", "t017"): "الإجراءات",
    ("requesterAccept", "t018"): "موافقة",
    ("requesterAccept", "t019"): "رفض",
    ("requesterAccept", "t020"): "إعادة",
    ("requesterAccept", "t021"): "القبول",
    ("requesterAccept", "t022"): "السجلات",
    ("requesterAccept", "t023"): "المراجع",
    ("requesterAccept", "t024"): "السبب",
    ("requesterAccept", "t025"): "التعليقات",
    ("requesterAccept", "t026"): "وقت التقديم",
    ("requesterAccept", "t027"): "وقت القرار",
    ("requesterAccept", "t028"): "تصفية حسب المشروع",
    ("requesterAccept", "t029"): "تصدير التقرير",
    # workflowBuilder
    ("workflowBuilder", "t034"): "سير العمل",
    ("workflowBuilder", "t035"): "المنشئ",
    ("workflowBuilder", "t036"): "الحالة",
    ("workflowBuilder", "t037"): "تشغيل",
    ("workflowBuilder", "t038"): "السجل",
}
for k, v in ar_map.items():
    TRANSLATIONS["ar"][k] = v

# === pt (Portuguese) ===
pt_map = {
    # capabilityRegistry
    ("capabilityRegistry", "t010"): "Versão da capacidade",
    ("capabilityRegistry", "t011"): "Última atualização",
    ("capabilityRegistry", "t012"): "Equipe responsável",
    ("capabilityRegistry", "t013"): "Esquema de entrada",
    ("capabilityRegistry", "t014"): "Esquema de saída",
    ("capabilityRegistry", "t015"): "Etiquetas",
    ("capabilityRegistry", "t016"): "Documentação",
    ("capabilityRegistry", "t017"): "Compatibilidade",
    ("capabilityRegistry", "t018"): "Registrar novo",
    ("capabilityRegistry", "t019"): "Ver detalhes",
    # collectionCenter
    ("collectionCenter", "t017"): "Ações",
    ("collectionCenter", "t018"): "URL de origem",
    ("collectionCenter", "t019"): "Última coleta",
    ("collectionCenter", "t020"): "Número de itens",
    ("collectionCenter", "t021"): "Filtrar por origem",
    ("collectionCenter", "t022"): "Filtrar por estado",
    ("collectionCenter", "t023"): "Filtrar por tipo",
    ("collectionCenter", "t024"): "Executar agora",
    ("collectionCenter", "t025"): "Agendar",
    ("collectionCenter", "t026"): "Pausar coleta",
    ("collectionCenter", "t027"): "Retomar coleta",
    # delivery
    ("delivery", "t011"): "Filtrar por estado",
    ("delivery", "t012"): "Destino",
    ("delivery", "t013"): "Formato",
    ("delivery", "t014"): "Tamanho",
    ("delivery", "t015"): "Última execução",
    ("delivery", "t016"): "Destinatários",
    ("delivery", "t017"): "Gatilho",
    ("delivery", "t018"): "Manual",
    ("delivery", "t019"): "Automático",
    ("delivery", "t020"): "Descrição",
    ("delivery", "t021"): "Ações",
    # internalQC
    ("internalQC", "t017"): "Ações",
    ("internalQC", "t018"): "Revisor",
    ("internalQC", "t019"): "Número de problemas",
    ("internalQC", "t020"): "Taxa de aprovação",
    ("internalQC", "t021"): "Filtrar por revisor",
    ("internalQC", "t022"): "Filtrar por estado",
    ("internalQC", "t023"): "Executar QC",
    ("internalQC", "t024"): "Marcar como aprovado",
    ("internalQC", "t025"): "Marcar como reprovado",
    ("internalQC", "t026"): "Descrição",
    # packManager
    ("packManager", "t009"): "Filtrar por tipo",
    ("packManager", "t010"): "Tamanho do pack",
    ("packManager", "t011"): "Versão",
    ("packManager", "t012"): "Autor",
    ("packManager", "t013"): "Licença",
    ("packManager", "t014"): "Última publicação",
    ("packManager", "t015"): "Downloads",
    ("packManager", "t016"): "Avaliação",
    ("packManager", "t017"): "Ações",
    ("packManager", "t018"): "Ver pack",
    ("packManager", "t019"): "Editar pack",
    ("packManager", "t020"): "Publicar",
    ("packManager", "t021"): "Despublicar",
    ("packManager", "t022"): "Excluir",
    ("packManager", "t023"): "Descrição",
    ("packManager", "t024"): "Etiquetas",
    ("packManager", "t025"): "Categorias",
    ("packManager", "t026"): "Compatibilidade",
    ("packManager", "t027"): "Código-fonte",
    ("packManager", "t028"): "Documentação",
    # projectCenter
    ("projectCenter", "t018"): "Criar projeto",
    ("projectCenter", "t019"): "Editar projeto",
    ("projectCenter", "t020"): "Editar",
    ("projectCenter", "t021"): "Salvar",
    ("projectCenter", "t022"): "Adicionar membro",
    ("projectCenter", "t023"): "Membros",
    ("projectCenter", "t024"): "Centro de projetos",
    ("projectCenter", "t025"): "Cabeçalho",
    ("projectCenter", "t026"): "Projeto",
    ("projectCenter", "t027"): "Recursos",
    # requirementCenter
    ("requirementCenter", "t018"): "Criar requisito",
    ("requirementCenter", "t019"): "Editar requisito",
    ("requirementCenter", "t020"): "Salvar",
    ("requirementCenter", "t021"): "Adicionar membro",
    ("requirementCenter", "t022"): "Membros",
    ("requirementCenter", "t023"): "Navegar",
    ("requirementCenter", "t024"): "Gerenciar",
    ("requirementCenter", "t025"): "Requisito",
    ("requirementCenter", "t026"): "Projeto",
    ("requirementCenter", "t027"): "Descrição",
    # requesterAccept
    ("requesterAccept", "t017"): "Ações",
    ("requesterAccept", "t018"): "Aprovar",
    ("requesterAccept", "t019"): "Rejeitar",
    ("requesterAccept", "t020"): "Devolver",
    ("requesterAccept", "t021"): "Aceitação",
    ("requesterAccept", "t022"): "Registros",
    ("requesterAccept", "t023"): "Revisor",
    ("requesterAccept", "t024"): "Motivo",
    ("requesterAccept", "t025"): "Comentários",
    ("requesterAccept", "t026"): "Enviado em",
    ("requesterAccept", "t027"): "Decidido em",
    ("requesterAccept", "t028"): "Filtrar por projeto",
    ("requesterAccept", "t029"): "Exportar relatório",
    # workflowBuilder
    ("workflowBuilder", "t034"): "Fluxo de trabalho",
    ("workflowBuilder", "t035"): "Construtor",
    ("workflowBuilder", "t036"): "Estado",
    ("workflowBuilder", "t037"): "Executar",
    ("workflowBuilder", "t038"): "Histórico",
}
for k, v in pt_map.items():
    TRANSLATIONS["pt"][k] = v

# Verify all 100 keys have a translation in every language
for lname in [lname for _, lname in LOCALES]:
    assert len(TRANSLATIONS[lname]) == 100, f"{lname} has {len(TRANSLATIONS[lname])} translations, expected 100"

print(f"All {len(NEW_KEYS)} keys have translations in all {len(LOCALES)} languages.")

# === Update each locale file ===
# Strategy: read the file, find the namespace object (e.g. `capabilityRegistry: { ... }`),
# add the new key-value pairs at the end of that object (before the closing `}`).
# The format is `key: 'value'` separated by commas.

def escape_for_ts(s):
    # Escape single quotes and backslashes for TypeScript string literal
    return s.replace("\\", "\\\\").replace("'", "\\'")

def insert_keys_into_locale(file_path, lname, is_en):
    """Insert new keys into the locale file. For non-en, add // TODO comment after each."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Group new keys by namespace
    by_ns = {}
    for ns, key, _en_text in NEW_KEYS:
        by_ns.setdefault(ns, []).append(key)
    
    # For each namespace, find the object and insert new keys before the closing `}`
    # Pattern: namespace: { ... existing keys ... }
    for ns, keys in by_ns.items():
        # Build the new entries
        new_entries = []
        for key in keys:
            text = TRANSLATIONS[lname][(ns, key)]
            escaped = escape_for_ts(text)
            if is_en:
                new_entries.append(f"    {key}: '{escaped}'")
            else:
                # Add TODO comment after the value for non-en
                new_entries.append(f"    {key}: '{escaped}' // TODO: native review")
        
        new_block = ",\n".join(new_entries)
        
        # Find the namespace object - use a regex to match the entire `namespace: { ... }` block
        # We need to find the start and the matching close brace
        # Pattern: \n  namespace: {\n  ... \n  } (with proper indentation)
        # We'll use a state machine to find the matching brace
        ns_pattern = re.compile(rf'(\n\s*{re.escape(ns)}:\s*\{{)')
        m = ns_pattern.search(content)
        if not m:
            print(f"  WARNING: namespace '{ns}' not found in {os.path.basename(file_path)}")
            continue
        
        # Find the matching closing brace
        start = m.end()  # position right after `{`
        depth = 1
        pos = start
        in_string = False
        string_char = None
        while pos < len(content) and depth > 0:
            ch = content[pos]
            if in_string:
                if ch == '\\' and pos + 1 < len(content):
                    pos += 2
                    continue
                if ch == string_char:
                    in_string = False
            else:
                if ch == "'" or ch == '"' or ch == '`':
                    in_string = True
                    string_char = ch
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
            pos += 1
        
        # pos is now the position right after the matching `}`
        # We want to insert the new keys just before the `}`
        insert_pos = pos - 1  # position of the `}`
        
        # Check the character just before insert_pos - is it a comma?
        # If not, we need to add a comma
        # Walk back to find non-whitespace
        j = insert_pos - 1
        while j >= 0 and content[j] in ' \t\n':
            j -= 1
        if j >= 0 and content[j] != ',':
            # Need to add comma after the last existing entry
            new_content = (
                content[:insert_pos] +
                ',\n' + new_block +
                content[insert_pos:]
            )
        else:
            # Already have a trailing comma; just insert after it
            # Find the position of the comma
            comma_pos = j + 1  # j is at the comma
            # Insert after the comma
            new_content = (
                content[:comma_pos + 1] +
                '\n' + new_block +
                content[comma_pos + 1:]
            )
        
        content = new_content
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"  Updated {os.path.basename(file_path)} ({lname}): added {len(NEW_KEYS)} keys")


# Main: process each locale
for fname, lname in LOCALES:
    path = os.path.join(LOCALES_DIR, fname)
    print(f"\nProcessing {fname} ({lname})...")
    is_en = (lname == "en")
    insert_keys_into_locale(path, lname, is_en)

print(f"\nDone. {len(NEW_KEYS)} new keys added to {len(LOCALES)} locale files.")
