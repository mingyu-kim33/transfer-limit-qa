"""tests/conftest.py

app/index.html은 이제 서버 없이 동작하는 완전한 정적 페이지다.
원장은 브라우저에 내장된 SQLite(sql.js)에 저장되므로, 테스트용으로는
파일을 서빙만 하는 단순 정적 서버만 있으면 된다. 각 테스트는 새
브라우저 컨텍스트(= 새 페이지 = 새 sql.js 인스턴스)를 받으므로
세션 id로 데이터를 분리할 필요도 없어졌다.
"""

import functools
import http.server
import socketserver
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from pages.transfer_page import TransferPage

APP_DIR = Path(__file__).resolve().parent.parent / "app"
PORT = 8899
BASE_URL = f"http://127.0.0.1:{PORT}/index.html"


@pytest.fixture(scope="session")
def server():
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(APP_DIR)
    )
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield BASE_URL
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def app(server, browser) -> TransferPage:
    context = browser.new_context()
    page = context.new_page()
    transfer_page = TransferPage(page, server)
    transfer_page.open()
    yield transfer_page
    context.close()
