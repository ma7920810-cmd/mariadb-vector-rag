"""Offline fixtures shaped like real MediaWiki API responses (formatversion=2)."""

# Modern Wikipedia parser output: headings wrapped in div.mw-heading, citation
# superscripts, infobox/navbox tables, hatnotes, MathML and a references list.
ARTICLE_HTML = """
<div class="mw-content-ltr mw-parser-output" lang="en" dir="ltr">
<div class="shortdescription nomobile noexcerpt noprint searchaux" style="display:none">Organized collection of data</div>
<div role="note" class="hatnote navigation-not-searchable">For other uses, see Database (disambiguation).</div>
<table class="infobox"><tr><td>Infobox noise that must not be indexed</td></tr></table>
<p class="mw-empty-elt"></p>
<p>In computing, a <b>database</b> is an organized collection of data<sup id="cite_ref-1" class="reference"><a href="#cite_note-1">[1]</a></sup> managed by a
<a href="/wiki/Database_management_system">database management system</a> (DBMS). Databases are widely used.<sup class="noprint Inline-Template"><i>[citation needed]</i></sup> The DBMS lets users define, create and query data.</p>
<p>Small databases can be stored on a file system, while large databases are hosted on computer clusters or cloud storage. The design of databases spans formal techniques and practical considerations, including data modeling, efficient data representation and storage, query languages, security and privacy of sensitive data, and distributed computing issues, including supporting concurrent access and fault tolerance.</p>
<div class="mw-heading mw-heading2"><h2 id="Terminology">Terminology</h2></div>
<p>Formally, a "database" refers to a set of related data accessed through the use of a DBMS, which is an integrated set of computer software that allows users to interact with one or more databases and provides access to all of the data contained in the database. The size of a table grows as <span class="mwe-math-element"><span class="mwe-math-mathml-inline"><math alttext="{\\displaystyle O(n^{2})}"><semantics><mi>O</mi></semantics></math></span><img src="x.svg" class="mwe-math-fallback-image-inline" alt="{\\displaystyle O(n^{2})}"></span> in the worst case. Storage reached 10<sup>6</sup> records.</p>
<div class="mw-heading mw-heading3"><h3 id="Models">Models</h3></div>
<p>Databases and DBMSs can be categorized according to the database models that they support, such as relational or XML, the types of computer they run on, from a server cluster to a mobile phone, and the query languages used to access the database, such as SQL or XQuery.</p>
<ul><li>Relational model</li><li>Document model</li></ul>
<div class="mw-heading mw-heading2"><h2 id="See_also">See also</h2></div>
<ul><li><a href="/wiki/Comparison_of_database_tools">Comparison of database tools</a></li></ul>
<div class="mw-heading mw-heading2"><h2 id="References">References</h2></div>
<div class="reflist"><ol class="references"><li id="cite_note-1">Reference text that must be removed.</li></ol></div>
<p>Stray paragraph inside references.</p>
<div class="navbox"><table><tr><td>Navbox noise</td></tr></table></div>
</div>
"""

QUERY_RESPONSE = {
    "batchcomplete": True,
    "query": {
        "normalized": [{"fromencoded": False, "from": "database", "to": "Database"}],
        "redirects": [{"from": "DBMS", "to": "Database management system"}],
        "pages": [
            {"pageid": 8377, "ns": 0, "title": "Database", "lastrevid": 1001,
             "length": 80000,
             "pageprops": {"wikibase-shortdesc": "Organized collection of data"}},
            {"pageid": 18933632, "ns": 0, "title": "Database management system",
             "lastrevid": 2002, "length": 45000},
            {"pageid": 555, "ns": 0, "title": "Mercury", "lastrevid": 3003,
             "length": 3000, "pageprops": {"disambiguation": ""}},
            {"pageid": 777, "ns": 0, "title": "Tiny stub", "lastrevid": 4004,
             "length": 900},
            {"ns": 0, "title": "No such article xyz", "missing": True},
        ],
    },
}


def parse_response(page_id, title, rev_id, html=ARTICLE_HTML):
    return {"parse": {"title": title, "pageid": page_id, "revid": rev_id, "text": html}}
