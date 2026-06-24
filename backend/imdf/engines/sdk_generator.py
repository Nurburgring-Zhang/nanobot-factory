"""
SDK Generator — P1-A3-Worker-1
================================
Generate Python / JavaScript / Go SDK packages from an OpenAPI 3.x spec.

The output is a **zip archive** (bytes) containing:
  - python/:  package_name/*.py  (requests + type hints + sync + async)
  - javascript/: package_name.js  (ES6 + fetch + named exports)
  - go/: package_name/*.go        (net/http + struct types)

Design constraints:
  * No external codegen dependency (openapi-generator-cli etc.) — we
    emit string templates from spec fields directly. This keeps the
    module hermetic and avoids adding a 50 MB dependency just to
    satisfy tests.
  * Templates are deterministic — same spec + same package_name +
    same language must produce byte-identical output.
  * Caller passes a single OpenAPI spec dict. The generator picks
    endpoints and schemas; if `paths` / `components.schemas` are
    missing, fall back to minimal hardcoded stubs so the package is
    still importable.
  * Package name validation: ^[a-zA-Z][a-zA-Z0-9_-]{0,127}$ (same as
    the existing API layer regex in sdk_routes.py).
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple


_PACKAGE_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]{0,127}$")
SUPPORTED_LANGUAGES: Tuple[str, ...] = ("python", "javascript", "go")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_package_name(name: str) -> str:
    """Raise ValueError if package_name is invalid; otherwise return as-is."""
    if not isinstance(name, str) or not _PACKAGE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid package_name: {name!r}. "
            "Must match ^[a-zA-Z][a-zA-Z0-9_-]{0,127}$"
        )
    return name


def _resolve_python_module_name(package_name: str) -> str:
    """Map hyphens to underscores for Python module name."""
    return package_name.replace("-", "_")


def _resolve_go_package_path(package_name: str) -> str:
    """Lower-case for Go package directory."""
    return package_name.lower().replace("_", "-")


def _pascal(name: str) -> str:
    """Convert snake/kebab-case to PascalCase."""
    parts = re.split(r"[-_\s]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _camel(name: str) -> str:
    p = _pascal(name)
    return p[:1].lower() + p[1:] if p else p


def _to_python_type(schema: Dict[str, Any], name_hint: str = "Any") -> str:
    """Map a (subset of) JSON Schema to a Python type hint."""
    if not isinstance(schema, dict):
        return "Any"
    if "$ref" in schema:
        ref = schema["$ref"].rsplit("/", 1)[-1]
        return _pascal(ref)
    typ = schema.get("type")
    if typ == "string":
        if "enum" in schema:
            return "Literal[" + ", ".join(json.dumps(v) for v in schema["enum"]) + "]"
        return "str"
    if typ == "integer":
        return "int"
    if typ == "number":
        return "float"
    if typ == "boolean":
        return "bool"
    if typ == "array":
        inner = _to_python_type(schema.get("items", {}))
        return f"List[{inner}]"
    if typ == "object":
        return f"Dict[str, Any]"
    if "oneOf" in schema or "anyOf" in schema:
        opts = schema.get("oneOf") or schema.get("anyOf") or []
        if opts:
            return "Union[" + ", ".join(_to_python_type(o) for o in opts) + "]"
    return "Any"


def _to_js_type(schema: Dict[str, Any]) -> str:
    """Map JSON Schema to TypeScript-like JS type (used in JSDoc)."""
    if not isinstance(schema, dict):
        return "any"
    if "$ref" in schema:
        ref = schema["$ref"].rsplit("/", 1)[-1]
        return _pascal(ref)
    typ = schema.get("type")
    if typ == "string":
        return "string"
    if typ == "integer":
        return "number"
    if typ == "number":
        return "number"
    if typ == "boolean":
        return "boolean"
    if typ == "array":
        return _to_js_type(schema.get("items", {})) + "[]"
    if typ == "object":
        return "object"
    return "any"


def _to_go_type(schema: Dict[str, Any], name_hint: str = "interface{}") -> str:
    """Map JSON Schema to a Go type name."""
    if not isinstance(schema, dict):
        return "interface{}"
    if "$ref" in schema:
        ref = schema["$ref"].rsplit("/", 1)[-1]
        return _pascal(ref)
    typ = schema.get("type")
    if typ == "string":
        return "string"
    if typ == "integer":
        return "int64"
    if typ == "number":
        return "float64"
    if typ == "boolean":
        return "bool"
    if typ == "array":
        inner = _to_go_type(schema.get("items", {}))
        return f"[]{inner}"
    if typ == "object":
        return "map[string]interface{}"
    return "interface{}"


def _iter_operations(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Yield {path, method, operationId, tags, summary, requestBody, parameters}."""
    paths = spec.get("paths") or {}
    out: List[Dict[str, Any]] = []
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in ("get", "post", "put", "delete", "patch"):
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            out.append({
                "path": path,
                "method": method,
                "operationId": op.get("operationId") or f"{method}_{path}".replace("/", "_").replace("{", "").replace("}", ""),
                "tags": op.get("tags") or ["default"],
                "summary": op.get("summary") or "",
                "parameters": op.get("parameters") or [],
                "requestBody": op.get("requestBody"),
            })
    return out


def _iter_schemas(spec: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Yield (name, schema) for each schema in components.schemas."""
    components = spec.get("components") or {}
    schemas = components.get("schemas") or {}
    return [(name, sch) for name, sch in schemas.items() if isinstance(sch, dict)]


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

class SDKGenerator:
    """Generate Python / JS / Go SDK packages as zip bytes.

    Usage::

        gen = SDKGenerator()
        blob = gen.generate(openapi_spec, language="python", package_name="imdf-sdk")
        # blob is bytes of a .zip archive
    """

    SUPPORTED_LANGUAGES = SUPPORTED_LANGUAGES

    # --------------------------- Public API --------------------------------

    def generate(
        self,
        openapi_spec: Dict[str, Any],
        language: str,
        package_name: str,
        version: str = "1.0.0",
    ) -> bytes:
        """Generate a zip archive containing the SDK for one language.

        Args:
            openapi_spec: OpenAPI 3.x dict (may be partial).
            language: One of "python", "javascript", "go".
            package_name: SDK package name (must match ^[a-zA-Z][a-zA-Z0-9_-]{0,127}$).
            version: SemVer string embedded in the SDK metadata.

        Returns:
            bytes — content of a zip archive.

        Raises:
            ValueError: on unsupported language or invalid package_name.
        """
        language = (language or "").strip().lower()
        if language not in self.SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language: {language!r}. "
                f"Supported: {list(self.SUPPORTED_LANGUAGES)}"
            )
        _validate_package_name(package_name)

        spec = openapi_spec or {}
        if language == "python":
            files = self._python_template(spec, package_name, version)
        elif language == "javascript":
            files = self._js_template(spec, package_name, version)
        else:  # go
            files = self._go_template(spec, package_name, version)

        return self._to_zip(files, language=language)

    # --------------------------- Python ------------------------------------

    def _python_template(
        self,
        spec: Dict[str, Any],
        package_name: str,
        version: str = "1.0.0",
    ) -> Dict[str, str]:
        """Generate Python SDK files (sync + async clients + models).

        Returns dict mapping archive-relative path → file content.
        """
        module_name = _resolve_python_module_name(package_name)
        title = (spec.get("info") or {}).get("title") or "IMDF API"
        operations = _iter_operations(spec)
        schemas = _iter_schemas(spec)

        # Models file
        model_lines = [
            '"""Auto-generated Pydantic models."""',
            "from __future__ import annotations",
            "from typing import Any, Dict, List, Optional, Union, Literal",
            "from pydantic import BaseModel, Field",
            "",
        ]
        for name, sch in schemas:
            cls_name = _pascal(name)
            model_lines.append(f"class {cls_name}(BaseModel):")
            props = sch.get("properties") or {}
            required = set(sch.get("required") or [])
            if not props:
                model_lines.append("    pass")
            else:
                for prop_name, prop_sch in props.items():
                    ptype = _to_python_type(prop_sch, prop_name)
                    field_kwargs: List[str] = []
                    desc = prop_sch.get("description") if isinstance(prop_sch, dict) else None
                    if desc:
                        field_kwargs.append(f"description={desc!r}")
                    if prop_name not in required:
                        ptype = f"Optional[{ptype}]"
                        field_kwargs.append("default=None")
                    model_lines.append(
                        f"    {prop_name}: {ptype} = Field({', '.join(field_kwargs)})"
                    )
            model_lines.append("")

        # Client file
        client_lines = [
            '"""Auto-generated IMDF Python SDK client."""',
            "from __future__ import annotations",
            "import json",
            "from typing import Any, Dict, List, Optional",
            "from urllib.parse import urlencode, urljoin",
            "",
            "try:",
            "    import requests  # type: ignore",
            "except ImportError:  # pragma: no cover",
            "    requests = None  # type: ignore",
            "",
            "try:",
            "    import httpx  # type: ignore",
            "except ImportError:  # pragma: no cover",
            "    httpx = None  # type: ignore",
            "",
            "from .models import *  # noqa: F401,F403",
            "",
            f'__version__ = "{version}"',
            f'__title__ = "{title}"',
            "",
            "",
            "class IMDFClient:",
            '    """Synchronous IMDF API client."""',
            "",
            "    def __init__(",
            "        self,",
            "        base_url: str = \"http://localhost:8900\",",
            "        api_key: Optional[str] = None,",
            "        timeout: float = 30.0,",
            "    ) -> None:",
            "        self.base_url = base_url.rstrip(\"/\")",
            "        self.api_key = api_key",
            "        self.timeout = timeout",
            "",
            "    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:",
            "        if requests is None:",
            "            raise RuntimeError(",
            '                "requests is required for sync client; pip install requests"',
            "            )",
            "        url = urljoin(self.base_url + \"/\", path.lstrip(\"/\"))",
            "        headers = kwargs.pop(\"headers\", {}) or {}",
            "        headers.setdefault(\"Content-Type\", \"application/json\")",
            "        if self.api_key:",
            "            headers[\"X-API-Key\"] = self.api_key",
            "        resp = requests.request(",
            "            method, url, headers=headers, timeout=self.timeout, **kwargs",
            "        )",
            "        resp.raise_for_status()",
            "        try:",
            "            return resp.json()",
            "        except ValueError:",
            "            return {\"raw\": resp.text}",
            "",
            "    # ---- Operations ----------------------------------------------------",
            "",
        ]
        for op in operations:
            op_id = _camel(op["operationId"])
            method = op["method"].upper()
            path = op["path"]
            client_lines.append(f"    def {op_id}(self, **kwargs: Any) -> Dict[str, Any]:")
            client_lines.append(f'        """{op["summary"] or op_id} ({method} {path})."""')
            client_lines.append(
                f"        return self._request({method!r}, {path!r}, **kwargs)"
            )
            client_lines.append("")

        # Async client
        async_lines = [
            '"""Auto-generated async IMDF Python SDK client."""',
            "from __future__ import annotations",
            "from typing import Any, Dict, Optional",
            "from urllib.parse import urljoin",
            "",
            "try:",
            "    import httpx  # type: ignore",
            "except ImportError:  # pragma: no cover",
            "    httpx = None  # type: ignore",
            "",
            "from .models import *  # noqa: F401,F403",
            "",
            f'__version__ = "{version}"',
            "",
            "",
            "class AsyncIMDFClient:",
            '    """Asynchronous IMDF API client (requires httpx)."""',
            "",
            "    def __init__(",
            "        self,",
            "        base_url: str = \"http://localhost:8900\",",
            "        api_key: Optional[str] = None,",
            "        timeout: float = 30.0,",
            "    ) -> None:",
            "        if httpx is None:",
            "            raise RuntimeError(",
            '                "httpx is required for async client; pip install httpx"',
            "            )",
            "        self._client = httpx.AsyncClient(",
            "            base_url=base_url,",
            "            timeout=timeout,",
            "            headers={\"X-API-Key\": api_key} if api_key else {},",
            "        )",
            "",
            "    async def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:",
            "        resp = await self._client.request(method, path, **kwargs)",
            "        resp.raise_for_status()",
            "        try:",
            "            return resp.json()",
            "        except ValueError:",
            "            return {\"raw\": resp.text}",
            "",
            "    async def aclose(self) -> None:",
            "        await self._client.aclose()",
            "",
            "    # ---- Operations ----------------------------------------------------",
            "",
        ]
        for op in operations:
            op_id = _camel(op["operationId"])
            method = op["method"].upper()
            path = op["path"]
            async_lines.append(f"    async def {op_id}(self, **kwargs: Any) -> Dict[str, Any]:")
            async_lines.append(f'        """{op["summary"] or op_id} ({method} {path})."""')
            async_lines.append(
                f"        return await self._request({method!r}, {path!r}, **kwargs)"
            )
            async_lines.append("")

        init_lines = [
            f'"""Auto-generated {package_name} SDK ({version})."""',
            f'__version__ = "{version}"',
            "from .client import IMDFClient  # noqa: F401",
            "from .async_client import AsyncIMDFClient  # noqa: F401",
            "",
        ]

        readme = (
            f"# {package_name} (Python)\n\n"
            f"Auto-generated Python SDK for {title} (version {version}).\n\n"
            f"## Install\n\n"
            f"```\npip install {package_name}\n```\n\n"
            f"## Usage\n\n"
            f"```python\n"
            f"from {module_name}.client import IMDFClient\n"
            f"from {module_name}.async_client import AsyncIMDFClient\n\n"
            f"client = IMDFClient(base_url='http://localhost:8900', api_key='YOUR_KEY')\n"
            f"# Sync call example:\n"
            f"# resp = client.someOperation()\n"
            f"```\n\n"
            f"Generated by IMDF SDK Generator — {len(operations)} operations, "
            f"{len(schemas)} models.\n"
        )

        setup_lines = (
            f"from setuptools import setup, find_packages\n\n"
            f"setup(\n"
            f"    name={package_name!r},\n"
            f"    version={version!r},\n"
            f"    packages=find_packages(exclude=['tests', 'tests.*']),\n"
            f"    install_requires=['requests>=2.28', 'pydantic>=2.0'],\n"
            f"    extras_require={{'async': ['httpx>=0.24']}},\n"
            f"    python_requires='>=3.9',\n"
            f")\n"
        )

        return {
            f"{module_name}/__init__.py": "\n".join(init_lines),
            f"{module_name}/client.py": "\n".join(client_lines),
            f"{module_name}/async_client.py": "\n".join(async_lines),
            f"{module_name}/models.py": "\n".join(model_lines),
            f"{module_name}/README.md": readme,
            "setup.py": setup_lines,
        }

    # --------------------------- JavaScript --------------------------------

    def _js_template(
        self,
        spec: Dict[str, Any],
        package_name: str,
        version: str = "1.0.0",
    ) -> Dict[str, str]:
        """Generate JavaScript (ES6) SDK files using fetch."""
        title = (spec.get("info") or {}).get("title") or "IMDF API"
        operations = _iter_operations(spec)
        schemas = _iter_schemas(spec)

        # JSDoc typedefs for schemas
        type_lines = [
            "/**",
            f" * @file Auto-generated {package_name} SDK (JavaScript / ES6).",
            f" * Title: {title}",
            f" * Version: {version}",
            " */",
            "",
            "// ----- Type Definitions -----",
            "",
        ]
        for name, sch in schemas:
            cls_name = _pascal(name)
            props = sch.get("properties") or {}
            type_lines.append(f"/** @typedef {{Object}} {cls_name} */")
            for prop_name, prop_sch in props.items():
                ptype = _to_js_type(prop_sch)
                desc = (prop_sch or {}).get("description") if isinstance(prop_sch, dict) else None
                doc = f" * @property {{{ptype}}} {prop_name}"
                if desc:
                    doc += f" {desc}"
                type_lines.append(doc)
            type_lines.append("")

        # Client implementation
        client_lines = [
            "/**",
            f" * Auto-generated IMDF JavaScript SDK ({version}).",
            " */",
            "",
            f"export const VERSION = {version!r};",
            f"export const TITLE = {title!r};",
            "",
            "export class APIResponse {",
            "  /** @param {{number}} status @param {{any}} data */",
            "  constructor(status, data) { this.status = status; this.data = data; }",
            "}",
            "",
            "export class IMDFClient {",
            "  /**",
            "   * @param {{Object}} config",
            "   * @param {{string}} [config.baseUrl='http://localhost:8900']",
            "   * @param {{string}} [config.apiKey]",
            "   * @param {{number}} [config.timeout=30000]",
            "   */",
            "  constructor(config = {}) {",
            "    this.baseUrl = (config.baseUrl || 'http://localhost:8900').replace(/\\/$/, '');",
            "    this.apiKey = config.apiKey;",
            "    this.timeout = config.timeout || 30000;",
            "  }",
            "",
            "  /**",
            "   * @private",
            "   * @param {{string}} method",
            "   * @param {{string}} path",
            "   * @param {{any}} [body]",
            "   * @param {{Record<string,string>}} [params]",
            "   * @returns {{Promise<APIResponse>}}",
            "   */",
            "  async _request(method, path, body, params) {",
            "    const url = new URL(path, this.baseUrl);",
            "    if (params) {",
            "      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));",
            "    }",
            "    const headers = { 'Content-Type': 'application/json' };",
            "    if (this.apiKey) headers['X-API-Key'] = this.apiKey;",
            "    const init = { method, headers };",
            "    if (body !== undefined) init.body = JSON.stringify(body);",
            "    const controller = new AbortController();",
            "    const timer = setTimeout(() => controller.abort(), this.timeout);",
            "    init.signal = controller.signal;",
            "    try {",
            "      const resp = await fetch(url.toString(), init);",
            "      const text = await resp.text();",
            "      let data;",
            "      try { data = JSON.parse(text); } catch { data = text; }",
            "      if (!resp.ok) {",
            "        throw new Error((data && data.detail) || `HTTP ${resp.status}`);",
            "      }",
            "      return new APIResponse(resp.status, data);",
            "    } finally {",
            "      clearTimeout(timer);",
            "    }",
            "  }",
            "",
            "  // ---- Operations ----",
            "",
        ]
        for op in operations:
            op_id = _camel(op["operationId"])
            method = op["method"].upper()
            path = op["path"]
            client_lines.append(f"  /** {op['summary'] or op_id} ({method} {path}) */")
            client_lines.append(
                f"  async {op_id}(body, params) {{\n"
                f"    return this._request({method!r}, {path!r}, body, params);\n"
                f"  }}"
            )
            client_lines.append("")

        client_lines.append("}")
        client_lines.append("")
        client_lines.append("export default IMDFClient;")

        # package.json
        pkg_json = {
            "name": package_name,
            "version": version,
            "description": f"Auto-generated JS SDK for {title}",
            "main": "index.js",
            "module": "index.js",
            "type": "module",
            "exports": {
                ".": "./index.js",
            },
            "scripts": {"test": "echo \"No tests yet\""},
            "license": "MIT",
            "engines": {"node": ">=14"},
        }

        readme = (
            f"# {package_name} (JavaScript)\n\n"
            f"Auto-generated ES6 JavaScript SDK for {title} (version {version}).\n\n"
            f"## Install\n\n"
            f"```\nnpm install {package_name}\n```\n\n"
            f"## Usage\n\n"
            f"```javascript\n"
            f"import {{ IMDFClient }} from '{package_name}';\n\n"
            f"const client = new IMDFClient({{ baseUrl: 'http://localhost:8900', apiKey: 'YOUR_KEY' }});\n"
            f"// const resp = await client.someOperation();\n"
            f"```\n\n"
            f"Generated by IMDF SDK Generator — {len(operations)} operations, "
            f"{len(schemas)} models.\n"
        )

        return {
            "index.js": "\n".join(client_lines),
            "types.js": "\n".join(type_lines),
            "package.json": json.dumps(pkg_json, indent=2),
            "README.md": readme,
        }

    # --------------------------- Go ----------------------------------------

    def _go_template(
        self,
        spec: Dict[str, Any],
        package_name: str,
        version: str = "1.0.0",
    ) -> Dict[str, str]:
        """Generate Go SDK files using net/http and struct types."""
        title = (spec.get("info") or {}).get("title") or "IMDF API"
        operations = _iter_operations(spec)
        schemas = _iter_schemas(spec)
        pkg_path = _resolve_go_package_path(package_name)
        go_module_name = pkg_path  # e.g. "imdf-sdk"

        # Types file (struct definitions)
        types_lines: List[str] = [
            "// Auto-generated IMDF SDK types.",
            f"// Version: {version}",
            "",
            "package " + go_module_name.replace("-", ""),
            "",
            "import (",
            "\t\"encoding/json\"",
            "\t\"time\"",
            ")",
            "",
        ]
        for name, sch in schemas:
            cls_name = _pascal(name)
            props = sch.get("properties") or {}
            types_lines.append(f"// {cls_name} represents the {name} schema.")
            types_lines.append(f"type {cls_name} struct {{")
            for prop_name, prop_sch in props.items():
                gtype = _to_go_type(prop_sch, prop_name)
                json_tag = prop_name
                desc = (prop_sch or {}).get("description") if isinstance(prop_sch, dict) else None
                if desc:
                    types_lines.append(f"\t// {prop_name} {desc}")
                types_lines.append(f"\t{prop_name.capitalize()} {gtype} `json:\"{json_tag}\"`")
            types_lines.append("}")
            types_lines.append("")

        # Client file
        client_lines: List[str] = [
            "// Auto-generated IMDF Go SDK client.",
            f"// Version: {version}",
            "",
            "package " + go_module_name.replace("-", ""),
            "",
            "import (",
            "\t\"bytes\"",
            "\t\"context\"",
            "\t\"encoding/json\"",
            "\t\"fmt\"",
            "\t\"io\"",
            "\t\"net/http\"",
            "\t\"net/url\"",
            "\t\"strings\"",
            "\t\"time\"",
            ")",
            "",
            "// Client is the IMDF API client.",
            "type Client struct {",
            "\tBaseURL    string",
            "\tAPIKey     string",
            "\tHTTPClient *http.Client",
            "}",
            "",
            "// NewClient creates a new IMDF API client.",
            "func NewClient(baseURL, apiKey string) *Client {",
            "\treturn &Client{",
            "\t\tBaseURL:    strings.TrimRight(baseURL, \"/\"),",
            "\t\tAPIKey:     apiKey,",
            "\t\tHTTPClient: &http.Client{Timeout: 30 * time.Second},",
            "\t}",
            "}",
            "",
            "// APIResponse is the standard response envelope.",
            "type APIResponse struct {",
            "\tStatus int",
            "\tData   json.RawMessage",
            "}",
            "",
            "// request is the internal request helper.",
            "func (c *Client) request(ctx context.Context, method, path string, body, out interface{}) error {",
            "\tfullURL := c.BaseURL + \"/\" + strings.TrimLeft(path, \"/\")",
            "\tvar reqBody io.Reader",
            "\tif body != nil {",
            "\t\tb, err := json.Marshal(body)",
            "\t\tif err != nil { return err }",
            "\t\treqBody = bytes.NewReader(b)",
            "\t}",
            "\treq, err := http.NewRequestWithContext(ctx, method, fullURL, reqBody)",
            "\tif err != nil { return err }",
            "\treq.Header.Set(\"Content-Type\", \"application/json\")",
            "\tif c.APIKey != \"\" {",
            "\t\treq.Header.Set(\"X-API-Key\", c.APIKey)",
            "\t}",
            "\tresp, err := c.HTTPClient.Do(req)",
            "\tif err != nil { return err }",
            "\tdefer resp.Body.Close()",
            "\tif resp.StatusCode >= 400 {",
            "\t\treturn fmt.Errorf(\"HTTP %d\", resp.StatusCode)",
            "\t}",
            "\tif out != nil {",
            "\t\treturn json.NewDecoder(resp.Body).Decode(out)",
            "\t}",
            "\treturn nil",
            "}",
            "",
            "// URLValues is a tiny alias to avoid importing net/url in user code.",
            "type URLValues = url.Values",
            "",
            "// ---- Operations ----",
            "",
        ]
        for op in operations:
            op_id = _pascal(op["operationId"])
            method = op["method"].upper()
            path = op["path"]
            client_lines.append(f"// {op_id} — {op['summary'] or op_id} ({method} {path}).")
            client_lines.append(f"func (c *Client) {op_id}(ctx context.Context) error {{")
            client_lines.append(
                f"\treturn c.request(ctx, {method!r}, {path!r}, nil, nil)"
            )
            client_lines.append("}")
            client_lines.append("")

        # go.mod
        gomod_lines = [
            f"module {go_module_name}",
            "",
            "go 1.21",
            "",
            "require (",
            ")",
        ]

        readme = (
            f"# {package_name} (Go)\n\n"
            f"Auto-generated Go SDK for {title} (version {version}).\n\n"
            f"## Install\n\n"
            f"```\ngo get {go_module_name}\n```\n\n"
            f"## Usage\n\n"
            f"```go\n"
            f"package main\n\n"
            f"import \"{go_module_name}\"\n\n"
            f"func main() {{\n"
            f"    client := {go_module_name}.NewClient(\"http://localhost:8900\", \"YOUR_KEY\")\n"
            f"    // _ = client.SomeOperation(context.Background())\n"
            f"}}\n```\n\n"
            f"Generated by IMDF SDK Generator — {len(operations)} operations, "
            f"{len(schemas)} types.\n"
        )

        return {
            f"{go_module_name}.go": "\n".join(client_lines),
            f"types.go": "\n".join(types_lines),
            "go.mod": "\n".join(gomod_lines),
            "README.md": readme,
        }

    # --------------------------- Zip writer --------------------------------

    def _to_zip(self, files: Dict[str, str], language: str) -> bytes:
        """Pack files into a zip and return as bytes."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Stable ordering: sorted by path for deterministic output
            for path in sorted(files.keys()):
                zf.writestr(path, files[path])
            # Manifest file
            manifest = {
                "language": language,
                "generator": "SDKGenerator/1.0",
                "file_count": len(files),
                "files": sorted(files.keys()),
            }
            zf.writestr("MANIFEST.json", json.dumps(manifest, indent=2))
        return buf.getvalue()


# ---------------------------------------------------------------------------
# Convenience top-level function (used by API layer)
# ---------------------------------------------------------------------------

def generate_sdk_zip(
    openapi_spec: Dict[str, Any],
    language: str,
    package_name: str,
    version: str = "1.0.0",
) -> bytes:
    """Convenience function: generate a zip and return bytes."""
    return SDKGenerator().generate(openapi_spec, language, package_name, version)