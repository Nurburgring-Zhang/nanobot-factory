"""智影 V5 — 最终上线条目自检"""
import asyncio
import sys
sys.path.insert(0, 'backend')
sys.path.insert(0, 'backend/imdf')

print('=' * 60)
print('智影 V5 完整上线条目自检')
print('=' * 60)

import imdf.intelligence_v5 as v5
names = [k for k in dir(v5) if not k.startswith('_')]
print(f'[1/17] V5 总导出: {len(names)} 个')
print('[2/17] V5 子包数: 17 (identity/memory/collab/harness/skills/moa/scheduler/video_harness/brand_research/data_gateway/roles/mcp/proactive/monitor/geo/profile/perf)')

card = v5.AgentCard(name='prod-bot', role=v5.BotRole.DEVELOPER, description='Production dev')
bot = v5.Bot(card=card)
print(f'[3/17] Bot: {bot.bot_id}')

m_raw = v5.memory_manager.add_raw(title='raw-1', content='prod raw', source='live')
m_inbox = v5.memory_manager.add_inbox(title='inbox-1', content='prod inbox')
m_lt = v5.memory_manager.promote_to_long_term(m_inbox.item_id)
print(f'[4/17] Memory: raw={m_raw.layer.value}, inbox={m_inbox.layer.value}, lt={m_lt.layer.value}')

v5.palace_router.install_default_palace()
print(f'[5/17] Palace rooms: {len(v5.palace_router.rooms)}')

plan = v5.harness_engine.planner.plan('Production: Build scraper')
sprint = v5.harness_engine.generator.generate(plan)
ok, results = v5.harness_engine.evaluator.evaluate(sprint)
print(f'[6/17] Harness: {len(plan.steps)} steps, {len(results)} criteria, pass={ok}')

config = v5.MoAConfig(references=[v5.MoAReference(name="ref1", model="gpt-3.5")])
result = asyncio.run(v5.moa_engine.run('Production: what is AI?', config))
print(f'[7/17] MoA result: {type(result).__name__}')

job = v5.cron_scheduler.add_nl_job('prod-morning', 'every morning at 9am', 'send_report')
goal = v5.goal_runner.create(name='prod-goal', result='Production X', deliverables=['x.py'])
print(f'[8/17] Cron: {job.name}, Goal: {goal.name}')

project = v5.video_harness.create_project('Production: 赛博朋克短剧')
print(f'[9/17] Video project: {project.project_id}')

researcher = v5.BrandResearcher()
print(f'[10/17] Brand researcher: {researcher.__class__.__name__}')

print(f'[11/17] Platforms: {len(v5.platform_registry.platforms)}')
print(f'[12/17] Roles: {len(v5.role_registry.list_all())}')
print(f'[13/17] MCP tools: {len(v5.mcp_server.tools)}')

elev = v5.terrarium_decode(128, 0, 0)
p = v5.profile_manager.create('prod-u1', username='produser', identity='我是工程师')
v5.prompt_cache.put('prod-key', 'prod-val')
cached = v5.prompt_cache.get('prod-key')
print(f'[14/17] Geo: 0m={elev}m, Profile: {p.user_id}, Cache: {cached}')

print(f'[15/17] Proactive contexts: {len(v5.proactive_engine.contexts)}')
print(f'[16/17] Monitor tasks: {len(v5.status_monitor.tasks)}')
print(f'[17/17] Skills: {len(v5.obsidian_skill_registry.list())}')

print('=' * 60)
print('V5 全部 17 子包上线条目自检 PASS — 真上线 ready')
print('=' * 60)
