import sys
import os
import tempfile

sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend')

from imdf.crawler.rss_crawler import RSSCrawler
from imdf.crawler.config import make_default_config, RobotsPolicy

cfg = make_default_config('rss')
cfg.robots_policy = RobotsPolicy.IGNORE
cfg.enable_audit_chain = False

# Test 1: rss_seen.json corruption recovery
with tempfile.TemporaryDirectory() as tmp:
    state_file = os.path.join(tmp, 'rss_seen.json')
    with open(state_file, 'w', encoding='utf-8') as f:
        f.write('{ corrupted json')

    rss = RSSCrawler(config=cfg, state_dir=tmp, feed_fetcher=lambda u: b"""<rss version="2.0"><channel>
<title>Test</title>
<item><title>Item 1</title><link>https://x.com/1</link><guid>1</guid></item>
<item><title>Item 2</title><link>https://x.com/2</link><guid>2</guid></item>
</channel></rss>""")
    r = rss.crawl('https://example.com/feed.xml')
    print('Corrupt state file recovery:', r.status.value, 'items:', len(r.items))

# Test 2: GUID extraction - 4 fallback paths
rss2 = RSSCrawler(config=cfg, state_dir=tempfile.mkdtemp(), feed_fetcher=lambda u: b"""<rss version="2.0"><channel>
<item><title>Only Title</title><link>https://x.com/only-title</link></item>
<item><link>https://x.com/only-link</link></item>
<item><title>Title no link</title></item>
<item><title>No link no id</title></item>
</channel></rss>""")
r = rss2.crawl('https://example.com/feed2.xml')
print('GUIDs:')
for i in r.items:
    print(' -', repr(i['guid']))

# Test 3: max_items limit
big_rss = '<rss><channel>'
for i in range(50):
    big_rss += '<item><title>t{i}</title><link>https://x.com/{i}</link><guid>{i}</guid></item>'.format(i=i)
big_rss += '</channel></rss>'

rss3 = RSSCrawler(config=cfg, state_dir=tempfile.mkdtemp(), feed_fetcher=lambda u: big_rss.encode())
r = rss3.crawl('https://example.com/feed3.xml', max_items=20)
print('max_items=20 with 50 entries:', len(r.items))

# Test 4: Incremental dedup
rss4 = RSSCrawler(config=cfg, state_dir=tempfile.mkdtemp(), feed_fetcher=lambda u: b"""<rss version="2.0"><channel>
<item><title>T1</title><guid>g1</guid></item>
<item><title>T2</title><guid>g2</guid></item>
</channel></rss>""")
r1 = rss4.crawl('https://example.com/feed4.xml')
print('First crawl items:', len(r1.items))
r2 = rss4.crawl('https://example.com/feed4.xml')
print('Second crawl (incremental) items:', len(r2.items))

# Test 5: full_history mode
r3 = rss4.crawl('https://example.com/feed4.xml', full_history=True)
print('Third crawl (full_history) items:', len(r3.items))
