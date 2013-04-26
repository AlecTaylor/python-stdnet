'''Asynchronous binding for stdnet.

Backend Query
~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: BackendQuery
   :members:
   :member-order: bysource
'''
from inspect import isgeneratorfunction
from functools import partial

from .conf import settings

if settings.ASYNC_BINDINGS:
    try:
        from pulsar import is_async, async, multi_async, maybe_async, is_failure
    except ImportError:
        settings.ASYNC_BINDINGS = False
        
if not settings.ASYNC_BINDINGS:
    
    def is_async(result):
        return False
    
    def is_failure(result):
        return False
    
    def multi_async(data, **kwargs):
        return data
    
    def maybe_async(data):
        return data
    
    class async:
        
        def __call__(self, f):
            assert isgeneratorfunction(f), 'async decorator only for generator functions'
            def _(*args, **kwargs):
                res = tuple(f(*args, **kwargs))
                return res[-1] if res else None
            return _


def on_result(result, callback, errback=None):
    if is_async(result):
        return result.add_callback(callback, errback)
    elif is_failure(result):
        result.raise_all()
    else:
        return callback(result)
    
def on_error(result, callback):
    if is_async(result):
        return result.add_errback(callback)
    else:
        return result
    
    
class BackendQuery(object):
    '''Asynchronous query interface class which implements the database
queries specified by :class:`stdnet.odm.Query`.

.. attribute:: queryelem

    The :class:`stdnet.odm.QueryElement` to process.
    
.. attribute:: executed

    flag indicating if the query has been executed in the backend server
    
'''
    def __init__(self, queryelem, timeout=0, **kwargs):
        '''Initialize the query for the backend database.'''
        self.queryelem = queryelem
        self.expire = max(timeout, 10)
        self.timeout = timeout
        self.__count = None
        self.__slice_cache = {}
        # build the queryset without performing any database communication
        self._build(**kwargs)

    def __repr__(self):
        return self.queryelem.__repr__()
    
    def __str__(self):
        return str(self.queryelem)
    
    @property
    def session(self):
        return self.queryelem.session
    
    @property
    def backend(self):
        return self.queryelem.backend
    
    @property
    def meta(self):
        return self.queryelem.meta
    
    @property
    def model(self):
        return self.queryelem.model
    
    @property
    def executed(self):
        return self.__count is not None
    
    def cache(self):
        return self.__slice_cache
    
    def __len__(self):
        return self.execute_query()
    
    def count(self):
        return self.execute_query()

    def __contains__(self, val):
        self.execute_query()
        return self._has(val)
    
    def execute_query(self):
        if not self.executed:
            return on_result(self._execute_query(), self._got_count)
        return self.__count
    
    def __getitem__(self, slic):
        if isinstance(slic, slice):
            return self.items(slic)
        return on_result(self.items(), lambda r: r[slic])
    
    @async()
    def items(self, slic=None, callback=None):
        '''This function does the actual fetching of data from the backend
server matching this :class:`Query`. This method is usually not called directly,
instead use the :meth:`all` method or alternatively slice the query in the same
way you can slice a list or iterate over the query.'''
        key = None
        seq = self.cache().get(None)
        if slic:
            if seq is not None: # we have the whole query cached already
                yield seq[slic]
            else:
                key = (slic.start, slic.step, slic.stop)
        if seq is not None:
            yield seq
        else:
            result = yield self.execute_query()
            if result:
                items = yield self._items(slic)
            items = items or ()
            yield self._store_items(key, callback, items)
        
    def delete(self):
        with self.session.begin() as t:
            t.delete(self)
        return on_result(t.on_result, lambda _: t.deleted.get(self.meta))
    
    # VIRTUAL METHODS - MUST BE IMPLEMENTED BY BACKENDS
    
    def _has(self, val):    # pragma: no cover
        raise NotImplementedError
    
    def _items(self, slic):     # pragma: no cover
        raise NotImplementedError
    
    def _build(self, **kwargs):     # pragma: no cover
        raise NotImplementedError
    
    def _execute_query(self):       # pragma: no cover
        '''Execute the query without fetching data from server. Must
 be implemented by data-server backends.'''
        raise NotImplementedError
    
    # PRIVATE METHODS
    
    def _got_count(self, c):
        self.__count = c
        return c
    
    def _get_items(self, slic, result):
        if result:
            return self._items(slic)
        else:
            return ()
        
    def _store_items(self, key, callback, items):
        session = self.session
        seq = []
        model = self.model
        for el in items:
            if isinstance(el, model):
                session.add(el, modified=False)
            seq.append(el)
        self.__slice_cache[key] = seq
        return callback(seq) if callback else seq