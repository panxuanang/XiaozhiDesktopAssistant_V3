from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import quote_plus

import pychrome
import requests

from ..action_log import record
from ..config import load_settings
from ..llm import AIClient
from ..paths import browser_profile_dir

DEBUG_PORT = 9222


def _port_open(port: int = DEBUG_PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _find_browser_executable() -> str:
    candidates = []
    if os.name == "nt":
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        candidates += [
            os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
    for name in ("chrome", "google-chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for path in candidates:
        if path and Path(path).exists():
            return path
    raise FileNotFoundError("未找到 Chrome 或 Edge。请先安装 Chrome/Edge 浏览器。")


def ensure_browser() -> pychrome.Browser:
    if not _port_open():
        exe = _find_browser_executable()
        flags = [
            exe,
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={browser_profile_dir()}",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
        ]
        if os.name == "nt":
            subprocess.Popen(flags, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 8
        while time.time() < deadline and not _port_open():
            time.sleep(0.2)
        if not _port_open():
            raise RuntimeError("浏览器启动成功但 DevTools 端口未就绪。")
    return pychrome.Browser(url=f"http://127.0.0.1:{DEBUG_PORT}")


def _tab():
    browser = ensure_browser()
    tabs = [t for t in browser.list_tab() if getattr(t, "type", "page") == "page"]
    if not tabs:
        tab = browser.new_tab("about:blank")
        try:
            tab.start()
        except Exception:
            pass
    else:
        tab = tabs[-1]
        for candidate in tabs:
            try:
                candidate.start()
                focus = candidate.Runtime.evaluate(expression="document.hasFocus()", returnByValue=True)
                if focus.get("result", {}).get("value") is True:
                    tab = candidate
                    break
            except Exception:
                continue
        try:
            tab.start()
        except Exception:
            pass
    try:
        tab.Runtime.enable()
        tab.Page.enable()
    except Exception:
        pass
    return tab


def _eval(expression: str):
    tab = _tab()
    result = tab.Runtime.evaluate(expression=expression, returnByValue=True, awaitPromise=True)
    return result.get("result", {}).get("value")


def browser_open(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    browser = ensure_browser()
    tab = browser.new_tab(url)
    try:
        tab.start()
        tab.Page.enable()
        tab.Page.navigate(url=url)
        time.sleep(1.2)
    except Exception:
        pass
    record("browser_open", {"url": url})
    return f"已打开：{url}"


def browser_search(query: str, engine: str = "bing") -> str:
    engines = {
        "bing": "https://www.bing.com/search?q=",
        "baidu": "https://www.baidu.com/s?wd=",
        "google": "https://www.google.com/search?q=",
    }
    url = engines.get(engine.lower(), engines["bing"]) + quote_plus(query)
    return browser_open(url)


def browser_current_page(max_chars: int = 30000) -> dict[str, str]:
    script = """(() => ({title: document.title, url: location.href, text: document.body ? document.body.innerText : ''}))()"""
    value = _eval(script) or {}
    return {
        "title": str(value.get("title", "")),
        "url": str(value.get("url", "")),
        "text": str(value.get("text", ""))[:max_chars],
    }


def summarize_current_webpage(question: str = "总结当前网页的主要内容") -> str:
    settings = load_settings()
    page = browser_current_page(settings.safety.max_webpage_chars_for_ai)
    ai = AIClient()
    result = ai.complete(
        f"任务：{question}\n网页标题：{page['title']}\n网页地址：{page['url']}\n\n网页正文：\n{page['text']}",
        system="你是网页阅读助手。只根据提供的网页正文总结或回答问题，不臆造网页没有的信息。",
    )
    record("summarize_current_webpage", {"url": page["url"], "question": question}, detail=result[:500])
    return result


def browser_click_text(text: str) -> str:
    needle = json.dumps(text)
    script = f"""(() => {{
      const target = {needle}.trim().toLowerCase();
      const els = [...document.querySelectorAll('button,a,[role="button"],input[type="button"],input[type="submit"],summary')];
      const el = els.find(e => ((e.innerText || e.value || e.getAttribute('aria-label') || '').trim().toLowerCase() === target))
              || els.find(e => ((e.innerText || e.value || e.getAttribute('aria-label') || '').trim().toLowerCase().includes(target)));
      if (!el) return {{ok:false, reason:'not found'}};
      el.scrollIntoView({{block:'center'}}); el.click(); return {{ok:true, tag:el.tagName, text:(el.innerText||el.value||'').trim()}};
    }})()"""
    result = _eval(script)
    record("browser_click_text", {"text": text}, detail=str(result))
    return json.dumps(result, ensure_ascii=False)


def browser_fill(field: str, value: str) -> str:
    f = json.dumps(field)
    v = json.dumps(value)
    script = f"""(() => {{
      const target = {f}.trim().toLowerCase();
      const candidates = [...document.querySelectorAll('input,textarea,[contenteditable="true"]')];
      const labelText = e => {{
        const id=e.id; let lab=id?document.querySelector(`label[for="${{CSS.escape(id)}}"]`):null;
        return [e.placeholder,e.name,e.getAttribute('aria-label'),lab?.innerText].filter(Boolean).join(' ').toLowerCase();
      }};
      const el = candidates.find(e => labelText(e) === target) || candidates.find(e => labelText(e).includes(target));
      if (!el) return {{ok:false, reason:'field not found'}};
      el.focus();
      if (el.isContentEditable) el.innerText={v}; else el.value={v};
      el.dispatchEvent(new Event('input',{{bubbles:true}})); el.dispatchEvent(new Event('change',{{bubbles:true}}));
      return {{ok:true}};
    }})()"""
    result = _eval(script)
    record("browser_fill", {"field": field, "value_len": len(value)}, detail=str(result))
    return json.dumps(result, ensure_ascii=False)


def browser_extract_tables(max_tables: int = 10) -> str:
    script = f"""(() => [...document.querySelectorAll('table')].slice(0,{max_tables}).map((t,ti)=>({{
      index:ti,
      rows:[...t.querySelectorAll('tr')].slice(0,100).map(r=>[...r.querySelectorAll('th,td')].map(c=>c.innerText.trim()))
    }})))()"""
    result = _eval(script) or []
    return json.dumps(result, ensure_ascii=False)[:50000]


def browser_download_by_text(text: str, download_dir: str) -> str:
    target = str(Path(download_dir).expanduser().resolve())
    tab = _tab()
    try:
        tab.Page.setDownloadBehavior(behavior="allow", downloadPath=target)
    except Exception:
        pass
    return browser_click_text(text) + f"\n下载目录：{target}"


def browser_upload_file(field: str, file_path: str) -> str:
    path = str(Path(file_path).expanduser().resolve())
    if not Path(path).exists():
        raise FileNotFoundError(path)
    tab = _tab()
    try:
        tab.DOM.enable()
    except Exception:
        pass
    f = json.dumps(field)
    expression = f"""(() => {{
      const target={f}.trim().toLowerCase();
      const candidates=[...document.querySelectorAll('input[type=\"file\"]')];
      const labelText=e=>{{const id=e.id; const lab=id?document.querySelector(`label[for=\"${{CSS.escape(id)}}\"]`):null; return [e.name,e.getAttribute('aria-label'),lab?.innerText].filter(Boolean).join(' ').toLowerCase();}};
      return candidates.find(e=>labelText(e)===target) || candidates.find(e=>labelText(e).includes(target)) || candidates[0] || null;
    }})()"""
    obj = tab.Runtime.evaluate(expression=expression, returnByValue=False).get("result", {})
    object_id = obj.get("objectId")
    if not object_id:
        return json.dumps({"ok": False, "reason": "file input not found"}, ensure_ascii=False)
    tab.DOM.setFileInputFiles(files=[path], objectId=object_id)
    record("browser_upload_file", {"field": field, "path": path})
    return json.dumps({"ok": True, "path": path}, ensure_ascii=False)


def browser_tables_to_excel(output_path: str = "桌面/网页表格.xlsx", max_tables: int = 10) -> str:
    """Extract visible HTML tables and save them to a local XLSX. No AI call."""
    import pandas as pd
    raw = json.loads(browser_extract_tables(max_tables=max_tables))
    if not raw:
        raise RuntimeError("当前网页没有检测到 HTML table。")
    target = Path(output_path).expanduser()
    if not target.is_absolute():
        from .files import resolve_user_path
        target = resolve_user_path(output_path)
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        for item in raw[:max_tables]:
            rows = item.get("rows", [])
            if not rows:
                continue
            width = max(len(r) for r in rows)
            norm = [r + [""] * (width - len(r)) for r in rows]
            header = norm[0]
            # Avoid duplicate/blank headers that pandas/openpyxl dislike.
            seen: dict[str, int] = {}
            cols = []
            for i, h in enumerate(header):
                base = str(h).strip() or f"列{i+1}"
                seen[base] = seen.get(base, 0) + 1
                cols.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
            df = pd.DataFrame(norm[1:], columns=cols)
            df.to_excel(writer, sheet_name=f"网页表格{int(item.get('index', 0))+1}"[:31], index=False)
    record("browser_tables_to_excel", {"output": str(target), "tables": len(raw)})
    return str(target)


def browser_search_results(query: str, engine: str = "bing", limit: int = 10) -> list[dict[str, str]]:
    """Search with a temporary local browser tab and return visible result links.

    No model/API call. The temporary tab avoids accidentally reading whichever tab the
    user currently has focused.
    """
    engines = {
        "bing": "https://www.bing.com/search?q=",
        "baidu": "https://www.baidu.com/s?wd=",
        "google": "https://www.google.com/search?q=",
    }
    url = engines.get(engine.lower(), engines["bing"]) + quote_plus(query)
    max_items = max(1, min(int(limit), 30))
    b = ensure_browser()
    tab = b.new_tab("about:blank")
    raw = []
    try:
        try:
            tab.start()
        except Exception:
            pass
        tab.Runtime.enable(); tab.Page.enable(); tab.Page.navigate(url=url)
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                state = tab.Runtime.evaluate(expression="document.readyState", returnByValue=True).get("result", {}).get("value")
                if state in {"interactive", "complete"}:
                    break
            except Exception:
                pass
            time.sleep(0.25)
        time.sleep(0.7)
        script = f"""(() => {{
          const host = location.hostname.toLowerCase();
          let anchors = [];
          if (host.includes('bing.')) anchors = [...document.querySelectorAll('li.b_algo h2 a')];
          else if (host.includes('google.')) anchors = [...document.querySelectorAll('a:has(h3)')];
          else if (host.includes('baidu.')) anchors = [...document.querySelectorAll('h3 a')];
          if (!anchors.length) anchors = [...document.querySelectorAll('a[href]')];
          const out = []; const seen = new Set();
          for (const a of anchors) {{
            const href = a.href || '';
            const title = (a.innerText || a.textContent || '').trim().replace(/\\s+/g,' ');
            if (!href.startsWith('http') || title.length < 4 || title.length > 220) continue;
            try {{
              const u = new URL(href); const h = u.hostname.toLowerCase();
              if (h.includes('bing.com') || h.includes('google.com') || h.includes('baidu.com')) {{
                if (!(h.includes('baidu.com') && u.pathname.includes('link'))) continue;
              }}
            }} catch(e) {{ continue; }}
            if (seen.has(href)) continue; seen.add(href);
            const parent = a.closest('li,div,article') || a.parentElement;
            const snippet = parent ? (parent.innerText || '').trim().replace(/\\s+/g,' ').slice(0,700) : '';
            out.push({{title, url:href, snippet}});
            if (out.length >= {max_items * 3}) break;
          }}
          return out;
        }})()"""
        raw = tab.Runtime.evaluate(expression=script, returnByValue=True).get("result", {}).get("value") or []
    finally:
        try:
            b.close_tab(tab)
        except Exception:
            try: tab.stop()
            except Exception: pass

    out: list[dict[str, str]] = []
    seen_hosts_paths: set[str] = set()
    for item in raw:
        url = str(item.get("url", "")).strip(); title = str(item.get("title", "")).strip()
        if not url or not title:
            continue
        try:
            from urllib.parse import urlsplit
            parsed = urlsplit(url); key = (parsed.netloc.lower() + parsed.path.rstrip("/")).lower()
        except Exception:
            key = url.lower()
        if key in seen_hosts_paths:
            continue
        seen_hosts_paths.add(key)
        out.append({"title": title, "url": url, "snippet": str(item.get("snippet", ""))})
        if len(out) >= max_items:
            break
    if not out and engine.lower() == "bing":
        # Public Bing RSS is a useful non-AI fallback when the rendered search page
        # changes structure or is blocked by a consent interstitial.
        try:
            import xml.etree.ElementTree as ET
            resp = requests.get(
                "https://www.bing.com/search",
                params={"q": query, "format": "rss"},
                headers={"User-Agent": "Mozilla/5.0 XiaozhiDesktopAssistant/0.3"},
                timeout=8,
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = (item.findtext("description") or "").strip()
                if title and link.startswith("http"):
                    out.append({"title": title, "url": link, "snippet": desc})
                    if len(out) >= max_items:
                        break
        except Exception:
            pass
    record("browser_search_results", {"query": query, "engine": engine, "count": len(out)})
    return out

def browser_read_url(url: str, max_chars: int = 50000, timeout_seconds: float = 10.0) -> dict[str, str]:
    """Open one URL in a temporary Chrome/Edge DevTools tab and extract visible text locally."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("只允许读取 http/https 网页。")
    b = ensure_browser()
    tab = b.new_tab("about:blank")
    try:
        try:
            tab.start()
        except Exception:
            pass
        tab.Runtime.enable()
        tab.Page.enable()
        tab.Page.navigate(url=url)
        deadline = time.time() + max(2.0, min(float(timeout_seconds), 30.0))
        while time.time() < deadline:
            try:
                state = tab.Runtime.evaluate(expression="document.readyState", returnByValue=True).get("result", {}).get("value")
                if state in {"interactive", "complete"}:
                    break
            except Exception:
                pass
            time.sleep(0.25)
        time.sleep(0.5)
        script = """(() => ({
          title: document.title || '',
          url: location.href || '',
          description: document.querySelector('meta[name="description"]')?.content || '',
          text: document.body ? document.body.innerText : ''
        }))()"""
        value = tab.Runtime.evaluate(expression=script, returnByValue=True).get("result", {}).get("value") or {}
        result = {
            "title": str(value.get("title", "")),
            "url": str(value.get("url", url)),
            "description": str(value.get("description", "")),
            "text": str(value.get("text", ""))[:max(1000, int(max_chars))],
        }
        record("browser_read_url", {"url": result["url"], "chars": len(result["text"])})
        return result
    finally:
        try:
            b.close_tab(tab)
        except Exception:
            try:
                tab.stop()
            except Exception:
                pass
