#known bugs:
# fails to recognise this tag:
#   <link media="only screen and (max-device-width: 480px)"rel="stylesheet" type="text/css" href="http://static.storm8.com/rl/css/global.css?v=310"/>
#   (presumably because of the lack of whitespace before rel=)
# it is generally a bug that tags that do not fit the super regex are dumped as text
# the tag regex should be much more permissive, with subsequent regexes parsing attributes etc


import re
import itertools

r = r"""<(/?\w+)((\s+\w+(\s*=\s*(?:".*?"|'.*?'|[^'">\s]+))?)+\s*|\s*)/?>"""

tagRegex = re.compile(r"""(?x)
<
(?P<isEnd>/)?
(?P<tagName>[\w:-]+)
(?:
    (?P<attributes>
        (?:\s+[\w:-]+
            (?:\s*=\s*
                (?:"[^"]*"|'[^']*'|[^'">\s]+)
            )?
        )+\s*
    )?
    |\s*
)
(?P<isEmpty>/)?
\s*
>
|
(?P<text>.[^<]*)
""")

class Element(object):
    def __init__(self,parent=None,index=None):
        self._parent = parent
        self._index = index

    def forwards(self):
        i = self._index
        while True:
            try:
                yield(self._parent.elements[i])
                i+=1
            except StopIteration:
                break

    def backwards(self):
        i = self._index
        while i>=0:
            try:
                yield(self._parent.elements[i])
                i-=1
            except StopIteration:
                break

    def fetch(self,tagName = None, attrs = None):
        # next is forwards, skipping self
        g = (t for t in itertools.islice(self.forwards(),1,None) if not (type(t)==Tag and t.isEnd))
        if tagName:
            g = _filterByTagName(g,tagName)
        if type(attrs) == dict:
            for (n,v) in attrs.iteritems():
                g = _filterByAttribute(g,n,v)
        elif attrs!=None:
            g = _filterByClass(g,attrs)
        return g

    def first(self,tagName = None, attrs = None):
        return self.fetch(tagName,attrs).next()

    def backwardsByDepth(self,maxDepth=None,minDepth=0):

        def indexLast(v,l):
            for i in xrange(len(l)-1,-1,-1):
                if l[i]==v:
                    return i 
            raise ValueError()

        openTags = []
        reachedMinDepth = False
        for e in itertools.islice(self.backwards(),1,None):
            depth = len(openTags)
            if type(e)==Tag:
                if e.isEmpty: # empty tag
                    if depth>=minDepth and depth<=maxDepth:
                        reachedMinDepth = True
                        yield(e)
                elif e.isEnd: # close tag
                    if depth>=minDepth and depth<=maxDepth:
                        reachedMinDepth = True
                        yield(e)
                    openTags.append(e.name)
                else: # open tag
                    try:
                        index = indexLast(e.name,openTags)
                        del openTags[index]
                    except ValueError:
                        break
                    depth = len(openTags)
                    if depth<minDepth and reachedMinDepth:
                        break
                    elif depth>=minDepth and depth<=maxDepth:
                        reachedMinDepth = True
                        yield(e)
                    
            elif depth>=minDepth and depth<=maxDepth:
                reachedMinDepth = True
                yield(e)




class Text(Element):
    def __init__(self,match,parent=None,index=None):
        self.__match = match
        super(Text,self).__init__(parent,index)

    def __repr__(self):
        t = self.text
        if len(t)>50:
            t=t[:50]+"..."
        return "<Text:'%s'>" % t

    @property
    def text(self):
        return self.__match.group("text")

class Tag(Element):
    def __init__(self,match,parent=None,index=None):
        self.__match = match
        self.__attributes = None
        self.__empty = None
        super(Tag,self).__init__(parent,index)

    def __repr__(self):
        t = self.__match.group(0)
        if len(t)>50:
            t=t[:50]+"..."
        return "<Tag:'%s'>" % t

    @property
    def string(self):
        g = _filterByDepth(self.forwards(),minDepth=1,maxDepth=1)
        res = ""
        for text in [e.text for e in g if type(e)==Text]:
            res+=text
        return res

    def children(self):
        # in ideal circumstances we just need to track the depth of our own tag type
        kindDepth = 1
        # but we also track our tag depth with all tags, just incase of particularly bad html
        totalDepth = 1
        index = self._index+1
        while kindDepth>0 and totalDepth>0:
            e = self._parent.elements[index]
            if type(e)==Tag:
                if not e.isEmpty:
                    if e.isEnd:
                        totalDepth -= 1
                    else:
                        totalDepth += 1

                    if e.name==self.name:
                        if e.isEnd:
                            kindDepth -= 1
                        else:
                            kindDepth += 1

            if kindDepth>0 and totalDepth>0:
                yield e
            else:
                break
            index+=1

    def getAttribute(self,name):
        """ Get a list of values for the given attribute name """
        return (v for (n,v) in self.attributes if n==name)

    @property
    def attributes(self):
        """ Presents the attribute of a list of (name,value) tuples """
        if self.__attributes==None:
            self.__attributes = _attributesToList(self.__match.group("attributes"))
        return self.__attributes

    @property
    def name(self):
        return self.__match.group("tagName")

    @property
    def isEmpty(self):
        if self.__empty==None:
            if self.name.lower() in ["area","base","basefont","br","col","frame","hr","img","input","isindex","link","meta","param"]:
                self.__empty = True
            else:
                self.__empty = bool(self.__match.group("isEmpty"))
        return self.__empty

    @property
    def isEnd(self):
        return bool(self.__match.group("isEnd"))

def _filterByClass(g,className):
    return (t for t in iter(g) if type(t)==Tag and className in itertools.chain.from_iterable(map(str.split,t.getAttribute("class"))))

def _filterByTagName(g,tagName):
    if callable(tagName):
        tagNameFunc = tagName
    elif tagName == None:
        tagNameFunc = lambda x:True
    elif "match" in dir(tagName):
        tagNameFunc = tagName.match
    else:
        tagNameFunc =  tagName.__eq__
    return (t for t in iter(g) if type(t)==Tag and tagNameFunc(t.name))

# the idea here is to send a stream of tags in.. best to include the current tag
# make sure  this can work with siblings, recursive and non-recursive children
def _filterByDepth(g,maxDepth=None,minDepth=0):

    def indexLast(v,l):
        for i in xrange(len(l)-1,-1,-1):
            if l[i]==v:
                return i 
        raise ValueError()

    openTags = []
    danglingTags = []
    reachedMinDepth = False
    # should change depth after returning open tags but before returning close tags
    for e in iter(g):
        if type(e)==Tag and not e.isEnd and not e.isEmpty:
            openTags.append(e.name)
          
        #print "openTags: "+str(openTags)
        #print "danglingTags: "+str(danglingTags)

        depth = len(openTags)
        if depth>=minDepth:
            reachedMinDepth = True
            if maxDepth==None or depth<=maxDepth:
                yield(e)


        if type(e)==Tag and e.isEnd:
            try:
                del danglingTags[indexLast(e.name,danglingTags)]
                #print "removed %s from danglingTags" % e.name
            except ValueError:
                try:
                    index = indexLast(e.name,openTags)
                    # split opentags
                    dt = openTags[index+1:]
                    #if len(dt):
                    #   print "dangling: "+str(dt)
                    del openTags[index:]
                    danglingTags.extend(dt)
                except ValueError:
                    # close tag with no open tag?.. what to do
                    #print "close tag with no open tag?" + e.name 
                    pass
                if reachedMinDepth and len(openTags)<=minDepth:
                    break

        if reachedMinDepth and len(openTags)<minDepth:
            break






def _filterByAttribute(g,name=None,value=None):
    if callable(name):
        nameFunc = name
    elif name == None:
        nameFunc = lambda x:True
    elif "match" in dir(name):
        nameFunc = name.match
    else:
        nameFunc =  name.__eq__
    if callable(value):
        valueFunc = value
    elif value == None:
        valueFunc = lambda x:True
    elif "match" in dir(value):
        valueFunc = value.match
    else:
        valueFunc = value.__eq__
    return (t for t in iter(g) if type(t)==Tag and any(map(lambda i:nameFunc(i[0]) and valueFunc(i[1]),t.attributes)))

class HereticalSoup(object):
    def __init__(self,doc):
        def fetchAll(doc):
            for n,m in enumerate(tagRegex.finditer(doc)):
                if m.group("tagName"):
                    yield Tag(m,self,n)
                elif m.group("text"):
                    yield Text(m,self,n)
        self.elements = CachedIterable(fetchAll(doc))

    def fetch(self,tagName = None, attrs = None):
        g = (t for t in self.elements if not (type(t)==Tag and t.isEnd))
        if tagName:
            g = _filterByTagName(g,tagName)
        if type(attrs) == dict:
            for (n,v) in attrs.iteritems():
                g = _filterByAttribute(g,n,v)
        elif attrs!=None:
            g = _filterByClass(g,attrs)
        return g

    def first(self,tagName = None, attrs = None):
        return self.fetch(tagName,attrs).next()

    def fetchText(self,text=None):
        g = (e for e in self.elements if type(e)==Text)
        if "match" in dir(text):
            g = (e for e in g if text.match(e.text))
        if text:
            g = (e for e in g if e.text == text)
        return g

    def firstText(self,text=None):
        return self.fetchText(text).next()

    def __oldfetch(tagName = None, attrs = None, startIndex = None, endIndex = None):
        for e in filter(lambda e: type(e)==Tag,elements[startIndex:endIndex]):
            tag = e
            match = True
            if tagName and tag.name!=tagName:
                match = False
            if attrs:
                #parse attrs into a dict
                if type(attrs)==str:
                    #match str in class
                    # TODO only matches first class attribute, there may be more
                    try:
                        classValue = filter(lambda a: a[0]=="class",tag.attributes)[0][1]
                    except IndexError:
                        classValue = ""
                    if attrs not in classValue.split():
                        match = False
                elif "match" in dir(attrs):
                    classMatch = False 
                    #for c in tag.attributes["class"].split():
                    # TODO only matches first class attribute, there may be more
                    for c in filter(lambda a: a[0]=="class",tag.attributes)[0][1].split():
                        if attrs.match(c):
                            classMatch = True
                    if not classMatch:
                        match = False
                elif type(attrs)==dict:
                    #for each key,
                    for attrName,attrValue in attrs.iteritems():
                        try:
                            attribute = filter(lambda a:a[0]==attrName,tag.attributes)[0]
                            #if value param is a regex
                            if "match" in dir(attrValue):
                                # do a regex search
                                if not attrValue.match(attribute[1]):
                                    match = False
                            # else do a (string?) comparison
                            elif attribute[1]!=attrValue:
                                match = False
                        except IndexError:
                            match = False
            if match:
                #return some object... tagname, isempty, attr dict, match object
                yield tag

class CachedIterable(object):
    def __init__(self, iterable):
        self.__iter = iter(iterable)
        self.__list = []
    def __getitem__(self, index):
        for _ in range(index - len(self.__list) + 1):
            self.__list.append(self.__iter.next())
        return self.__list[index]


def _attributesToList(attributes):
    resultList = [] 
    if not attributes:
        return resultList
    #print "got attributes = " + attributes
    for a in re.finditer(r"""(?x)
            \s+(?P<name>[\w:-]+)
                (?:\s*=\s*
                    (?:"(?P<value_double_quotes>[^"]*)"|'(?P<value_single_quotes>[^']*)'|(?P<value_plain>[^'">\s]+))
                )?
        """,attributes):
        name = a.group("name")
        value = None
        # i could just "or" these together, but then I lose any distinction between a valueless attribute and an
        # attribute set to the empty string
        value = a.group("value_double_quotes")
        if value == None:
            value = a.group("value_single_quotes")
        if value == None:
            value = a.group("value_plain")
        resultList.append((name,value))
    return resultList


def oldFetch(doc, tagName = None, attrs = None):
    for m in tagRegex.finditer(doc):
        match = True
        if tagName and m.group("tagName")!=tagName:
            match = False
        if attrs:
            #parse attrs into a dict
            attrList = _attributesToList(m.group("attributes"))
            if type(attrs)==str:
                #match str in class
                try:
                    classAttr = filter(lambda a: a[0]=="class",attrList)[0][1]
                except IndexError:
                    classAttr = ""
                if attrs not in classAttr.split():
                    match = False
            elif "match" in dir(attrs):
                classMatch = False 
                for c in attrDict["class"].split():
                    if attrs.match(c):
                        classMatch = True
                if not classMatch:
                    match = False
            elif type(attrs)==dict:
                #for each key,
                for attrName,attrValue in attrs.iteritems():
                    if attrName not in attrDict:
                        match = False
                    else:
                        #if value param is a regex
                        if "match" in dir(attrValue):
                            valueMatch = False
                            # do a regex search
                            if not attrValue.match(attrDict[attrName]):
                                match = False
                        # else do a (string?) comparison
                        elif attrDict[attrName]!=attrValue:
                            match = False
        if match:
            yield Tag(match)
            #return some object... tagname, isempty, attr dict, match object


def oldMain():
    for m in tagRegex.finditer(h):
        print m.group(0) + ": " + str(m.groupdict()) + "\n"
        attributes = m.group("attributes")
        if attributes:
            print "got attributes = " + attributes
            for a in re.finditer(r"""(?x)
                    \s+(?P<name>[\w:-]+)
                        (?:\s*=\s*
                            (?:"(?P<value_double_quotes>[^"]*)"|'(?P<value_single_quotes>[^']*)'|(?P<value_plain>[^'">\s]+))
                        )?
                """,attributes):
                print "match:"+str(a.groupdict())
                print "name:"+a.group("name")
                print "value:"+(a.group("value_double_quotes") or a.group("value_single_quotes") or a.group("value_plain") or "")
        #print "%s : [%s]" % (m.group("tagName"), m.group("text"))


if __name__ == '__main__':
    h = file("/home/pix/dl/fight.html").read()
    soup = HereticalSoup(h)

    print [t for t in soup.first(attrs={'id':"cashType"}).backwardsByDepth(maxDepth=1)]
