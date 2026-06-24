# -*- coding: utf-8 -*-
"""
NanoBot Factory - Experts System 432 experts
Technical, Domain, and Industry experts

@author MiniMax Agent
@date 2026-04-14
"""

from typing import List, Dict
from .agent_registry import AgentRegistry, AgentProfile, AgentType, get_agent_registry
import logging

logger = logging.getLogger(__name__)


def create_technical_experts(registry: AgentRegistry) -> List[AgentProfile]:
    """Create 180 Technical experts"""
    experts = []
    
    # Programming Languages (30)
    languages = [
        ("python", "Python Expert", ["Python", "async", "performance"]),
        ("javascript", "JavaScript Expert", ["JavaScript", "ES6+", "async"]),
        ("typescript", "TypeScript Expert", ["TypeScript", "type_system", "compilation"]),
        ("java", "Java Expert", ["Java", "JVM", "concurrency"]),
        ("go", "Go Expert", ["Go", "concurrency", "microservices"]),
        ("rust", "Rust Expert", ["Rust", "memory_safety", "performance"]),
        ("cpp", "C++ Expert", ["C++", "STL", "performance"]),
        ("csharp", "C# Expert", ["C#", ".NET", "async"]),
        ("swift", "Swift Expert", ["Swift", "iOS", "syntax"]),
        ("kotlin", "Kotlin Expert", ["Kotlin", "JVM", "Android"]),
    ]
    
    for i, (lang_id, title, skills) in enumerate(languages):
        for j in range(3):
            experts.append(AgentProfile(
                agent_id=f"tech_lang_{lang_id}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.TECHNICAL_EXPERT,
                personality={"specialty": skills[0], "style": "technical_deep"},
                capabilities=["programming", "code_review", "optimization", "mentoring"],
                skills=skills + ["best_practices", "design_patterns"],
                tools=["ide", "debugger", "profiler"],
                system_prompt=f"You are a senior {title}."
            ))
    
    # Frontend (20)
    frontend = [
        ("react", "React Expert", ["React", "hooks", "state"]),
        ("vue", "Vue Expert", ["Vue", "composition", "vuex"]),
        ("angular", "Angular Expert", ["Angular", "RxJS", "NgModules"]),
        ("css", "CSS Expert", ["CSS", "flexbox", "grid"]),
        ("performance", "Performance Expert", ["optimization", "lazy_loading", "caching"]),
    ]
    
    for i, (fe_id, title, skills) in enumerate(frontend):
        for j in range(4):
            experts.append(AgentProfile(
                agent_id=f"tech_fe_{fe_id}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.TECHNICAL_EXPERT,
                personality={"specialty": skills[0], "style": "frontend_master"},
                capabilities=["frontend_dev", "performance", "ui_ux"],
                skills=skills + ["responsive", "accessibility"],
                tools=["devtools", "lighthouse", "webpack"],
                system_prompt=f"You are a {title}."
            ))
    
    # Backend (25)
    backend = [
        ("microservices", "Microservices Expert", ["microservices", "api", "scaling"]),
        ("database", "Database Expert", ["sql", "nosql", "optimization"]),
        ("cache", "Cache Expert", ["redis", "memcached", "caching"]),
        ("message_queue", "MQ Expert", ["kafka", "rabbitmq", "messaging"]),
        ("api", "API Expert", ["rest", "graphql", "api_design"]),
    ]
    
    for i, (be_id, title, skills) in enumerate(backend):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"tech_be_{be_id}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.TECHNICAL_EXPERT,
                personality={"specialty": skills[0], "style": "backend_master"},
                capabilities=["backend_dev", "api_design", "scaling"],
                skills=skills + ["security", "monitoring"],
                tools=["postman", "swagger", "docker"],
                system_prompt=f"You are a {title}."
            ))
    
    # AI/ML (25)
    ai_ml = [
        ("deep_learning", "Deep Learning Expert", ["neural_nets", "frameworks", "training"]),
        ("nlp", "NLP Expert", ["transformers", "text_processing", "llm"]),
        ("cv", "CV Expert", ["computer_vision", "object_detection", "segmentation"]),
        ("rl", "RL Expert", ["reinforcement_learning", "agents", "games"]),
        ("mlops", "MLOps Expert", ["deployment", "monitoring", "pipelines"]),
    ]
    
    for i, (ai_id, title, skills) in enumerate(ai_ml):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"tech_ai_{ai_id}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.TECHNICAL_EXPERT,
                personality={"specialty": skills[0], "style": "ai_researcher"},
                capabilities=["ml_dev", "research", "optimization"],
                skills=skills + ["math", "statistics"],
                tools=["tensorflow", "pytorch", "jupyter"],
                system_prompt=f"You are a {title}."
            ))
    
    # DevOps (20)
    devops = [
        ("k8s", "Kubernetes Expert", ["k8s", "containers", "orchestration"]),
        ("docker", "Docker Expert", ["docker", "containers", "registry"]),
        ("cicd", "CI/CD Expert", ["jenkins", "github_actions", "pipelines"]),
        ("monitoring", "Monitoring Expert", ["prometheus", "grafana", "logging"]),
    ]
    
    for i, (do_id, title, skills) in enumerate(devops):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"tech_do_{do_id}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.TECHNICAL_EXPERT,
                personality={"specialty": skills[0], "style": "devops_master"},
                capabilities=["devops", "automation", "infrastructure"],
                skills=skills + ["scripting", "cloud"],
                tools=["terraform", "ansible", "gitlab"],
                system_prompt=f"You are a {title}."
            ))
    
    # Security (20)
    security = [
        ("pentest", "Penetration Expert", ["pentest", "vulnerabilities", "exploits"]),
        ("code_audit", "Code Audit Expert", ["security_review", "owasp", "best_practices"]),
        ("compliance", "Compliance Expert", ["security_compliance", "gdpr", "sox"]),
    ]
    
    for i, (sec_id, title, skills) in enumerate(security):
        for j in range(7) if i < 2 else range(6):
            experts.append(AgentProfile(
                agent_id=f"tech_sec_{sec_id}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.TECHNICAL_EXPERT,
                personality={"specialty": skills[0], "style": "security_expert"},
                capabilities=["security", "testing", "consulting"],
                skills=skills + ["risk_assessment", "incident_response"],
                tools=["burp", "owasp_zap", "nessus"],
                system_prompt=f"You are a {title}."
            ))
    
    # Data Engineering (20)
    data_eng = [
        ("warehouse", "Data Warehouse Expert", ["data_warehouse", "etl", "modeling"]),
        ("etl", "ETL Expert", ["etl", "transformation", "pipelines"]),
        ("streaming", "Streaming Expert", ["kafka", "flink", "real_time"]),
        ("bi", "BI Expert", ["bi", "visualization", "dashboards"]),
    ]
    
    for i, (de_id, title, skills) in enumerate(data_eng):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"tech_data_{de_id}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.TECHNICAL_EXPERT,
                personality={"specialty": skills[0], "style": "data_engineer"},
                capabilities=["data_engineering", "pipelines", "analytics"],
                skills=skills + ["sql", "python"],
                tools=["spark", "airflow", "dbt"],
                system_prompt=f"You are a {title}."
            ))
    
    # Mobile (20)
    mobile = [
        ("ios", "iOS Expert", ["swift", "ios", "xcode"]),
        ("android", "Android Expert", ["kotlin", "android", "gradle"]),
        ("cross_platform", "Cross Platform Expert", ["flutter", "react_native", "multi_platform"]),
    ]
    
    for i, (mob_id, title, skills) in enumerate(mobile):
        for j in range(7) if i < 2 else range(6):
            experts.append(AgentProfile(
                agent_id=f"tech_mobile_{mob_id}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.TECHNICAL_EXPERT,
                personality={"specialty": skills[0], "style": "mobile_expert"},
                capabilities=["mobile_dev", "performance", "ui"],
                skills=skills + ["testing", "deployment"],
                tools=["xcode", "android_studio", "flutter"],
                system_prompt=f"You are a {title}."
            ))

    for expert in experts:
        registry.register(expert)
    
    logger.info(f"Created {len(experts)} technical experts")
    return experts


def create_domain_experts(registry: AgentRegistry) -> List[AgentProfile]:
    """Create 162 Domain experts"""
    experts = []
    
    # Product Management (20)
    product = [
        ("strategy", "Product Strategy Expert"),
        ("design", "Product Design Expert"),
        ("data", "Data Product Expert"),
        ("ai", "AI Product Expert"),
    ]
    
    for i, (pid, title) in enumerate(product):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"domain_prod_{pid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.DOMAIN_EXPERT,
                personality={"specialty": title, "style": "product_thinker"},
                capabilities=["product_planning", "requirement", "data_analysis"],
                skills=["user_research", "competitive_analysis", "roadmap"],
                tools=["axure", "figma", "jira", "mixpanel"],
                system_prompt=f"You are a {title}."
            ))
    
    # Project Management (20)
    pm = [
        ("agile", "Agile Expert"),
        ("waterfall", "Waterfall Expert"),
        ("hybrid", "Hybrid Expert"),
        ("program", "Program Manager"),
    ]
    
    for i, (pmid, title) in enumerate(pm):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"domain_pm_{pmid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.DOMAIN_EXPERT,
                personality={"specialty": title, "style": "project_leader"},
                capabilities=["project_planning", "team_management", "risk_control"],
                skills=["scrum", "kanban", "stakeholder_management"],
                tools=["jira", "confluence", "ms_project"],
                system_prompt=f"You are a {title}."
            ))
    
    # UX Design (20)
    ux = [
        ("research", "UX Researcher"),
        ("interaction", "Interaction Designer"),
        ("visual", "Visual Designer"),
        ("usability", "Usability Expert"),
    ]
    
    for i, (uxid, title) in enumerate(ux):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"domain_ux_{uxid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.DOMAIN_EXPERT,
                personality={"specialty": title, "style": "user_centered"},
                capabilities=["ux_design", "user_research", "prototyping"],
                skills=["user_testing", "journey_mapping", "personas"],
                tools=["figma", "miro", "userTesting"],
                system_prompt=f"You are a {title}."
            ))
    
    # Operations Marketing (22)
    ops_mkt = [
        ("growth", "Growth Expert"),
        ("content", "Content Expert"),
        ("social", "Social Media Expert"),
        ("seo", "SEO Expert"),
        ("sem", "SEM Expert"),
    ]
    
    for i, (omid, title) in enumerate(ops_mkt):
        for j in range(5) if i < 3 else range(3):
            experts.append(AgentProfile(
                agent_id=f"domain_ops_{omid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.DOMAIN_EXPERT,
                personality={"specialty": title, "style": "growth_minded"},
                capabilities=["growth_hacking", "marketing", "analytics"],
                skills=["a_b_testing", "funnel_optimization", "campaigns"],
                tools=["google_analytics", "mixpanel", "hubspot"],
                system_prompt=f"You are a {title}."
            ))
    
    # Finance (20)
    finance = [
        ("accounting", "Accounting Expert"),
        ("fp_a", "FP&A Expert"),
        ("treasury", "Treasury Expert"),
        ("audit", "Audit Expert"),
    ]
    
    for i, (fid, title) in enumerate(finance):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"domain_fin_{fid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.DOMAIN_EXPERT,
                personality={"specialty": title, "style": "detail_oriented"},
                capabilities=["financial_analysis", "reporting", "compliance"],
                skills=["financial_modeling", "budgeting", "forecasting"],
                tools=["excel", "sap", "tableau"],
                system_prompt=f"You are a {title}."
            ))
    
    # Legal Compliance (20)
    legal = [
        ("contract", "Contract Expert"),
        ("ip", "IP Expert"),
        ("privacy", "Privacy Expert"),
        ("corporate", "Corporate Expert"),
    ]
    
    for i, (lid, title) in enumerate(legal):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"domain_legal_{lid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.DOMAIN_EXPERT,
                personality={"specialty": title, "style": "compliance_focused"},
                capabilities=["legal_review", "contract_drafting", "compliance"],
                skills=["risk_assessment", "negotiation", "documentation"],
                tools=["legal_databases", "contract_management"],
                system_prompt=f"You are a {title}."
            ))
    
    # HR (20)
    hr = [
        ("recruiting", "Recruiting Expert"),
        ("training", "Training Expert"),
        ("compensation", "Compensation Expert"),
        ("culture", "Culture Expert"),
    ]
    
    for i, (hid, title) in enumerate(hr):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"domain_hr_{hid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.DOMAIN_EXPERT,
                personality={"specialty": title, "style": "people_oriented"},
                capabilities=["hr_management", "talent_development", "culture_building"],
                skills=["interviewing", "training_design", "employee_engagement"],
                tools=["workday", "linkedin", "lms"],
                system_prompt=f"You are a {title}."
            ))
    
    # Data Analytics (20)
    analytics = [
        ("statistics", "Statistics Expert"),
        ("visualization", "Visualization Expert"),
        ("mining", "Data Mining Expert"),
        ("business", "Business Analytics Expert"),
    ]
    
    for i, (aid, title) in enumerate(analytics):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"domain_analytics_{aid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.DOMAIN_EXPERT,
                personality={"specialty": title, "style": "data_driven"},
                capabilities=["data_analysis", "modeling", "insights"],
                skills=["statistics", "machine_learning", "visualization"],
                tools=["python", "r", "tableau", "sql"],
                system_prompt=f"You are a {title}."
            ))
    
    for expert in experts:
        registry.register(expert)
    
    logger.info(f"Created {len(experts)} domain experts")
    return experts


def create_industry_experts(registry: AgentRegistry) -> List[AgentProfile]:
    """Create 90 Industry experts"""
    experts = []
    
    # Internet (20)
    internet = [
        ("e_commerce", "E-commerce Expert"),
        ("social", "Social Media Expert"),
        ("search", "Search Expert"),
        ("gaming", "Gaming Expert"),
    ]
    
    for i, (iid, title) in enumerate(internet):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"industry_net_{iid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.INDUSTRY_EXPERT,
                personality={"specialty": title, "style": "internet_native"},
                capabilities=["industry_knowledge", "market_analysis", "trend_forecasting"],
                skills=["user_behavior", "platform_strategy", "monetization"],
                tools=["analytics", "competitive_intelligence"],
                system_prompt=f"You are a {title}."
            ))
    
    # Fintech (15)
    fintech = [
        ("payments", "Payments Expert"),
        ("lending", "Lending Expert"),
        ("insurance", "Insurtech Expert"),
    ]
    
    for i, (fid, title) in enumerate(fintech):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"industry_fin_{fid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.INDUSTRY_EXPERT,
                personality={"specialty": title, "style": "fintech_expert"},
                capabilities=["fintech_knowledge", "regulatory_compliance", "innovation"],
                skills=["payments", "risk_management", "blockchain"],
                tools=["fintech_platforms", "risk_models"],
                system_prompt=f"You are a {title}."
            ))
    
    # E-commerce Retail (15)
    retail = [
        ("omnichannel", "Omnichannel Expert"),
        ("supply_chain", "Supply Chain Expert"),
        ("marketing", "Retail Marketing Expert"),
    ]
    
    for i, (rid, title) in enumerate(retail):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"industry_ret_{rid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.INDUSTRY_EXPERT,
                personality={"specialty": title, "style": "retail_expert"},
                capabilities=["retail_knowledge", "operations", "customer_experience"],
                skills=["inventory", "logistics", "merchandising"],
                tools=["erp", "crm", "analytics"],
                system_prompt=f"You are a {title}."
            ))
    
    # Healthcare (15)
    healthcare = [
        ("telemedicine", "Telemedicine Expert"),
        ("health_data", "Health Data Expert"),
        ("pharma", "Pharma Tech Expert"),
    ]
    
    for i, (hid, title) in enumerate(healthcare):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"industry_health_{hid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.INDUSTRY_EXPERT,
                personality={"specialty": title, "style": "healthcare_expert"},
                capabilities=["healthcare_knowledge", "compliance", "innovation"],
                skills=["medical_data", "regulatory", "patient_care"],
                tools=["ehr", "health_platforms", "analytics"],
                system_prompt=f"You are a {title}."
            ))
    
    # Education (15)
    education = [
        ("edtech", "EdTech Expert"),
        ("elearning", "E-Learning Expert"),
        ("assessment", "Assessment Expert"),
    ]
    
    for i, (eid, title) in enumerate(education):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"industry_edu_{eid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.INDUSTRY_EXPERT,
                personality={"specialty": title, "style": "education_expert"},
                capabilities=["education_knowledge", "pedagogy", "technology"],
                skills=["curriculum", "online_learning", "assessment"],
                tools=["lms", "video_platforms", "collaboration"],
                system_prompt=f"You are a {title}."
            ))
    
    # Manufacturing (10)
    manufacturing = [
        ("smart_factory", "Smart Factory Expert"),
        ("iot", "IoT Expert"),
    ]
    
    for i, (mid, title) in enumerate(manufacturing):
        for j in range(5):
            experts.append(AgentProfile(
                agent_id=f"industry_mfg_{mid}_{j+1}", 
                name=f"{title}{chr(65+j)}", 
                agent_type=AgentType.INDUSTRY_EXPERT,
                personality={"specialty": title, "style": "manufacturing_expert"},
                capabilities=["manufacturing_knowledge", "automation", "optimization"],
                skills=["iot", "robotics", "process_improvement"],
                tools=["scada", "plc", "mes"],
                system_prompt=f"You are a {title}."
            ))
    
    for expert in experts:
        registry.register(expert)
    
    logger.info(f"Created {len(experts)} industry experts")
    return experts


def initialize_experts_system() -> AgentRegistry:
    """Initialize 432 Experts System"""
    registry = get_agent_registry()
    
    tech_experts = create_technical_experts(registry)
    domain_experts = create_domain_experts(registry)
    industry_experts = create_industry_experts(registry)
    
    total = len(tech_experts) + len(domain_experts) + len(industry_experts)
    
    print(f"\n{'='*60}")
    print(f"Experts System initialized")
    print(f"Technical experts: {len(tech_experts)}")
    print(f"Domain experts: {len(domain_experts)}")
    print(f"Industry experts: {len(industry_experts)}")
    print(f"Total: {total}")
    print(f"{'='*60}\n")
    
    return registry


# Global variable for Experts System
EXPERTS_SYSTEM: Dict[str, List[AgentProfile]] = {
    "TECHNICAL": [],
    "DOMAIN": [],
    "INDUSTRY": [],
}
"""Experts System 432 experts organized by domain"""


def _populate_experts_system():
    """Populate EXPERTS_SYSTEM dict"""
    if not EXPERTS_SYSTEM["TECHNICAL"]:
        registry = get_agent_registry()
        
        tech = create_technical_experts(registry)
        domain = create_domain_experts(registry)
        industry = create_industry_experts(registry)
        
        EXPERTS_SYSTEM["TECHNICAL"] = tech
        EXPERTS_SYSTEM["DOMAIN"] = domain
        EXPERTS_SYSTEM["INDUSTRY"] = industry


_populate_experts_system()
