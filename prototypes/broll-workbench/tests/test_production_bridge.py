import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from production_bridge import SizedReader, proxy_production


class Handler:
    def __init__(self,path='/api/production/projects',method='GET',body=b'',headers=None):
        self.path=path;self.command=method;self.rfile=io.BytesIO(body);self.wfile=io.BytesIO()
        self.headers=headers or {};self.body=body;self.sent=[];self.status=None;self.close_connection=False
    def content_length(self):return len(self.body)
    def send_response(self,status):self.status=status
    def send_header(self,k,v):self.sent.append((k,v))
    def end_headers(self):pass
    def send_json(self,status,payload):self.status=status;self.payload=payload


class Response:
    def __init__(self,body,status=200,headers=None):self.stream=io.BytesIO(body);self.status=status;self.headers=headers or {'Content-Length':str(len(body)),'Content-Type':'application/json'}
    def getheader(self,name):return self.headers.get(name)
    def read(self,size):return self.stream.read(size)


class Connection:
    def __init__(self,response):self.response=response;self.closed=False;self.requested=None
    def request(self,method,target,body=None,headers=None):self.requested=(method,target,body.read() if body else None,headers)
    def getresponse(self):return self.response
    def close(self):self.closed=True


class ProductionBridgeTests(unittest.TestCase):
    def test_only_fixed_local_destination_and_no_browser_credentials_forwarded(self):
        handler=Handler('/api/production/projects?kind=source','POST',b'{"name":"x"}',{'Origin':'http://127.0.0.1:4182','Cookie':'private','Content-Type':'application/json'})
        connection=Connection(Response(b'{"project":{}}',201))
        with patch('production_bridge.http.client.HTTPConnection',return_value=connection) as factory:proxy_production(handler)
        factory.assert_called_once_with('127.0.0.1',4183,timeout=180)
        method,target,body,headers=connection.requested
        self.assertEqual(target,'/api/projects?kind=source');self.assertEqual(body,b'{"name":"x"}')
        self.assertNotIn('Origin',headers);self.assertNotIn('Cookie',headers)
        self.assertEqual(handler.status,201);self.assertTrue(connection.closed)
    def test_range_and_binary_response_pass_through_without_json_reencoding(self):
        handler=Handler('/api/production/media/'+'a'*64,headers={'Range':'bytes=0-3'})
        connection=Connection(Response(b'\x00\xff\x01\x02',206,{'Content-Type':'video/mp4','Content-Length':'4','Content-Range':'bytes 0-3/100'}))
        with patch('production_bridge.http.client.HTTPConnection',return_value=connection):proxy_production(handler)
        self.assertEqual(handler.wfile.getvalue(),b'\x00\xff\x01\x02');self.assertEqual(handler.status,206)
        self.assertIn(('Content-Range','bytes 0-3/100'),handler.sent)
    def test_unavailable_engine_is_recoverable_and_does_not_modify_library(self):
        handler=Handler()
        with patch('production_bridge.http.client.HTTPConnection',side_effect=ConnectionRefusedError):
            # Construction occurs before request try; ordinary refusal is raised by request instead.
            with self.assertRaises(ConnectionRefusedError):proxy_production(handler)
        connection=Connection(Response(b''))
        with patch.object(connection,'request',side_effect=ConnectionRefusedError),patch('production_bridge.http.client.HTTPConnection',return_value=connection):proxy_production(handler)
        self.assertEqual(handler.status,503);self.assertEqual(handler.payload['code'],'production_unavailable')
    def test_upload_reader_never_consumes_the_next_keepalive_request(self):
        stream=io.BytesIO(b'ABCnext-request');reader=SizedReader(stream,3)
        self.assertEqual(reader.read(65536),b'ABC');self.assertEqual(reader.read(),b'');self.assertEqual(stream.read(),b'next-request')
        with self.assertRaises(ValueError):SizedReader(io.BytesIO(b''),3).read()
    def test_path_cannot_select_arbitrary_upstream(self):
        for path in ['/api/production/../status','https://example.com','/api/production/']:
            with self.assertRaises(ValueError):proxy_production(Handler(path))


if __name__=='__main__':unittest.main()
