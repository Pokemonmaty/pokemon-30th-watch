"""One scan per GitHub Actions run. No credentials are written to disk."""
import concurrent.futures
import datetime
import json
import os
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
import watch


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if '30th' in href.lower() and any(w in href.lower() for w in ('celebration', 'anniversary')):
                self.urls.append(href)


def discover_page(url):
    try:
        parser = Links()
        parser.feed(watch.http(url))
        root = urlsplit(url).hostname
        return [urlunsplit((p.scheme, p.netloc, p.path, '', ''))
                for href in parser.urls for p in [urlsplit(urljoin(url, href))]
                if p.scheme == 'https' and p.hostname == root and not p.username and not p.port
                and 'pokemon' in p.path.lower() and not p.path.startswith(('/en/', '/sk/'))]
    except Exception as e:
        print('Discovery failed:', urlsplit(url).hostname, type(e).__name__)
        return []


def main():
    config = json.loads(Path('config.json').read_text())
    live = os.environ.get('WATCH_ENABLED') == 'true'
    if live:
        if not os.environ.get('TELEGRAM_BOT_TOKEN') or not os.environ.get('TELEGRAM_CHAT_ID'):
            raise RuntimeError('Telegram secrets missing')
        me = watch.telegram('getMe')
        if me.get('username', '').lower() != 'matyaspokemonwatch_bot':
            raise RuntimeError('Unexpected bot identity')
    path = Path('state.json')
    state = json.loads(path.read_text()) if path.exists() else {'offers': {}, 'urls': []}
    urls = set(config['product_urls']) | set(state.get('urls', []))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for discovered in pool.map(discover_page, config['collection_urls']):
            urls.update(discovered)
    # Bound runtime and avoid silently claiming complete coverage.
    targets = sorted(urls)[:250]
    successes, failures, eligible = 0, [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for url, offer, error in pool.map(watch.check, targets):
            if error:
                failures.append(url)
                print('UNREADABLE', url, error)
                continue
            successes += 1
            name, price, status = offer
            print(status, str(price), name, url)
            qualifies = status in ('InStock', 'PreOrder', 'PreSale') and price < watch.LIMIT
            if qualifies:
                eligible.append(url)
            if not live:
                continue
            previous = state['offers'].get(url)
            if watch.should_notify(previous, price, status):
                label = 'SKLADEM' if status == 'InStock' else 'PŘEDOBJEDNÁVKA'
                message = f'{label}\n{name}\n{price} Kč (bez dopravy)\n{url}\nDostupnost podle údajů e-shopu; před nákupem ověř.'
                try:
                    watch.send(message)
                except Exception as error:
                    print('Notification failed:', type(error).__name__)
                    failures.append(url)
                    continue
            state['offers'][url] = [bool(qualifies), str(price), status]
    report = {'mode': 'LIVE' if live else 'VALIDATION ONLY — Telegram disabled',
              'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'targets': len(targets), 'readable': successes, 'failed': len(failures),
              'eligible': len(eligible), 'failed_urls': failures}
    Path('report.json').write_text(json.dumps(report, indent=2))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as f:
            f.write('## Scan result\n\n```json\n' + json.dumps(report, indent=2) + '\n```\n')
    if live:
        state['urls'] = targets
        # Persist after every scan, even partial failures; failed requests retain old observations.
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n')
    if successes == 0:
        raise RuntimeError('No readable products: monitoring is not functional')
    if failures:
        print('WARNING: Partial coverage; unreadable pages require adapters')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Run failed:', type(error).__name__)  # Never echo API URLs containing bot token.
        raise SystemExit(1)
