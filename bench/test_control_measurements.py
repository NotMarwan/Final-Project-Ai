from bench.run import summarize

def test_route_latencies_are_not_mixed():
    client={'requests':[{'route':'/set_threshold','status':200,'ms':10},{'route':'/set_cooldown','status':200,'ms':90},{'route':'/decision/config','status':200,'ms':30}]}
    result=summarize([],client,0,0,10)
    assert result['post_set_threshold_ms']['p50']==10
    assert result['control_routes_ms']['/set_cooldown']['p50']==90
    assert result['control_routes_ms']['/decision/config']['count']==1

def test_failed_control_is_not_counted_as_fast_success():
    client={'requests':[{'route':'/set_threshold','status':401,'ms':1},{'route':'/set_threshold','status':200,'ms':20}]}
    result=summarize([],client,0,0,10)
    assert result['post_set_threshold_ms']['count']==1
    assert result['post_set_threshold_ms']['p50']==20
    assert len(result['post_failures'])==1
