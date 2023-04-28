from typing import List, Dict, Callable

import requests
from rss_parser import Parser


def _parse_rss_xml(text: str) -> List[str]:
    parser = Parser(xml=text)
    feed = parser.parse()
    return feed.feed


def update_json_with_rss(podjsn: Dict[str, str], rss: str) -> None:
    items = _parse_rss_xml(rss)
    for item in items:
        if item.title not in podjsn:
            podjsn[item.title] = [item.link, item.publish_date]


def fetch_rss(urls: List[str]):
    """Generator: yields the content of urls"""
    for url in urls:
        # fetch RSS content
        resp = requests.get(url=url)
        if resp.status_code == requests.codes.ok:
            yield resp.text


def rss_iteration(urls: List[str], fetcher: Callable, putter: Callable) -> None:
    poddata = fetcher()
    before = len(poddata)
    print("Before:", before)
    for data in fetch_rss(urls):
        update_json_with_rss(poddata, data)
    after = len(poddata)
    if after != before:
        print("After:", after)
        putter(poddata)
