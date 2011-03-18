from stdnet import test
from stdnet.utils import populate
from stdnet.exceptions import QuerySetError
from stdnet.orm import model_to_dict

from examples.models import Instrument, Fund, Position


class TestInspectionAndComparison(test.TestCase):
    
    def setUp(self):
        '''Create Instruments and Funds'''
        orm = self.orm
        orm.register(Instrument)
        orm.register(Fund)
        orm.register(Position)
        
    def testSimple(self):
        d = model_to_dict(Instrument)
        self.assertFalse(d)
        inst = Instrument(name = 'erz12', type = 'future', ccy = 'EUR').save()
        d = model_to_dict(inst)
        self.assertTrue(len(d),3)
        
    def testEqual(self):
        inst = Instrument(name = 'erz12', type = 'future', ccy = 'EUR').save()
        id = inst.id
        b = Instrument.objects.get(id = id)
        self.assertEqual(b.id,id)
        self.assertTrue(inst == b)
        self.assertFalse(inst != b)
        f = Fund(name = 'bla', ccy = 'EUR').save()
        self.assertFalse(inst == f)
        self.assertTrue(inst != f)
        
    def testNotEqual(self):
        inst = Instrument(name = 'erz12', type = 'future', ccy = 'EUR').save()
        inst2 = Instrument(name = 'edz14', type = 'future', ccy = 'USD').save()
        id = inst.id
        b = Instrument.objects.get(id = id)
        self.assertEqual(b.id,id)
        self.assertFalse(inst2 == b)
        self.assertTrue(inst2 != b)
        
    def testHash(self):
        '''Test model instance hash'''
        inst = Instrument(name = 'erz12', type = 'future', ccy = 'EUR')
        self.assertRaises(TypeError,hash, inst)
        inst.save()
        h = hash(inst)
        self.assertTrue(h)
        
    def testUniqueId(self):
        '''Test model instance unique id across different model'''
        inst = Instrument(name = 'erz12', type = 'future', ccy = 'EUR')
        self.assertRaises(inst.DoesNotExist, lambda : inst.uuid)
        inst.save()
        v = inst.uuid.split('.') # <<model hash>>.<<instance id>>
        self.assertEqual(len(v),2)
        self.assertEqual(v[0],inst._meta.hash)
        self.assertEqual(v[1],str(inst.id))

        