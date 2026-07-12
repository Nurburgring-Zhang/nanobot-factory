"""test_datasets_5.py — 5 public dataset API crawlers (P20-B1 batch 2)

Tests:
    - KaggleCrawler              (REST)
    - HuggingFaceDatasetsCrawler (HF Datasets Server)
    - OpenMLCrawler              (REST)
    - UCIMLCrawler               (HTML scrape)
    - PapersWithCodeCrawler      (REST)

All tests use httpx.MockTransport — no real network.
Each crawler must have ≥6 tests.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from typing import Any, Dict, Optional, Tuple

import httpx

_THIS = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_THIS)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CRAWLER_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.channels.datasets import Dataset, BaseDatasetCrawler
from imdf.crawler.channels.datasets.kaggle import KaggleCrawler
from imdf.crawler.channels.datasets.huggingface import HuggingFaceDatasetsCrawler
from imdf.crawler.channels.datasets.openml import OpenMLCrawler
from imdf.crawler.channels.datasets.uci import (
    UCIMLCrawler,
    parse_uci_search_html,
)
from imdf.crawler.channels.datasets.paperswithcode import PapersWithCodeCrawler


# ============================================================
# Mock factories — produce httpx.MockTransport per crawler
# ============================================================

def _kaggle_mock_factory(payload: Any) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "datasets/list" in str(request.url):
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not mocked"})
    return httpx.MockTransport(handler)


def _hf_mock_factory(payload: Any) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/datasets" in str(request.url):
            return httpx.Response(200, json=payload)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def _openml_mock_factory(payload: Any) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/v1/json/data/list" in str(request.url):
            return httpx.Response(200, json=payload)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def _uci_mock_factory(payload: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "archive.ics.uci.edu" in str(request.url):
            return httpx.Response(200, text=payload)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def _pwc_mock_factory(payload: Any) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/v1/datasets/" in str(request.url):
            return httpx.Response(200, json=payload)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


# ============================================================
# Fixtures
# ============================================================

KAGGLE_PAYLOAD = [
    {
        "id": 123,
        "ref": "owner/cats-and-dogs",
        "title": "Cats and Dogs",
        "subtitle": "10k labeled cat/dog images",
        "creatorName": "owner",
        "downloadCount": 5432,
        "totalBytes": 104_857_600,
        "tags": [{"name": "image"}, {"name": "classification"}],
        "licenseName": "CC BY 4.0",
        "lastUpdated": "2024-03-01T00:00:00Z",
        "isPrivate": False,
        "kernelCount": 12,
        "category": "Images",
        "fileTypes": ["csv", "json"],
    },
    {
        "id": 456,
        "ref": "owner/iris-flower",
        "title": "Iris Flower Dataset",
        "subtitle": "Classic iris dataset",
        "creatorName": "owner",
        "downloadCount": 99000,
        "totalBytes": 4096,
        "tags": [{"name": "tabular"}, {"name": "beginner"}],
        "licenseName": "Public Domain",
        "lastUpdated": "2024-05-15T12:00:00Z",
        "isPrivate": False,
        "kernelCount": 0,
        "category": "Tabular",
        "fileTypes": ["csv"],
    },
]

HF_PAYLOAD = [
    {
        "id": "squad",
        "downloads": 100000,
        "downloadsAllTime": 250000,
        "tags": ["task_categories:question-answering",
                 "language:en",
                 "size_categories:100K<n<1M"],
        "lastModified": "2024-06-01T00:00:00Z",
        "private": False,
        "gated": False,
        "author": "rajpurkar",
        "likes": 234,
        "siblings": [
            {"rfilename": "data/train-00000-of-00001.parquet"},
            {"rfilename": "README.md"},
        ],
        "cardData": {
            "license": "cc-by-4.0",
            "description": "Stanford Question Answering Dataset",
            "summary": "SQuAD is a reading comprehension dataset",
            "dataset_info": {"num_rows": 87599},
        },
    },
    {
        "id": "imagenet-1k",
        "downloads": 50000,
        "downloadsAllTime": 150000,
        "tags": ["task_categories:image-classification"],
        "lastModified": "2023-12-01T00:00:00Z",
        "private": True,
        "gated": "manual",
        "author": "imagenet",
        "likes": 999,
        "siblings": [
            {"rfilename": "data/train-00000.parquet"},
            {"rfilename": "data/val-00000.parquet"},
        ],
        "cardData": {
            "license": "custom",
            "description": "ImageNet 1k",
            "summary": "ImageNet",
        },
    },
]

OPENML_PAYLOAD = {
    "data": {
        "dataset": [
            {
                "did": "1",
                "name": "anneal",
                "version": "1",
                "status": "active",
                "format": "ARFF",
                "tag": ["study_1", "uci", "categorical"],
                "visibility": "public",
                "uploader": "1",
                "url": "https://api.openml.org/data/download/1/anneal.arff",
                "upload_date": "2014-08-21 16:16:14",
                "licence": "Public",
            },
            {
                "did": "61",
                "name": "iris",
                "version": "2",
                "status": "active",
                "format": "ARFF",
                "tag": ["uci", "study_14", "classification"],
                "visibility": "public",
                "uploader": "1",
                "url": "https://api.openml.org/data/download/61/iris.arff",
                "upload_date": "2014-09-19 17:29:39",
                "licence": "Public",
            },
        ]
    }
}

UCI_HTML = """
<html><body>
  <div class="dataset-card">
    <a class="link-style" href="/dataset/53/iris">Iris</a>
    <div class="dataset-description">
      Classic iris dataset with 150 samples.
    </div>
    <span class="dataset-tag">classification</span>
    <span class="dataset-tag">tabular</span>
  </div>
  <div class="dataset-card">
    <a class="link-style" href="/dataset/2/adult">Adult</a>
    <div class="dataset-description">
      Census income dataset.
    </div>
    <span class="dataset-tag">tabular</span>
    <span class="dataset-tag">categorical</span>
  </div>
</body></html>
"""

PWC_PAYLOAD = {
    "count": 2,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": "mnist",
            "name": "MNIST",
            "description": "Handwritten digit images",
            "url": "https://paperswithcode.com/dataset/mnist",
            "tags": ["image", "classification"],
            "variants": ["mnist", "fashion-mnist"],
            "modalities": ["Images"],
            "languages": ["English"],
            "tasks": [
                {"id": "image-classification", "name": "Image Classification"}
            ],
            "num_papers": 1234,
            "num_tasks": 5,
        },
        {
            "id": "cifar-10",
            "name": "CIFAR-10",
            "description": "CIFAR-10 image classification dataset in parquet format",
            "url": "https://paperswithcode.com/dataset/cifar-10",
            "tags": ["image", "classification"],
            "variants": [],
            "modalities": ["Images"],
            "languages": ["English"],
            "tasks": [
                {"id": "image-classification", "name": "Image Classification"}
            ],
            "num_papers": 890,
            "num_tasks": 3,
        },
    ],
}


# ============================================================
# Helper — run async coroutine in tests
# ============================================================

def _run(coro):
    """Run coroutine and return result, even if there's already a loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # in same thread — use a fresh loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(asyncio.run, coro)
                return fut.result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ============================================================
# Dataset model tests
# ============================================================

class TestDatasetModel(unittest.TestCase):
    """Pydantic v2 Dataset model — covers required + edge cases."""

    def test_minimal_required_fields(self):
        ds = Dataset(id="x", title="X", url="https://example.com")
        self.assertEqual(ds.id, "x")
        self.assertEqual(ds.title, "X")
        self.assertEqual(ds.url, "https://example.com")
        self.assertEqual(ds.format, [])
        self.assertEqual(ds.tags, [])
        self.assertEqual(ds.channel, "")
        self.assertIsNotNone(ds.created_at)

    def test_format_coercion_from_string(self):
        ds = Dataset(id="x", title="X", url="u", format="csv, parquet, arrow")
        self.assertEqual(ds.format, ["csv", "parquet", "arrow"])

    def test_format_coercion_from_pipe(self):
        ds = Dataset(id="x", title="X", url="u", format="csv|parquet|arrow")
        self.assertEqual(ds.format, ["csv", "parquet", "arrow"])

    def test_tags_coercion_from_list(self):
        ds = Dataset(id="x", title="X", url="u", tags=["a", "b", "", None])
        self.assertEqual(ds.tags, ["a", "b"])

    def test_downloads_negative_becomes_none(self):
        ds = Dataset(id="x", title="X", url="u", downloads=-5)
        self.assertIsNone(ds.downloads)

    def test_url_httpurl_compat(self):
        # HttpUrl input → str
        from pydantic import HttpUrl
        ds = Dataset(id="x", title="X", url=str(HttpUrl("https://example.com")))
        # Pydantic v2 HttpUrl may add trailing slash — accept either
        self.assertIn(ds.url, ("https://example.com", "https://example.com/"))

    def test_to_dict_isoformat(self):
        ds = Dataset(id="x", title="X", url="u")
        out = ds.to_dict()
        self.assertIn("created_at", out)
        # ISO format with T
        self.assertIn("T", out["created_at"])

    def test_extra_fields_allowed(self):
        ds = Dataset(id="x", title="X", url="u", my_custom_field=42)
        # With extra="allow" Pydantic v2 puts extras at top level
        self.assertEqual(getattr(ds, "my_custom_field", None), 42)
        # And to_dict should preserve them
        out = ds.to_dict()
        self.assertEqual(out.get("my_custom_field"), 42)


# ============================================================
# Kaggle
# ============================================================

class TestKaggleCrawler(unittest.TestCase):

    def setUp(self):
        self.transport = _kaggle_mock_factory(KAGGLE_PAYLOAD)
        self.cw = KaggleCrawler(transport=self.transport)

    def test_mock_returns_n_records(self):
        results = _run(self.cw.list_datasets("cats", max_results=5))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(d, Dataset) for d in results))

    def test_dataset_fields_populated(self):
        results = _run(self.cw.list_datasets("cats", max_results=5))
        d0 = results[0]
        self.assertEqual(d0.id, "123")
        self.assertEqual(d0.title, "Cats and Dogs")
        self.assertIn("kaggle.com/datasets/owner/cats-and-dogs", d0.url)
        self.assertEqual(d0.channel, "kaggle_datasets")
        self.assertEqual(d0.format, ["csv", "json"])
        self.assertIn("image", d0.tags)
        self.assertEqual(d0.license, "CC BY 4.0")
        self.assertEqual(d0.downloads, 5432)
        self.assertEqual(d0.size, "100.0 MB")
        self.assertEqual(d0.author, "owner")
        self.assertEqual(d0.last_updated, "2024-03-01T00:00:00Z")

    def test_max_results_truncates(self):
        results = _run(self.cw.list_datasets("cats", max_results=1))
        self.assertEqual(len(results), 1)

    def test_empty_response(self):
        cw = KaggleCrawler(transport=_kaggle_mock_factory([]))
        results = _run(cw.list_datasets("nothing"))
        self.assertEqual(results, [])

    def test_status_error_returns_empty(self):
        def handler(request):
            return httpx.Response(500, json={"error": "server"})
        cw = KaggleCrawler(transport=httpx.MockTransport(handler))
        results = _run(cw.list_datasets("cats"))
        self.assertEqual(results, [])

    def test_auth_header_present_with_credentials(self):
        seen_headers = {}
        def handler(request):
            seen_headers.update(dict(request.headers))
            return httpx.Response(200, json=KAGGLE_PAYLOAD)
        cw = KaggleCrawler(transport=httpx.MockTransport(handler),
                            username="u", key="k")
        _run(cw.list_datasets("cats"))
        self.assertIn("authorization", seen_headers)
        self.assertTrue(seen_headers["authorization"].startswith("Basic "))

    def test_sync_wrapper(self):
        results = self.cw.list_datasets_sync("cats", max_results=3)
        self.assertEqual(len(results), 2)
        self.assertTrue(isinstance(results[0], Dataset))


# ============================================================
# HuggingFace
# ============================================================

class TestHuggingFaceCrawler(unittest.TestCase):

    def setUp(self):
        self.transport = _hf_mock_factory(HF_PAYLOAD)
        self.cw = HuggingFaceDatasetsCrawler(transport=self.transport)

    def test_basic_list(self):
        results = _run(self.cw.list_datasets("qa", max_results=5))
        self.assertEqual(len(results), 2)
        for d in results:
            self.assertIsInstance(d, Dataset)
            self.assertTrue(d.url.startswith("https://huggingface.co/datasets/"))

    def test_format_inferred_from_siblings(self):
        results = _run(self.cw.list_datasets("qa", max_results=5))
        self.assertIn("parquet", results[0].format)

    def test_tags_split_colon(self):
        results = _run(self.cw.list_datasets("qa", max_results=5))
        # "task_categories:question-answering" → "question-answering"
        self.assertIn("question-answering", results[0].tags)
        self.assertIn("en", results[0].tags)

    def test_size_categories_to_size(self):
        results = _run(self.cw.list_datasets("qa", max_results=5))
        # squad has size_categories:100K<n<1M
        self.assertIsNotNone(results[0].size)

    def test_card_data_license(self):
        results = _run(self.cw.list_datasets("qa", max_results=5))
        self.assertEqual(results[0].license, "cc-by-4.0")

    def test_private_gated_extras(self):
        results = _run(self.cw.list_datasets("qa", max_results=5))
        # second record is private + gated
        self.assertTrue(results[1].extra.get("private"))
        self.assertEqual(results[1].extra.get("gated"), "manual")

    def test_downloads_from_all_time(self):
        results = _run(self.cw.list_datasets("qa", max_results=5))
        self.assertEqual(results[0].downloads, 250000)

    def test_token_auth_header(self):
        seen = {}
        def handler(request):
            seen.update(dict(request.headers))
            return httpx.Response(200, json=HF_PAYLOAD)
        cw = HuggingFaceDatasetsCrawler(transport=httpx.MockTransport(handler),
                                          token="hf_fake")
        _run(cw.list_datasets("qa"))
        self.assertEqual(seen.get("authorization"), "Bearer hf_fake")

    def test_status_error_returns_empty(self):
        def handler(request):
            return httpx.Response(503, text="down")
        cw = HuggingFaceDatasetsCrawler(transport=httpx.MockTransport(handler))
        results = _run(cw.list_datasets("qa"))
        self.assertEqual(results, [])


# ============================================================
# OpenML
# ============================================================

class TestOpenMLCrawler(unittest.TestCase):

    def setUp(self):
        self.transport = _openml_mock_factory(OPENML_PAYLOAD)
        self.cw = OpenMLCrawler(transport=self.transport)

    def test_basic_list(self):
        results = _run(self.cw.list_datasets("iris", max_results=10))
        self.assertEqual(len(results), 2)
        for d in results:
            self.assertIsInstance(d, Dataset)
            self.assertEqual(d.channel, "openml")

    def test_dataset_fields(self):
        results = _run(self.cw.list_datasets("iris", max_results=10))
        d0 = results[0]
        self.assertEqual(d0.id, "1")
        self.assertEqual(d0.title, "anneal")
        self.assertEqual(d0.format, ["arff"])
        self.assertIn("uci", d0.tags)
        self.assertEqual(d0.license, "Public")
        self.assertEqual(d0.last_updated, "2014-08-21 16:16:14")

    def test_version_in_extra(self):
        results = _run(self.cw.list_datasets("iris", max_results=10))
        self.assertEqual(results[0].extra.get("version"), "1")
        self.assertEqual(results[1].extra.get("version"), "2")

    def test_max_results_caps(self):
        results = _run(self.cw.list_datasets("iris", max_results=1))
        self.assertEqual(len(results), 1)

    def test_empty_response(self):
        cw = OpenMLCrawler(transport=_openml_mock_factory({"data": {"dataset": []}}))
        results = _run(cw.list_datasets("nothing"))
        self.assertEqual(results, [])

    def test_status_error_returns_empty(self):
        def handler(request):
            return httpx.Response(500, json={"error": "internal"})
        cw = OpenMLCrawler(transport=httpx.MockTransport(handler))
        results = _run(cw.list_datasets("iris"))
        self.assertEqual(results, [])

    def test_url_construction(self):
        results = _run(self.cw.list_datasets("iris", max_results=10))
        # second record's url field should be preserved
        self.assertIn("iris.arff", results[1].url)


# ============================================================
# UCI
# ============================================================

class TestUCIMLCrawler(unittest.TestCase):

    def setUp(self):
        self.transport = _uci_mock_factory(UCI_HTML)
        self.cw = UCIMLCrawler(transport=self.transport)

    def test_html_parser_extracts_two(self):
        records = parse_uci_search_html(UCI_HTML)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["id"], "53")
        self.assertEqual(records[1]["id"], "2")

    def test_basic_list(self):
        results = _run(self.cw.list_datasets("iris", max_results=5))
        self.assertEqual(len(results), 2)
        for d in results:
            self.assertIsInstance(d, Dataset)
            self.assertEqual(d.channel, "uci_ml")

    def test_dataset_fields(self):
        results = _run(self.cw.list_datasets("iris", max_results=5))
        d0 = results[0]
        self.assertEqual(d0.id, "53")
        self.assertEqual(d0.title, "Iris")
        self.assertIn("archive.ics.uci.edu/dataset/53", d0.url)
        self.assertEqual(d0.description, "Classic iris dataset with 150 samples.")

    def test_tags_extracted(self):
        results = _run(self.cw.list_datasets("iris", max_results=5))
        tags = results[0].tags
        self.assertIn("classification", tags)
        self.assertIn("tabular", tags)

    def test_empty_html(self):
        cw = UCIMLCrawler(transport=_uci_mock_factory("<html></html>"))
        results = _run(cw.list_datasets("nothing"))
        self.assertEqual(results, [])

    def test_status_error_returns_empty(self):
        def handler(request):
            return httpx.Response(500, text="down")
        cw = UCIMLCrawler(transport=httpx.MockTransport(handler))
        results = _run(cw.list_datasets("iris"))
        self.assertEqual(results, [])

    def test_search_query_in_extra(self):
        results = _run(self.cw.list_datasets("iris", max_results=5))
        self.assertEqual(results[0].extra.get("search_query"), "iris")

    def test_max_results_caps(self):
        results = _run(self.cw.list_datasets("iris", max_results=1))
        self.assertEqual(len(results), 1)


# ============================================================
# PapersWithCode
# ============================================================

class TestPapersWithCodeCrawler(unittest.TestCase):

    def setUp(self):
        self.transport = _pwc_mock_factory(PWC_PAYLOAD)
        self.cw = PapersWithCodeCrawler(transport=self.transport)

    def test_basic_list(self):
        results = _run(self.cw.list_datasets("mnist", max_results=5))
        self.assertEqual(len(results), 2)
        for d in results:
            self.assertIsInstance(d, Dataset)
            self.assertEqual(d.channel, "paperswithcode")

    def test_dataset_fields(self):
        results = _run(self.cw.list_datasets("mnist", max_results=5))
        d0 = results[0]
        self.assertEqual(d0.id, "mnist")
        self.assertEqual(d0.title, "MNIST")
        self.assertEqual(d0.url, "https://paperswithcode.com/dataset/mnist")
        self.assertIn("image", d0.tags)
        self.assertEqual(d0.stars, 1234)
        self.assertEqual(d0.size, "1234 papers")

    def test_format_inferred_from_description(self):
        results = _run(self.cw.list_datasets("cifar", max_results=5))
        # cifar description contains "parquet"
        self.assertIn("parquet", results[1].format)

    def test_modalities_languages_as_tags(self):
        results = _run(self.cw.list_datasets("mnist", max_results=5))
        self.assertIn("modality:Images", results[0].tags)
        self.assertIn("lang:English", results[0].tags)

    def test_tasks_as_tags(self):
        results = _run(self.cw.list_datasets("mnist", max_results=5))
        self.assertIn("Image Classification", results[0].tags)

    def test_max_results_caps(self):
        results = _run(self.cw.list_datasets("mnist", max_results=1))
        self.assertEqual(len(results), 1)

    def test_status_error_returns_empty(self):
        def handler(request):
            return httpx.Response(503, json={"error": "down"})
        cw = PapersWithCodeCrawler(transport=httpx.MockTransport(handler))
        results = _run(cw.list_datasets("mnist"))
        self.assertEqual(results, [])

    def test_empty_results(self):
        cw = PapersWithCodeCrawler(
            transport=_pwc_mock_factory({"count": 0, "results": []})
        )
        results = _run(cw.list_datasets("nothing"))
        self.assertEqual(results, [])


# ============================================================
# Integration — verify all 5 channels return Dataset objects
# ============================================================

class TestDatasetCrawlerIntegration(unittest.TestCase):
    """Verify all 5 crawlers share the same public contract."""

    def test_all_have_list_datasets(self):
        for cls in (KaggleCrawler, HuggingFaceDatasetsCrawler,
                    OpenMLCrawler, UCIMLCrawler, PapersWithCodeCrawler):
            self.assertTrue(hasattr(cls, "list_datasets"),
                            f"{cls.__name__} missing list_datasets")

    def test_all_have_channel_attr(self):
        channels = {
            KaggleCrawler.channel,
            HuggingFaceDatasetsCrawler.channel,
            OpenMLCrawler.channel,
            UCIMLCrawler.channel,
            PapersWithCodeCrawler.channel,
        }
        # 5 distinct channel names
        self.assertEqual(len(channels), 5)
        self.assertIn("kaggle_datasets", channels)
        self.assertIn("huggingface_datasets", channels)
        self.assertIn("openml", channels)
        self.assertIn("uci_ml", channels)
        self.assertIn("paperswithcode", channels)

    def test_all_importable_from_datasets_package(self):
        from imdf.crawler.channels import datasets as pkg
        for name in ("KaggleCrawler", "HuggingFaceDatasetsCrawler",
                     "OpenMLCrawler", "UCIMLCrawler", "PapersWithCodeCrawler",
                     "BaseDatasetCrawler", "Dataset"):
            self.assertTrue(hasattr(pkg, name), f"missing: {name}")


if __name__ == "__main__":
    unittest.main()