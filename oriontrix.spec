# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = Path(SPECPATH)
oriontrix_root = project_root / 'oriontrix'

datas = []

for md_file in oriontrix_root.rglob('skills/**/*.md'):
    rel_path = md_file.relative_to(project_root)
    datas.append((str(md_file), str(rel_path.parent)))

for jinja_file in oriontrix_root.rglob('agents/**/*.jinja'):
    rel_path = jinja_file.relative_to(project_root)
    datas.append((str(jinja_file), str(rel_path.parent)))

for xml_file in oriontrix_root.rglob('*.xml'):
    rel_path = xml_file.relative_to(project_root)
    datas.append((str(xml_file), str(rel_path.parent)))

for tcss_file in oriontrix_root.rglob('*.tcss'):
    rel_path = tcss_file.relative_to(project_root)
    datas.append((str(tcss_file), str(rel_path.parent)))

datas += collect_data_files('textual')

datas += collect_data_files('tiktoken')
datas += collect_data_files('tiktoken_ext')

datas += collect_data_files('litellm')

datas += collect_data_files('agents', includes=['**/*.md', '**/*.jinja', '**/*.json'])

hiddenimports = [
    # Core dependencies
    'litellm',
    'litellm.llms',
    'litellm.llms.openai',
    'litellm.llms.anthropic',
    'litellm.llms.vertex_ai',
    'litellm.llms.bedrock',
    'litellm.utils',
    'litellm.caching',

    # Textual TUI
    'textual',
    'textual.app',
    'textual.widgets',
    'textual.containers',
    'textual.screen',
    'textual.binding',
    'textual.reactive',
    'textual.css',
    'textual._text_area_theme',

    # Rich console
    'rich',
    'rich.console',
    'rich.panel',
    'rich.text',
    'rich.markup',
    'rich.style',
    'rich.align',
    'rich.live',

    # Pydantic
    'pydantic',
    'pydantic.fields',
    'pydantic_core',
    'email_validator',

    # Docker
    'docker',
    'docker.api',
    'docker.models',
    'docker.errors',

    # HTTP/Networking
    'httpx',
    'httpcore',
    'requests',
    'urllib3',
    'certifi',

    # Jinja2 templating
    'jinja2',
    'jinja2.ext',
    'markupsafe',

    # XML parsing
    'xmltodict',
    'defusedxml',
    'defusedxml.ElementTree',

    # Syntax highlighting
    'pygments',
    'pygments.lexers',
    'pygments.styles',
    'pygments.util',

    # Tiktoken (for token counting)
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',

    # Tenacity retry
    'tenacity',

    # CVSS scoring
    'cvss',

    # Oriontrix modules
    'oriontrix',
    'oriontrix.interface',
    'oriontrix.interface.main',
    'oriontrix.interface.cli',
    'oriontrix.interface.tui',
    'oriontrix.interface.tui.app',
    'oriontrix.interface.tui.history',
    'oriontrix.interface.tui.live_view',
    'oriontrix.interface.tui.messages',
    'oriontrix.interface.tui.renderers',
    'oriontrix.interface.tui.renderers.agent_message_renderer',
    'oriontrix.interface.tui.renderers.agents_graph_renderer',
    'oriontrix.interface.tui.renderers.base_renderer',
    'oriontrix.interface.tui.renderers.finish_renderer',
    'oriontrix.interface.tui.renderers.notes_renderer',
    'oriontrix.interface.tui.renderers.proxy_renderer',
    'oriontrix.interface.tui.renderers.registry',
    'oriontrix.interface.tui.renderers.reporting_renderer',
    'oriontrix.interface.tui.renderers.thinking_renderer',
    'oriontrix.interface.tui.renderers.todo_renderer',
    'oriontrix.interface.tui.renderers.user_message_renderer',
    'oriontrix.interface.tui.renderers.web_search_renderer',
    'oriontrix.interface.utils',
    'oriontrix.agents',
    'oriontrix.agents.factory',
    'oriontrix.agents.prompt',
    'oriontrix.config.models',
    'oriontrix.core',
    'oriontrix.core.agents',
    'oriontrix.core.execution',
    'oriontrix.core.inputs',
    'oriontrix.core.paths',
    'oriontrix.core.runner',
    'oriontrix.core.sessions',
    'oriontrix.report',
    'oriontrix.report.dedupe',
    'oriontrix.report.state',
    'oriontrix.report.writer',
    'oriontrix.runtime',
    'oriontrix.runtime.backends',
    'oriontrix.runtime.caido_bootstrap',
    'oriontrix.runtime.docker_client',
    'oriontrix.runtime.session_manager',
    'oriontrix.telemetry',
    'oriontrix.telemetry.logging',
    'oriontrix.tools',
    'oriontrix.tools.agents_graph.tools',
    'oriontrix.tools.finish.tool',
    'oriontrix.tools.notes.tools',
    'oriontrix.tools.proxy._calls',
    'oriontrix.tools.proxy.tools',
    'oriontrix.tools.python.tool',
    'oriontrix.tools.reporting.tool',
    'oriontrix.tools.scanner_runner',
    'oriontrix.tools.scanner_runner.tool',
    'oriontrix.tools.thinking.tool',
    'oriontrix.tools.todo.tools',
    'oriontrix.tools.web_search.tool',
    'oriontrix.skills',
]

hiddenimports += collect_submodules('litellm')
hiddenimports += collect_submodules('textual')
hiddenimports += collect_submodules('rich')
hiddenimports += collect_submodules('pydantic')
hiddenimports += collect_submodules('pygments')
hiddenimports += collect_submodules('oriontrix.core.net')

excludes = [
    # Sandbox-only packages
    'playwright',
    'playwright.sync_api',
    'playwright.async_api',
    'IPython',
    'ipython',
    'libtmux',
    'pyte',
    'openhands_aci',
    'openhands-aci',
    'numpydoc',

    # Google Cloud / Vertex AI
    'google.cloud',
    'google.cloud.aiplatform',
    'google.api_core',
    'google.auth',
    'google.oauth2',
    'google.protobuf',
    'grpc',
    'grpcio',
    'grpcio_status',

    # Test frameworks
    'pytest',
    'pytest_asyncio',
    'pytest_cov',
    'pytest_mock',

    # Development tools
    'mypy',
    'ruff',
    'black',
    'isort',
    'pylint',
    'pyright',
    'bandit',
    'pre_commit',

    # Unnecessary for runtime
    'tkinter',
    'matplotlib',
    'numpy',
    'pandas',
    'scipy',
    'PIL',
    'cv2',
]

a = Analysis(
    ['oriontrix/interface/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='oriontrix',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
