"""E2E example script for the report."""
import sys
import asyncio
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend')

from imdf.intelligence.agent_reach.integration import AgentReachIntegration
from imdf.intelligence.agent_reach.schemas import FetchResult, MultiChannelResult


async def make_fetch(channel):
    async def _f(query, **kwargs):
        return FetchResult(
            success=True,
            channel=channel,
            query=query,
            content=f"mock-{channel}-{query}",
            url=f"https://{channel}.mock/{query}",
            content_type="application/json",
            metadata={"engine": f"{channel}-mock", "query": query},
            latency_ms=1.0,
        )
    return _f


async def main():
    integ = AgentReachIntegration()
    # mock all 4 channels to avoid network
    for ch in ["exa_search", "web", "reddit", "twitter"]:
        integ._get_handler(ch).fetch = await make_fetch(ch)

    print("=== E2E Example: search 'AI safety' on 4 channels ===")
    result = await integ.search("AI safety")
    print(f"Type: {type(result).__name__}")
    print(f"Query: {result.query}")
    print(f"Channels: {result.channels}")
    print(f"Total: {result.total}")
    print(f"Success: {result.success_count}")
    print(f"Error: {result.error_count}")
    print(f"Elapsed ms: {result.elapsed_ms:.2f}")
    print()
    for ch, fr in result.results.items():
        print(f"  - {ch}: success={fr.success} content={fr.content!r} engine={fr.metadata.get('engine')!r}")
    print()
    print("Cache info:", integ.cache_info())


asyncio.run(main())