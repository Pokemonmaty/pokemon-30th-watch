import unittest
from decimal import Decimal
from watch import matches, should_notify, offer_from_html
import json

class Tests(unittest.TestCase):
    def test_collection(self):
        self.assertTrue(matches('Pokemon 30th Anniversary Binder Collection'))
        self.assertTrue(matches('Pokemon 30th Celebration Booster'))
        self.assertFalse(matches('Pokemon 25th Celebration ETB'))
        self.assertFalse(matches('Pokemon 30th empty box'))

    def test_stock_preorder_price(self):
        self.assertTrue(should_notify(None, Decimal('3999'), 'PreOrder'))
        self.assertTrue(should_notify(None, Decimal('3999'), 'InStock'))
        self.assertFalse(should_notify(None, Decimal('4000'), 'InStock'))
        self.assertFalse(should_notify(None, Decimal('999'), 'OutOfStock'))

    def test_dedup_and_transition(self):
        self.assertFalse(should_notify([True, '999', 'PreOrder'], Decimal('999'), 'PreOrder'))
        self.assertTrue(should_notify([True, '999', 'PreOrder'], Decimal('999'), 'InStock'))
        self.assertTrue(should_notify([False, '999', 'OutOfStock'], Decimal('999'), 'InStock'))
        self.assertTrue(should_notify([True, '999', 'InStock'], Decimal('899'), 'InStock'))

    def test_parser(self):
        data = {'@type':'Product', 'name':'Pokemon 30th Celebration Booster',
                'offers':{'price':'399', 'priceCurrency':'CZK', 'availability':'https://schema.org/PreOrder'}}
        html = '<script type="application/ld+json">'+json.dumps(data)+'</script>'
        self.assertEqual(offer_from_html(html)[2], 'PreOrder')
        for currency in ('EUR', ''):
            data['offers']['priceCurrency'] = currency
            with self.assertRaises(ValueError):
                offer_from_html('<script type="application/ld+json">'+json.dumps(data)+'</script>')

if __name__ == '__main__':
    unittest.main()
