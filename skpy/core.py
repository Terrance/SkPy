class SkypeObj(object):
    """
    A basic Skype object.  Holds references to the parent :class:`.Skype` instance, and a raw object from the API.

    Attributes:
        attrs (tuple):
            List of defined fields for the class.  Used by :meth:`initAttrs` to create an :meth:`__init__` method.
        defaults (dict):
            Collection of default values when any keyword arguments are omitted from the constructor.
        skype (:class:`.Skype`):
            Parent Skype instance.
        raw (dict):
            Raw object, as provided by the API.
    """

    attrs = ()
    defaults = {}

    def __init__(self, skype=None, raw=None):
        """
        Instantiate a plain instance of this class, and store a reference to the Skype object for later API calls.

        Normally this method won't be called or implemented directly.

        Implementers should make use of :meth:`fromRaw` and the :meth:`initAttrs` decorator instead.

        Args:
            skype (Skype): parent Skype instance
            raw (dict): raw object, as provided by the API
        """
        self.skype = skype
        self.raw = raw

    @classmethod
    def rawToFields(cls, raw={}):
        """
        Convert the raw properties of an API response into class fields.  Override to process additional values.

        Args:
            raw (dict): raw object, as provided by the API

        Returns:
            dict: a collection of fields, with keys matching :attr:`attrs`
        """
        return {}

    @classmethod
    def fromRaw(cls, skype=None, raw={}):
        """
        Create a new instance based on the raw properties of an API response.

        This can be overridden to automatically create subclass instances based on the raw content.

        Args:
            skype (Skype): parent Skype instance
            raw (dict): raw object, as provided by the API

        Returns:
            SkypeObj: the new class instance
        """
        return cls(skype, raw, **cls.rawToFields(raw))

    def merge(self, other):
        """
        Copy properties from other into self, skipping ``None`` values.  Also merges the raw data.

        Args:
            other (SkypeObj): second object to copy fields from
        """
        for attr in self.attrs:
            if not getattr(other, attr, None) is None:
                setattr(self, attr, getattr(other, attr))
        if other.raw:
            if not self.raw:
                self.raw = {}
            self.raw.update(other.raw)

    def __str__(self):
        """
        Pretty print the object, based on the class' :attr:`attrs`.  Produces output something like::

            [<class name>]
            <attribute>: <value>

        Nested objects are indented as needed.
        """
        out = "[{0}]".format(self.__class__.__name__)
        for attr in self.attrs:
            value = getattr(self, attr)
            valStr = ("\n".join(str(i) for i in value) if isinstance(value, list) else str(value))
            out += "\n{0}{1}: {2}".format(attr[0].upper(), attr[1:], valStr.replace("\n", "\n  " + (" " * len(attr))))
        return out

    def __repr__(self):
        """
        Dump properties of the object into a Python-like statement, based on the class' :attr:`attrs`.

        The resulting string is an expression that should evaluate to a similar object, minus Skype connection.
        """
        reprs = []
        for attr in self.attrs:
            val = getattr(self, attr)
            if not val == self.defaults.get(attr):
                reprs.append("{0}={1}".format(attr, repr(val)))
        return "{0}({1})".format(self.__class__.__name__, ", ".join(reprs))


class SkypeObjs(object):
    """
    A basic Skype collection.  Acts as a container for objects of a given type.

    Attributes:
        synced (bool):
            Whether an initial set of objects has been cached.
        cache (dict):
            Storage of objects by identifier key.
    """

    def __init__(self, skype=None):
        """
        Create a new container object.  The :attr:`synced` state and internal :attr:`cache` are initialised here.

        Args:
            skype (Skype): parent Skype instance
        """
        self.skype = skype
        self.synced = False
        self.cache = {}

    def __getitem__(self, key):
        """
        Provide key lookups for items in the cache.  Subclasses may override this to handle not-yet-cached objects.
        """
        if key in self.cache:
            return self.cache[key]
        if not self.synced:
            self.sync()
        return self.cache[key]

    def __iter__(self):
        """
        Create an iterator for all objects (not their keys) in this collection.
        """
        if not self.synced:
            self.sync()
        for id in sorted(self.cache):
            yield self.cache[id]

    def sync(self):
        """
        A stub method that subclasses can implement to retrieve an initial set of objects.
        """
        self.synced = True

    def merge(self, obj):
        """
        Add a given object to the cache, or update an existing entry to include more fields.

        Args:
            obj (SkypeObj): object to add to the cache
        """
        if obj.id in self.cache:
            self.cache[obj.id].merge(obj)
        else:
            self.cache[obj.id] = obj
        return self.cache[obj.id]

    def __str__(self):
        return "[{0}]".format(self.__class__.__name__)

    def __repr__(self):
        return "{0}()".format(self.__class__.__name__)


class SkypeEnum(object):
    """
    A basic implementation for an enum.
    """

    def __init__(self, label, names=(), path=None):
        """
        Create a new enumeration.  The parent enum creates an instance for each item.

        Args:
            label (str): enum name
            names (list): item labels
            path (list): qualified parent name, for :func:`repr` output
        """
        self.label = label
        self.names = names
        self.path = path
        for name in names:
            setattr(self, name, self.__class__(name, path="{0}.{1}".format(path, label) if path else label))

    def __getitem__(self, item):
        """
        Provide list-style index lookups for each item.
        """
        return getattr(self, self.names[item])

    def __str__(self):
        """
        Show a list of items for the parent, or just the label for each item.
        """
        if self.names:
            return "[{0}<{1}>]\n{2}".format(self.__class__.__name__, self.label, "\n".join(self.names))
        else:
            return self.label

    def __repr__(self):
        """
        Show constructor for the parent, or just the qualified name for each item.
        """
        if self.names:
            return "{0}({1}, {2})".format(self.__class__.__name__, repr(self.label), repr(self.names))
        else:
            return "{0}.{1}".format(self.path, self.label) if self.path else self.label


class SkypeException(Exception):
    """
    A generic Skype-related exception.
    """


class SkypeApiException(SkypeException):
    """
    An exception thrown for errors specific to external API calls.

    Arguments will usually be of the form (``message``, ``response``).
    """
