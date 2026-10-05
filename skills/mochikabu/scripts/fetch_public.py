#!/usr/bin/env python3
"""Fetch agent-selected public reports and timestamped JPY market quotes."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

MAX_BYTES = 40 * 1024 * 1024


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def download(url):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("Public downloads require HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "mochikabu/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Download exceeds 40 MiB")
        return data, response.geturl(), response.headers.get("Content-Type", "")


def parse_quote(payload, source_url, fetched_at):
    chart = payload.get("chart", {})
    if chart.get("error") or not chart.get("result"):
        raise ValueError("Market provider returned no usable quote")
    meta = chart["result"][0]["meta"]
    if meta.get("currency") != "JPY":
        raise ValueError("Quote currency is not JPY; use a sourced JPY conversion")
    price, timestamp = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if price is None or float(price) <= 0 or not timestamp:
        raise ValueError("Quote requires positive price and market timestamp")
    return {
        "ticker": meta.get("symbol"), "currency": "JPY", "current_price": float(price),
        "price_as_of": dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat(),
        "fetched_at": fetched_at, "source_url": source_url,
        "quote_type": "latest_regular_market_quote",
        "delay_status": "UNKNOWN", "realtime_verified": False,
        "exchange": meta.get("exchangeName"),
    }


def fetch_quote(ticker):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(ticker, safe="") + "?interval=1m&range=1d"
    data, final_url, _ = download(url)
    return parse_quote(json.loads(data), final_url, utc_now())


def xbrl_facts(data):
    root = ET.fromstring(data)
    facts = []
    for node in root.iter():
        if "contextRef" in node.attrib:
            facts.append({"tag": node.tag, "context_ref": node.attrib["contextRef"],
                          "unit_ref": node.attrib.get("unitRef"), "decimals": node.attrib.get("decimals"),
                          "scale": node.attrib.get("scale"), "sign": node.attrib.get("sign"),
                          "value": "".join(node.itertext()).strip()})
    contexts = [ET.tostring(n, encoding="unicode") for n in root.iter() if n.tag.endswith("}context")]
    units = [ET.tostring(n, encoding="unicode") for n in root.iter() if n.tag.endswith("}unit")]
    return {"facts": facts, "contexts": contexts, "units": units}


def extract_report(data, kind):
    if kind == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return {"status": "OPEN", "reason": "PDF saved; pypdf unavailable. Agent must read/render the original."}
        reader = PdfReader(io.BytesIO(data))
        pages = [{"page": i + 1, "text": p.extract_text() or ""} for i, p in enumerate(reader.pages)]
        return {"status": "EXTRACTED" if any(p["text"].strip() for p in pages) else "OPEN", "pages": pages}
    if kind == "xbrl":
        return {"status": "EXTRACTED", **xbrl_facts(data)}
    if kind == "zip":
        documents = []
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = [info for info in archive.infolist() if info.filename.lower().endswith((".xbrl", ".xml", ".xhtml"))]
            if sum(info.file_size for info in entries) > 100 * 1024 * 1024:
                raise ValueError("Expanded XBRL package exceeds 100 MiB")
            for info in entries:
                try:
                    documents.append({"member": info.filename, **xbrl_facts(archive.read(info))})
                except ET.ParseError:
                    continue
        return {"status": "EXTRACTED" if any(d["facts"] for d in documents) else "OPEN", "documents": documents}
    if kind == "html":
        return {"status": "EXTRACTED", "html": data.decode("utf-8", errors="replace")}
    raise ValueError("Report format must be pdf, xbrl, zip or html")


def collect(config, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {"currency": "JPY", "fetched_at": utc_now(), "companies": [], "status": "completed"}
    companies = [config["company"], *config.get("peers", [])]
    safe_ids = [re.sub(r"[^A-Za-z0-9_-]", "_", str(c["id"])) for c in companies]
    if len(safe_ids) != len(set(safe_ids)):
        raise ValueError("Company IDs must be distinct after filename normalization")
    for company in companies:
        record = {"id": company["id"], "name": company["name"], "ticker": company.get("ticker"), "reports": []}
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(company["id"]))
        if company.get("ticker"):
            try:
                record["market"] = fetch_quote(company["ticker"])
            except Exception as error:
                record["market"] = {"status": "failed", "error": str(error)}
                result["status"] = "partial"
        else:
            record["market"] = {"status": "OPEN", "reason": "No listed ticker"}
            result["status"] = "partial"
        for i, report in enumerate(company.get("reports", [])):
            evidence = {"source_url": report["url"], "publication_date": report.get("publication_date"),
                        "period": report.get("period"), "format": report["format"]}
            try:
                if report["format"] not in ("pdf", "xbrl", "zip", "html"):
                    raise ValueError("Unsupported report format")
                data, final_url, content_type = download(report["url"])
                raw_path = output_dir / f"{safe_id}_{i}.{report['format']}"
                raw_path.write_bytes(data)
                extracted = extract_report(data, report["format"])
                text_path = output_dir / f"{safe_id}_{i}.extracted.json"
                text_path.write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")
                evidence.update(status=extracted["status"], final_url=final_url, fetched_at=utc_now(),
                                content_type=content_type, raw_path=str(raw_path.resolve()),
                                extraction_path=str(text_path.resolve()), sha256=hashlib.sha256(data).hexdigest())
                if extracted["status"] == "OPEN":
                    result["status"] = "partial"
            except Exception as error:
                evidence.update(status="failed", error=str(error))
                result["status"] = "partial"
            record["reports"].append(evidence)
        if not record["reports"]:
            result["status"] = "partial"
        result["companies"].append(record)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, help="Agent-generated company, peers and official report URLs")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.request).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    result = collect(config, output_dir)
    manifest = output_dir / "manifest.json"
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "companies": len(result["companies"]), "artifact_path": str(manifest.resolve())}))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
