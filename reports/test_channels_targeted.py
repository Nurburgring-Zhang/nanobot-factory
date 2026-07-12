"""Targeted test: verify channels actually return items with mock transport."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Hermes\生产平台\nanobot-factory\backend")

import httpx

# Test arxiv
async def test_arxiv():
    body = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1234.5678v1</id>
    <title>Test Paper</title>
    <summary>Abstract</summary>
    <author><name>John Doe</name></author>
    <published>2024-01-01T00:00:00Z</published>
  </entry>
</feed>"""

    def handler(request):
        return httpx.Response(200, content=body,
                              headers={"content-type": "application/atom+xml"})

    transport = httpx.MockTransport(handler)
    from imdf.crawler.channels.academic import ArxivChannel
    ch = ArxivChannel(transport=transport, timeout=5.0)
    results = await ch.search("test", 3)
    print(f"arxiv results: {len(results)}")
    for r in results[:3]:
        print(f"  {r.id} - {r.title[:40]}")
    return results

# Test kaggle
async def test_kaggle():
    body = json.dumps([
        {"id": 1, "ref": "owner/slug1", "title": "Dataset 1",
         "creatorName": "alice", "licenseName": "CC0", "downloadCount": 100}
    ]).encode("utf-8")

    def handler(request):
        return httpx.Response(200, content=body,
                              headers={"content-type": "application/json"})

    transport = httpx.MockTransport(handler)
    from imdf.crawler.channels.datasets import KaggleCrawler
    ch = KaggleCrawler(transport=transport, timeout=5.0)
    results = await ch.list_datasets("test", 3)
    print(f"kaggle results: {len(results)}")
    for r in results[:3]:
        print(f"  {r.id} - {r.title}")
    return results

# Test S3
async def test_s3():
    body = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult>
<Name>aws-public-datasets</Name>
<Prefix>cats</Prefix>
<Contents><Key>cats/001.jpg</Key><Size>1024</Size><LastModified>2024-01-01T00:00:00.000Z</LastModified></Contents>
</ListBucketResult>"""

    def handler(request):
        return httpx.Response(200, content=body,
                              headers={"content-type": "application/xml"})

    transport = httpx.MockTransport(handler)
    from imdf.crawler.channels.storage import S3Channel
    ch = S3Channel(transport=transport, timeout=5.0)
    results = await ch.search("cats", 3)
    print(f"S3 results: {len(results)}")
    for r in results[:3]:
        print(f"  {r.id} - {r.bucket}/{r.key}")
    return results

# Test pubmed
async def test_pubmed():
    # PubMed eSearch returns JSON with esearchresult.idlist
    body = json.dumps({"esearchresult": {"idlist": ["12345", "67890"]}}).encode("utf-8")
    def handler_es(request):
        return httpx.Response(200, content=body,
                              headers={"content-type": "application/json"})

    # PubMed esummary returns result wrapper
    summary = {"result": {"uids": ["12345"], "12345": {
        "uid": "12345", "title": "Test PubMed Paper",
        "authors": [{"name": "Smith J"}], "pubdate": "2024 Jan 15",
        "elocationid": "doi: 10.1234/test", "articleids": [{"idtype": "doi", "value": "10.1234/test"}]
    }}}
    body2 = json.dumps(summary).encode("utf-8")
    def handler_summary(request):
        return httpx.Response(200, content=body2,
                              headers={"content-type": "application/json"})

    # Use side_effect
    from itertools import cycle
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if "esearch" in str(request.url):
            return httpx.Response(200, content=body,
                                  headers={"content-type": "application/json"})
        return httpx.Response(200, content=body2,
                              headers={"content-type": "application/json"})

    transport = httpx.MockTransport(handler)
    from imdf.crawler.channels.academic import PubMedChannel
    ch = PubMedChannel(transport=transport, timeout=5.0)
    results = await ch.search("test", 3)
    print(f"pubmed results: {len(results)}")
    for r in results[:3]:
        print(f"  {r.id} - {r.title[:40]}")
    return results

# Test google scholar
async def test_googlescholar():
    body = b"<html><body><h3 class='gs_rt'>Test Paper</h3></body></html>"
    def handler(request):
        return httpx.Response(200, content=body,
                              headers={"content-type": "text/html"})
    transport = httpx.MockTransport(handler)
    from imdf.crawler.channels.academic import GoogleScholarChannel
    ch = GoogleScholarChannel(transport=transport, timeout=5.0)
    results = await ch.search("test", 3)
    print(f"googlescholar results: {len(results)}")
    for r in results[:3]:
        print(f"  {r.id} - {r.title[:40]}")
    return results

async def main():
    print("--- arxiv ---")
    try:
        await test_arxiv()
    except Exception as e:
        print(f"arxiv FAILED: {e}")
    print()
    print("--- kaggle ---")
    try:
        await test_kaggle()
    except Exception as e:
        print(f"kaggle FAILED: {e}")
    print()
    print("--- S3 ---")
    try:
        await test_s3()
    except Exception as e:
        print(f"S3 FAILED: {e}")
    print()
    print("--- pubmed ---")
    try:
        await test_pubmed()
    except Exception as e:
        print(f"pubmed FAILED: {e}")
    print()
    print("--- googlescholar ---")
    try:
        await test_googlescholar()
    except Exception as e:
        print(f"googlescholar FAILED: {e}")

asyncio.run(main())