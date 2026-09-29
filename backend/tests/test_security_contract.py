import pytest
from starlette.requests import Request
from fastapi import HTTPException
from backend.security import AccessController, AccessConfig

def request(**headers):
    return Request({'type':'http','headers':[(key.encode(),value.encode()) for key,value in headers.items()]})

def test_claimed_admin_role_is_not_authorization():
    controller=AccessController(AccessConfig())
    with pytest.raises(HTTPException) as raised:controller.authorize(request(**{'x-user-role':'admin'}),'admin')
    assert raised.value.status_code==503

def test_wrong_key_fails_even_with_admin_header():
    controller=AccessController(AccessConfig('local-test-key'))
    with pytest.raises(HTTPException) as raised:controller.authorize(request(**{'x-api-key':'wrong','x-user-role':'admin'}),'admin')
    assert raised.value.status_code==401

def test_verified_key_has_server_assigned_role():
    controller=AccessController(AccessConfig('local-test-key'))
    assert controller.authorize(request(**{'x-api-key':'local-test-key','x-user-role':'invented'}),'admin')=='admin'

def test_open_read_access_cannot_mutate():
    controller=AccessController(AccessConfig())
    assert controller.authorize(request(),'viewer')=='viewer'
    with pytest.raises(HTTPException):controller.authorize(request(),'operator')
