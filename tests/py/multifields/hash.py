'''tests for odm.HashField'''
from stdnet.utils import test, populate, zip, iteritems, to_string

from examples.models import Dictionary

from .struct import MultiFieldMixin
        
keys = populate('string', 200)
values = populate('string', 200, min_len=20, max_len=300)


class TestHashField(test.TestCase, MultiFieldMixin):
    multipledb = 'redis'
    model = Dictionary
    
    def setUp(self):
        self.names = populate('string', size=10)
        self.defaults = {'name': self.names[0]}
        self.name = self.names[1]
        self.data = dict(zip(keys, values))
    
    def adddata(self, d):
        yield d.data.update(self.data)
        size = yield d.data.size()
        self.assertEqual(len(self.data), size)
    
    def create(self, fill=False):
        with self.session().begin() as t:
            d = t.add(self.model(name=self.name))
        yield t.on_result
        if fill:
            yield d.data.update(self.data)
        yield d
        
    def test_update(self):
        d = yield self.create(True)
        data = d.data
        self.assertTrue(data.is_field)
        self.assertEqual(data.session, d.session)
        self.assertEqual(data.cache.cache, None)
        items = yield data.items()
        self.assertTrue(data.cache.cache)
        self.assertEqual(data.cache.cache, items)
    
    def test_add(self):
        d = yield self.create()
        self.assertTrue(d.session)
        self.assertTrue(d in d.session)
        with d.session.begin() as t:
            t.add(d)
            for k, v in iteritems(self.data):
                d.data.add(k, v)
            size = yield d.data.size()
            self.assertEqual(size, 0)
        yield t.on_result
        size = yield d.data.size()
        self.assertEqual(len(self.data), size)

    def testKeys(self):
        d = yield self.fill()
        for k in d.data:
            self.data.pop(k)
        self.assertEqual(len(self.data),0)
    
    def testItems(self):
        d = yield self.fill()
        data = self.data.copy()
        items = d.data.items()
        for k, v in items:
            self.assertEqual(v, data.pop(k))
        self.assertEqual(len(data), 0)
        
    def testValues(self):
        d = yield self.fill()
        values = list(d.data.values())
        self.assertEqual(len(self.data),len(values))
        
    def createN(self):
        with self.model.objects.session().begin() as t:
            for name in self.names:
                t.add(self.model(name=name))
        yield t.on_result
        # Add some data to dictionaries
        qs = yield self.model.objects.query().all()
        with self.model.objects.session().begin() as t:
            for m in qs:
                t.add(m.data)
                m.data['ciao'] = 'bla'
                m.data['hello'] = 'foo'
                m.data['hi'] = 'pippo'
                m.data['salut'] = 'luna'
        yield t.on_result
        
    def testloadNotSelected(self):
        '''Get the model and check that no data-structure data
 has been loaded.'''
        yield self.createN()
        cache = self.model._meta.dfields['data'].get_cache_name()
        for m in self.model.objects.query():
            data = getattr(m,cache,None)
            self.assertFalse(data)
        
    def test_load_related(self):
        '''Use load_selected to load stastructure data'''
        yield self.createN()
        cache = self.model._meta.dfields['data'].get_cache_name()
        for m in self.model.objects.query().load_related('data'):
            self.assertTrue(m.data.cache.cache)