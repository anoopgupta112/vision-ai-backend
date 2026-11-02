"""Regression tests for audited search, analytics, drafts, and URL boundaries."""
import copy
import socket
import time
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from app.projects.reddit_leads.api import routes
from app.projects.reddit_leads.models import storage
from app.projects.reddit_leads.services import reddit_searcher as search
from app.projects.reddit_leads.services import safe_fetch
from app.projects.reddit_leads.services import post_evaluator as evaluator
from app.projects.reddit_leads.services import comment_generator as comments
from app.projects.reddit_leads.services.ai_client import RedditAIClientError


def raw_post(i='p1', **fields):
    return dict(id=i, permalink='/r/SaaS/comments/%s/topic/' % i,
                title='Looking for a support tool', selftext='Need support software',
                subreddit='SaaS', created_utc=time.time()-3600, score=1, num_comments=2, **fields)


@pytest.fixture
def providers():
    with patch.object(search, '_query_pullpush', return_value=[] ) as pull, patch.object(search, '_query_reddit_public', return_value=[]) as reddit:
        yield pull, reddit


def test_date_and_subreddit_filters_apply_to_every_result(providers):
    pull, _ = providers
    good, old, other = raw_post(), raw_post('old'), raw_post('other')
    old['created_utc'] = time.time()-365*86400
    other['subreddit'] = 'unrelated'
    pull.return_value = [old, other, good]
    result = search.search_reddit_discussions(['support'], ['SaaS'], date_range='past_week')
    assert [p['post_id'] for p in result] == ['p1']
    assert pull.call_args.kwargs['subreddit'] == 'saas'
    assert pull.call_args.kwargs['after'] > old['created_utc']


def test_broad_fallback_has_same_cap_dedup_and_validation(providers):
    pull, _ = providers
    pull.side_effect = [[raw_post('a')], [raw_post('a'), raw_post('b'), raw_post('c')]]
    result = search.search_reddit_discussions(['looking for support'], max_candidates=2)
    assert [p['post_id'] for p in result] == ['a','b']


@pytest.mark.parametrize('url', ['https://example.com/r/SaaS/comments/p1/', '//example.com/path',
    'https://reddit.com@evil.test/r/SaaS/comments/p1/', 'javascript:alert(1)',
    'https://reddit.com:444/r/SaaS/comments/p1/', 'https://reddit.com/login'])
def test_invalid_source_urls_rejected(url):
    assert search.reddit_post_url(url) is None


def test_source_url_validation_does_not_claim_post_was_verified(providers):
    providers[0].return_value = [raw_post(), raw_post()]
    result = search.search_reddit_discussions(['support'])
    assert len(result) == 1
    assert result[0]['source_url_validated'] is True
    assert result[0]['is_verified_url'] is False


def test_provider_outage_is_not_a_successful_empty_scan(providers):
    providers[0].side_effect = OSError('offline')
    providers[1].side_effect = OSError('offline')
    with pytest.raises(search.RedditSearchError):
        search.search_reddit_discussions(['support'])


def test_empty_results_and_partial_outage_are_distinct(providers):
    pull, reddit = providers
    assert search.search_reddit_discussions(['support']).diagnostics['successful_requests'] == 1
    pull.side_effect = OSError('offline')
    reddit.return_value = [raw_post()]
    result = search.search_reddit_discussions(['support'])
    assert len(result) == 1
    assert result.diagnostics['warnings']


@pytest.mark.parametrize('address', ['127.0.0.1', '10.1.2.3', '169.254.169.254', '::1', 'fe80::1', '::ffff:127.0.0.1'])
def test_product_fetch_rejects_nonpublic_dns_answers(address):
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 80))]
    with patch.object(safe_fetch.socket, 'getaddrinfo', return_value=answers), patch.object(safe_fetch.socket, 'create_connection') as connect:
        with pytest.raises(safe_fetch.UnsafeURL):
            safe_fetch.fetch_public_text('http://product.example/')
        connect.assert_not_called()


def test_private_redirect_is_checked_and_connection_is_pinned():
    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34',80))]
    private = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1',80))]
    response = MagicMock(status=302)
    response.getheader.return_value = 'http://127.0.0.1/private'
    with patch.object(safe_fetch.socket, 'getaddrinfo', side_effect=[public,private]), patch.object(safe_fetch.socket, 'create_connection') as connect, patch.object(safe_fetch.http.client,'HTTPConnection') as connection:
        connection.return_value.getresponse.return_value=response
        with pytest.raises(safe_fetch.UnsafeURL):
            safe_fetch.fetch_public_text('http://product.example/')
        connect.assert_called_once_with(('93.184.216.34',80), timeout=6)


def test_oversized_product_page_rejected():
    answer=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',80))]
    with patch.object(safe_fetch.socket,'getaddrinfo',return_value=answer),patch.object(safe_fetch.socket,'create_connection'),patch.object(safe_fetch.http.client,'HTTPConnection') as connection:
        connection.return_value.getresponse.return_value.status=200
        connection.return_value.getresponse.return_value.read.return_value=b'x'*11
        with pytest.raises(ValueError,match='too large'):
            safe_fetch.fetch_public_text('http://product.example',max_bytes=10)


def test_reply_failure_is_explicit_instead_of_an_invented_testimonial():
    with patch.object(comments,'complete_json',side_effect=RuntimeError('outage')):
        with pytest.raises(RedditAIClientError):
            comments.generate_comment_drafts_for_post('TestProduct',{}, {})
        posts=comments.batch_generate_comments('TestProduct',{},[{'post_id':'p1'}])
    assert posts[0]['comment_drafts']=={}
    assert posts[0]['draft_error']


def test_missing_ai_reply_fields_are_not_fabricated():
    with patch.object(comments,'complete_json',return_value={'helpful':'Actual useful advice'}):
        with pytest.raises(RedditAIClientError):
            comments.generate_comment_drafts_for_post('TestProduct',{}, {})


def test_evaluator_handles_empty_pain_points_and_marks_degradation():
    with patch.object(evaluator,'complete_json',side_effect=RuntimeError('outage')):
        result=evaluator.evaluate_posts('TestProduct',{'customer_pain_points':[]},[{'post_id':'p1','title':'Need help','selftext':''}])
    assert result[0]['evaluation_method']=='heuristic'


@pytest.mark.parametrize('score,level', [(150,'high'),(45,'medium'),(35,'low'),('broken','irrelevant')])
def test_evaluator_validates_scores_and_intent(score,level):
    with patch.object(evaluator,'complete_json',return_value={'evaluations':[{'index':0,'relevance_score':score,'intent_level':'high'}]}):
        result=evaluator.evaluate_posts('TestProduct',{},[{'title':'TestProduct feedback'}], include_irrelevant=True)
    assert 0 <= result[0]['relevance_score'] <= 100
    assert result[0]['intent_level']==level


@pytest.fixture
def client():
    app=Flask('reddit-tests');app.config['TESTING']=True;app.register_blueprint(routes.bp)
    with patch('app.core.middleware.decode_token',return_value={'user_id':'owner'}),patch('app.auth.models.find_user_by_id',return_value={'_id':'owner'}),patch.object(storage,'get_feedback_preferences',return_value=[]):
        yield app.test_client()


HEADERS={'Authorization':'Bearer fixture'}


@pytest.mark.parametrize('payload', [[],{'product_name':123},{'product_name':'P','subreddits':'SaaS'}, {'product_name':'P','date_range':'yesterday'}])
def test_request_validation(client,payload):
    assert client.post('/api/reddit-leads/research',json=payload,headers=HEADERS).status_code==400


def test_route_counts_only_real_mentions_and_preserves_nonopportunity_mentions(client):
    profile={'competitors_and_alternatives':['A','B'],'search_queries':['support']}
    opportunity={'post_id':'p1','intent_level':'high','is_opportunity':True}
    mention={'post_id':'m1','intent_level':'irrelevant','is_opportunity':False,'is_brand_mention':True,'brand_sentiment':'Negative'}
    with patch.object(routes,'research_product',return_value=profile),patch.object(routes,'search_reddit_discussions',return_value=[]),patch.object(routes,'evaluate_posts',return_value=[opportunity,mention]),patch.object(routes,'batch_generate_comments',return_value=[opportunity]),patch.object(storage,'save_search_session',return_value={'search_id':'s1'}):
        response=client.post('/api/reddit-leads/research',json={'product_name':'TestProduct'},headers=HEADERS)
    data=response.get_json()
    assert response.status_code==201
    assert data['stats']['competitor_mentions_count']==0
    assert data['stats']['brand_mentions_count']==1
    assert data['sentiment_breakdown']=={'positive':0,'mixed':0,'neutral':0,'negative':1,'total':1}
    assert data['brand_sentiments']==[mention]


def test_feedback_and_engagement_check_ownership(client):
    with patch.object(storage,'save_feedback',return_value=False),patch.object(storage,'update_post',return_value=False):
        assert client.post('/api/reddit-leads/posts/p1/feedback',json={'search_id':'someone-elses','vote':'down'},headers=HEADERS).status_code==404
        assert client.post('/api/reddit-leads/posts/p1/engage',json={'search_id':'someone-elses'},headers=HEADERS).status_code==404


def test_feedback_persisted_with_user_and_reason(client):
    with patch.object(storage,'save_feedback',return_value=True) as save:
        response=client.post('/api/reddit-leads/posts/p1/feedback',json={'search_id':'s1','vote':'down','reason':'Wrong audience'},headers=HEADERS)
    assert response.status_code==200
    save.assert_called_once_with('owner','s1','p1','down','Wrong audience')


def test_regeneration_uses_owned_stored_context_and_persists(client):
    doc={'product_name':'StoredProduct','product_profile':{},'opportunities':[{'post_id':'p1','title':'Stored title'}]}
    with patch.object(storage,'get_search_session',return_value=doc),patch.object(routes,'generate_comment_drafts_for_post',return_value={'user_recommendation':'New reply'}) as generate,patch.object(storage,'update_post',return_value=True) as save:
        response=client.post('/api/reddit-leads/posts/p1/comment',json={'search_id':'s1','product_name':'ForgedProduct'},headers=HEADERS)
    assert response.status_code==200
    assert generate.call_args.kwargs['product_name']=='StoredProduct'
    assert generate.call_args.kwargs['post']['title']=='Stored title'
    assert save.call_args.args[:3]==('owner','s1','p1')


def test_failed_regeneration_reports_error_without_persisting(client):
    with patch.object(routes,'generate_comment_drafts_for_post',side_effect=RedditAIClientError('unavailable')):
        assert client.post('/api/reddit-leads/posts/p1/comment',json={'post':{}},headers=HEADERS).status_code==503


def test_feedback_is_passed_to_ai_scoring():
    profile={"feedback_preferences":[{"vote":"down","reason":"Wrong industry"}]}
    with patch.object(evaluator,"complete_json",return_value={"evaluations":[{"index":0,"relevance_score":40,"intent_level":"medium"}]}) as complete:
        evaluator.evaluate_posts("TestProduct",profile,[{"title":"Need a tool"}])
    assert "Wrong industry" in complete.call_args.args[0]


def test_large_evaluations_are_batched():
    def response(prompt,**kwargs):
        return {"evaluations":[{"index":i,"relevance_score":50,"intent_level":"medium"} for i in range(6 if '"post_id": "p6"' not in prompt else 1)]}
    posts=[{"post_id":"p"+str(i),"title":"Question"} for i in range(7)]
    with patch.object(evaluator,"complete_json",side_effect=response) as complete:
        result=evaluator.evaluate_posts("Product",{},posts)
    assert len(result)==7
    assert complete.call_count==2
