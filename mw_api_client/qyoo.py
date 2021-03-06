"""
mw_api_client.qyoo - handling multiple requests in one.

Example use:

.. code-block:: python

    >>> queue = mw.Queue.fromtitles(mywiki, ('Main Page', 'Home'))
    >>> pages = queue.categories()
    >>> pages
    [<Page Main Page>, <Page Home>]
    >>> pages[0].categories
    [<Page Category:Main Pages>]
    >>> pages[1].categories
    [<Page Category:Redirects>]

Use for efficiency in batch processing.
"""
from .page import Page, Revision, User
from .misc import GenericData

class Queue(object):
    """A Queue makes batch processing of similarly-structured information
    about wiki data easier by fetching all data in one request.
    """

    def __init__(self, wiki, things=[], converter=None):
        """Set up the Queue, optionally initialized with an iterable.

        ``converter`` is an optional function to call on every item in
        ``things``; Queue(mywiki, [bunch, of, things], func) is equivalent
        to Queue(mywiki, list(map([bunch, of, things], func))).
        """
        self._converter = (lambda i: i) if converter is None else converter
        self._things = list(map(self._converter, things))
        self.wiki = wiki

    @classmethod
    def fromtitles(cls, wiki, things=[]):
        """Set up the Queue, optionally initialized with an iterable,
        all of whose arguments will be converted to a Page if possible.
        """
        return cls(wiki, things, wiki.page)

    @classmethod
    def frompages(cls, wiki, things=[]):
        """Set up the Queue, typechecking each item in it as a Page."""
        def check_is_page(thing):
            """Check if an item is a page."""
            if not isinstance(thing, Page):
                raise TypeError('Item is not Page: ' + repr(thing))
            return thing
        return cls(wiki, things, check_is_page)

    @classmethod
    def fromrevisions(cls, wiki, things=[]):
        """Set up the Queue, typechecking each item in it as a Page."""
        def check_is_rev(thing):
            """Check if an item is a revision."""
            if not isinstance(thing, Revision):
                raise TypeError('Item is not Revision: ' + repr(thing))
            return thing
        return cls(wiki, things, check_is_rev)

    def _check_type(self, typeobj, attr=None):
        things = ''
        for thing in self:
            if not isinstance(thing, typeobj):
                raise TypeError('Item is not {}: {}'.format(
                    typeobj.__name__,
                    repr(thing)
                ))
            if attr is not None:
                things += str(getattr(thing, attr)) + '|'
        things.strip('|')
        return things

    def __iadd__(self, thing):
        """Add something to this Queue (optionally using += syntax)."""
        self._things += self._converter(thing)

    add = __iadd__

    def __add__(self, other):
        """Concatenate two Queues."""
        if not isinstance(other, type(self)):
            raise TypeError("Cannot concatenate 'Queue' and '"
                            + type(other).__name__
                            + "'")
        self += other._things
        return self

    def __iter__(self):
        """Iterate over Queue items."""
        return iter(self._things)

    def __repr__(self):
        return '<Queue of: ' + repr(self._things) + '>'

    __str__ = __repr__

    def _convert(self, iterable, key, cls1, cls2):
        """Convert a list of dictionaries to a list of ``cls1``s, whose ``key``
        attribute is a list of ``cls2``s.
        """
        result = []
        if isinstance(iterable, dict):
            iterable = iterable.values() #ugh when will format JSONv2 come out
        for i in iterable:
            tmp = []
            if '*' in i:
                i['content'] = i['*']
                del i['*']
            convertedi = cls1(self.wiki, **i)
            for j in i[key]:
                if '*' in j:
                    j['content'] = j['*']
                    del j['*']
                if cls2 == Revision:
                    tmp.append(cls2(self.wiki, convertedi, **j))
                else:
                    tmp.append(cls2(self.wiki, **j))
            setattr(convertedi, key, tmp)
            result.append(convertedi)
        return result

    def _mklist(self, params, key, cls1, cls2):
        """Centralize generation of API data."""
        last_cont = {}
        limitkey = 'limit'
        for k in params:
            if k.endswith('limit'):
                limitkey = k
                break
        result = []

        while 1:
            params.update(last_cont)
            data = self.wiki.request(**params)
            result.extend(self._convert(data['query']['pages'],
                                        key,
                                        cls1,
                                        cls2))
            if params[limitkey] == 'max' \
                   or len(data['query']['pages']) < params[limitkey]:
                if 'continue' in data:
                    last_cont = data['continue']
                    last_cont[limitkey] = self.wiki._wraplimit(params)
                else:
                    break
            else:
                break
        return result

    #time for more API methods :D
    def categories(self, limit='max', hidden=0, **evil):
        """Return a list of Pages with lists of categories represented as
        more Pages. The Queue must contain only Pages.

        The ``hidden`` parameter specifies whether returned categories must be
        hidden (1), must not be hidden (-1), or can be either (0, default).
        """
        #typecheck
        titles = self._check_type(Page, 'title')

        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'categories',
            'clprop': 'sortkey|timestamp|hidden',
            'clshow': ('hidden'
                       if hidden == 1
                       else ('!hidden'
                             if hidden == -1
                             else None)),
            'cllimit': int(limit) if limit != 'max' else limit
        }
        params.update(evil)
        return self._mklist(params, 'categories', Page, Page)

    def categoryinfo(self, **evil):
        """Return a list of Pages with category information. The Queue must
        contain only Pages.
        """
        titles = self._check_type(Page, 'title')

        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'categoryinfo',
        }
        params.update(evil)
        data = self.request(**params)
        result = []
        for page_data in data['query']['pages']:
            result.append(Page(self.wiki, **page_data))
            result[-1].__dict__.update(result[-1].categoryinfo)
            del result[-1].categoryinfo
        return result

    def contributors(self, limit='max', **evil):
        """Return a list of Users that contributed to Pages in this Queue.
        The Queue must contain only Pages.
        """
        titles = self._check_type(Page, 'title')

        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'contributors',
            'pclimit': limit,
        }
        params.update(evil)
        return self._mklist(params, 'contributors', Page, User)

    def deletedrevisions(self, limit='max', **evil):
        """Return a list of deleted Revisions of Pages in this Queue.
        The Queue must contain only Pages.
        """
        titles = self._check_type(Page, 'title')

        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'deletedrevisions',
            'drvlimit': limit,
        }
        params.update(evil)
        return self._mklist(params, 'deletedrevisions', Page, Revision)

    def duplicatefiles(self, limit='max', localonly=None, **evil):
        """Return a list of duplicates of files in this Queue.
        The Queue must contain only Pages.

        It is your responsibility to ensure that all of the Pages are treated
        as files in your wiki.
        """
        titles = self._check_type(Page, 'title')

        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'duplicatefiles',
            'dflimit': limit,
            'dflocalonly': localonly,
        }
        params.update(evil)
        return self._mklist(params, 'duplicatefiles', Page, Page)

    def extlinks(self, limit='max', protocol=None, query=None, **evil):
        """Return a list of external links used by Pages in this Queue.
        The Queue must contain only Pages.
        """
        titles = self._check_type(Page, 'title')

        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'extlinks',
            'elexpandurl': True,
            'ellimit': limit,
            'elprotocol': protocol,
            'elquery': query,
        }
        params.update(evil)
        return self._mklist(params, 'extlinks', Page, GenericData)

    def fileusage(self, limit='max', **evil):
        """Return a list of files used by Pages in this Queue.
        The Queue must contain only Pages.
        """
        titles = self._check_type(Page, 'title')

        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'fileusage',
            'fuprop': 'pageid|title|redirect',
            'fulimit': limit,
        }
        params.update(evil)
        return self._mklist(params, 'fileusage', Page, Page)

    def imageinfo(self, *_, **evil):
        """Not implemented due to the API module's insanity and pending deprecation."""
        raise NotImplementedError("This module is not implemented due to the \
corresponding API module's insanity, instability, and pending deprecation.")

    def images(self, limit='max', images=None, *_, **evil):
        """Return a list of images used by Pages in this Queue.
        The Queue must contain only Pages.
        """
        titles = self._check_type(Page, 'title')
        if not isinstance(images, str) and images is not None:
            images = list(iter(images))
            if isinstance(images[0], Page):
                images = list(page.title for page in images)
            else:
                images = list(str(page) for page in images)
            images = '|'.join(images)

        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'images',
            'imlimit': limit,
            'imimages': images,
        }
        params.update(evil)
        return self._mklist(params, 'images', Page, Page)

    def info(self, testactions=None, **evil):
        """Return a list of Pages in this Queue. with their info updated.
        The Queue must contain only Pages.
        """
        titles = self._check_type(Page, 'title')
        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'info',
            'inprop': 'protection|talkid|watched|watchers|visitingwatchers|\
notificationtimestamp|subjectid|url|readable|preload|displaytitle',
            'intestactions': (testactions
                              if isinstance(testactions, str)
                              else '|'.join(testactions))
        }
        params.update(evil)
        data = self.wiki.request(**params)
        result = []
        for page_data in data['query']['pages'].values():
            result.append(Page(self.wiki, getinfo=False, **page_data))
        return result

    def iwlinks(self, prefix, limit='max', title=None, **evil):
        """Return a list of interwiki links from Pages in this Queue.
        The Queue must contain only Pages.
        """
        titles = self._check_type(Page, 'title')
        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'iwlinks',
            'iwprop': 'url',
            'iwprefix': prefix,
            'iwtitle': title,
            'iwlimit': limit,
        }
        params.update(evil)
        return self._mklist(params, 'iwlinks', Page, GenericData)

    interwikilinks = iwlinks

    def langlinks(self, limit='max', lang=None, title=None, inlang=None, **evil):
        """Return a list of language links from Pages in this Queue.
        The Queue must contain only Pages.
        """
        titles = self._check_type(Page, 'title')
        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'langlinks',
            'llprop': 'url|langname|autonym',
            'lllang': lang,
            'lltitle': title,
            'llinlanguagecode': inlang,
            'lllimit': limit
        }
        params.update(evil)
        return self._mklist(params, 'langlinks', Page, GenericData)

    languagelinks = langlinks

    def links(self, limit='max', namespace=None, linktitles=None, **evil):
        """Return a list of Pages that Pages in this Queue link to.
        The Queue must contain only Pages.
        """
        titles = self._check_type(Page, 'title')
        params = {
            'action': 'query',
            'titles': titles,
            'prop': 'links',
            'plnamespace': namespace,
            'pltitles': (titles
                         if isinstance(titles, str)
                         else '|'.join(titles)),
            'pllimit': limit,
        }
        params.update(evil)
        return self._mklist(params, 'links', Page, Page)

    def linkshere(self, limit='max', namespace=None, **evil):
        """Return a list of Pages that link to Pages in this Queue.
        The Queue must contain only Pages.
        """
        titles = self._check_type(Page, 'title')
        params = {
            'action': 'query',
            'titles': titles,
            'lhprop': 'pageid|title|redirect',
            'lhnamespace': namespace,
            'lhlimit': limit,
        }
        params.update(evil)
        return self._mklist(params, 'linkshere', Page, Page)
