"""Deployment draft. Live shop adapters must be validated before relying on alerts."""
import argparse
from urllib.parse import urljoin
import datetime as dt
import json
import logging
import os
import re
import sqlite3
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

LOG = logging.getLogger('watch')
LIMIT = Decimal('4000')


def http(url, payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    h = {'User-Agent': 'PokemonAvailabilityWatch/0.1', 'Cache-Control': 'no-cache'}
    if data is not None:
        h['Content-Type'] = 'application/json'
    h.update(headers or {})
    # Callers deliberately log only exception types, never credential-bearing URLs.
    with urlopen(Request(url, data=data, headers=h), timeout=20) as response:
        body = response.read(4_000_001)
        if len(body) > 4_000_000:
            raise ValueError('Response too large')
        return body.decode('utf-8', errors='replace')


def telegram(method, payload=None):
    token = os.environ['TELEGRAM_BOT_TOKEN']
    result = json.loads(http('https://api.telegram.org/bot' + token + '/' + method, payload))
    if not result.get('ok'):
        raise RuntimeError('Telegram request failed')
    return result['result']


def send(text):
    telegram('sendMessage', {'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': text})


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text).lower())
                   if not unicodedata.combining(c))


def matches(name):
    name = normalize(name)
    return ('30th' in name and ('celebration' in name or 'anniversary' in name)
            and ('pokemon' in name or 'celebration' in name or 'anniversary' in name)
            and not any(w in name for w in ('case', 'empty', 'prazdn', 'obal', 'rozbalen', 'opened')))


class JSONLD(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.buffer = ''
        self.docs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
            self.active = True
            self.buffer = ''

    def handle_data(self, data):
        if self.active:
            self.buffer += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            self.active = False
            try:
                self.docs.append(json.loads(self.buffer))
            except ValueError:
                pass


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def offer_from_html(html):
    parser = JSONLD()
    parser.feed(html)
    found = []
    for product in nodes(parser.docs):
        types = product.get('@type', [])
        types = [types] if isinstance(types, str) else types
        if 'Product' not in types or not matches(product.get('name', '')):
            continue
        offers = product.get('offers', [])
        offers = [offers] if isinstance(offers, dict) else offers
        for offer in offers:
            if offer.get('priceCurrency') != 'CZK':
                continue
            try:
                price = Decimal(str(offer['price']).replace(' ', '').replace('\u00a0', '').replace(',', '.'))
            except (KeyError, InvalidOperation):
                continue
            if not price.is_finite() or price <= 0:
                continue
            availability = str(offer.get('availability', '')).rstrip('/').rsplit('/', 1)[-1]
            if availability not in ('InStock', 'PreSale', 'OutOfStock', 'SoldOut', 'PreOrder', 'BackOrder', 'Discontinued'):
                continue
            condition = str(offer.get('itemCondition', product.get('itemCondition', 'NewCondition'))).rsplit('/', 1)[-1]
            if condition != 'NewCondition':
                continue
            found.append((product['name'], price, availability))
    # Ambiguous pages containing several products/offers need a shop-specific adapter.
    unique = set(found)
    if len(unique) != 1:
        raise ValueError('Missing or ambiguous product data; adapter required')
    return unique.pop()


def check(url):
    try:
        name, price, stock = offer_from_html(http(url))
        return url, (name, price, stock), None
    except Exception as error:
        return url, None, type(error).__name__


def should_notify(previous, price, stock):
    eligible = stock in ('InStock', 'PreOrder', 'PreSale') and price < LIMIT
    return eligible and (previous is None or not previous[0] or
                         stock != previous[2] or price < Decimal(previous[1]))

