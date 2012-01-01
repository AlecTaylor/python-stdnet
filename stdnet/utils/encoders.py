'''Classes used for encoding and decoding field values.'''
import json

from stdnet.utils import JSONDateDecimalEncoder, pickle, \
                         JSONDateDecimalEncoder, DefaultJSONHook,\
                         ispy3k, date2timestamp, timestamp2date
    

class Encoder(object):
    '''Virtaul class for encoding data in
:ref:`remote strcutures <structures-backend>`. It exposes two methods
for serializing and loading data to and from the data server.'''
    def dumps(self, x, logger = None):
        '''Serialize data for database'''
        raise NotImplementedError
    
    def loads(self, x, logger = None):
        '''Unserialize data from database'''
        raise NotImplementedError
    
        
    
class Default(Encoder):
    '''The default unicode encoder'''
    def __init__(self, charset = 'utf-8', encoding_errors = 'strict'):
        self.charset = charset
        self.encoding_errors = encoding_errors
        
    if ispy3k:
        def dumps(self, x, logger = None):
            if isinstance(x,bytes):
                return x
            else:
                return str(x).encode(self.charset,self.encoding_errors)
            
        def loads(self, x, logger = None):
            if isinstance(x,bytes):
                return x.decode(self.charset,self.encoding_errors)
            else:
                return str(x)
    
    else:
        def dumps(self, x, logger = None):
            if not isinstance(x,unicode):
                x = str(x)
            return x.encode(self.charset,self.encoding_errors)
            
        def loads(self, x, logger = None):
            if not isinstance(x,unicode):
                x = str(x)
            return x.decode(self.charset,self.encoding_errors)
    
    
class Bytes(Encoder):
    '''The binary unicode encoder'''
    def __init__(self, charset = 'utf-8', encoding_errors = 'strict'):
        self.charset = charset
        self.encoding_errors = encoding_errors
        
    def dumps(self, x, logger = None):
        if not isinstance(x,bytes):
            x = x.encode(self.charset,self.encoding_errors)
        return x
    
    loads = dumps


class NoEncoder(Encoder):
    '''A dummy encoder class'''
    def dumps(self, x, logger = None):
        return x
    
    def loads(self, x, logger = None):
        return x
    
    
class PythonPickle(Encoder):
    '''A safe pickle serializer. By default we use protocol 2 for compatibility
between python 2 and python 3.'''
    def __init__(self, protocol = 2):
        self.protocol = protocol
        
    def dumps(self, x, logger = None):
        if x is not None:
            try:
                return pickle.dumps(x,self.protocol)
            except:
                if logger:
                    logger.error('Could not serialize {0}'.format(x),
                                 exc_info = True)
    
    def loads(self, x, logger = None):
        if x is None:
            return x
        elif isinstance(x, bytes):
            try:
                return pickle.loads(x)
            except pickle.UnpicklingError:
                return None
        else:
            return x
    

class Json(Default):
    '''A JSON encoder for maintaning python types when dealing with
remote data structures.'''
    def __init__(self,
                 charset = 'utf-8',
                 encoding_errors = 'strict',
                 json_encoder = None,
                 object_hook = None):
        super(Json,self).__init__(charset, encoding_errors)
        self.json_encoder = json_encoder or JSONDateDecimalEncoder
        self.object_hook = object_hook or DefaultJSONHook
        
    def dumps(self, x, logger = None):
        s = json.dumps(x, cls=self.json_encoder)
        return s.encode(self.charset,self.encoding_errors)
    
    def loads(self, x, logger = None):
        s = x.decode(self.charset,self.encoding_errors)
        return json.loads(s, object_hook=self.object_hook)


class DateTimeConverter(Encoder):
    '''Convert to and from datetime.datetime and unix timestamps'''
    def dumps(self, value, logger = None):
        return date2timestamp(value)
    
    def loads(self, value, logger = None):
        return timestamp2date(value)
    

class DateConverter(DateTimeConverter):
    '''Convert to and from datetime.date and unix timestamps'''
    def loads(self, value, logger = None):
        return timestamp2date(value).date()
    