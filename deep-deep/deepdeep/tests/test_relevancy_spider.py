from scrapy.crawler import CrawlerRunner
from scrapy.settings import Settings
from twisted.web.resource import Resource

from deepdeep.predictor import LinkClassifier
import deepdeep.settings
from deepdeep.spiders.relevancy import KeywordRelevancySpider
from .mockserver import MockServer
from .utils import text_resource, find_item, inlineCallbacks


def make_crawler(spider_cls, **extra_settings):
    settings = Settings()
    settings.setmodule(deepdeep.settings)
    settings.update(extra_settings)
    runner = CrawlerRunner(settings)
    return runner.create_crawler(spider_cls)


class GoodBadSite(Resource):
    def __init__(self):
        super().__init__()
        self.putChild(b'', text_resource(
            '<a href="/page-good">decent page</a> '
            '<a href="/page-good-2">ok page</a> '
            '<a href="/page-bad">awful page</a> '
        )())
        self.putChild(b'page-good', text_resource('good')())
        self.putChild(b'page-good-2', text_resource('awesome')())
        self.putChild(b'page-bad', text_resource('bad')())


@inlineCallbacks
def test_keywords_crawler(tmpdir):
    crawler = make_crawler(KeywordRelevancySpider)
    keywords_path = tmpdir.join('keywords.txt')
    with keywords_path.open('wt') as f:
        f.write('\n'.join(['good', 'awesome', '-bad']))
        f.write('\n')
    with MockServer(GoodBadSite) as s:
        root_url = s.root_url
        seeds_path = tmpdir.join('seeds.txt')
        with seeds_path.open('wt') as f:
            f.write('{}\n'.format(root_url))
        yield crawler.crawl(
            keywords_file=str(keywords_path),
            seeds_url=str(seeds_path),
            steps_before_switch=2,
        )
    assert crawler.stats.get_value('downloader/response_status_count/200') == 5
    assert crawler.stats.get_value('finish_reason') == 'finished'

    spider = crawler.spider
    link_clf = LinkClassifier(Q=spider.Q, link_vectorizer=spider.link_vectorizer,
                              page_vectorizer=spider.page_vectorizer)
    urls = link_clf.extract_urls(
        '<a href="/page-good">decent page</a>, '
        '<a href="/page-bad">awful page</a>',
        url='http://ex.com')
    print(urls)
    assert len(urls) == 2
    scores = {url: score for score, url in urls}
    assert scores['http://ex.com/page-good'] > scores['http://ex.com/page-bad']
