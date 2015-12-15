# -*- coding: utf-8 -*-
"""
SOCKS support for urllib3
~~~~~~~~~~~~~~~~~~~~~~~~~

This contrib module contains provisional support for SOCKS proxies from within
urllib3.
"""
import socks

from socket import error as SocketError, timeout as SocketTimeout

from urllib3.connection import (
    HTTPConnection, HTTPSConnection, VerifiedHTTPSConnection
)
from urllib3.connectionpool import (
    HTTPConnectionPool, HTTPSConnectionPool
)
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
from urllib3.poolmanager import PoolManager
from urllib3.util.url import parse_url

try:
    import ssl
except ImportError:
    ssl = None


class SOCKSConnection(HTTPConnection):
    """
    A plain-text HTTP connection that connects via a SOCKS proxy.
    """
    def __init__(self, *args, **kwargs):
        self._socks_options = kwargs.pop('_socks_options')
        super(SOCKSConnection, self).__init__(*args, **kwargs)

    def _new_conn(self):
        """
        Establish a new connection via the SOCKS proxy.
        """
        # TODO: This is a duplicate of HTTPConnection._new_conn but with a
        # different callable for create_connection. Consider a refactor that
        # allows us to strip that out.
        extra_kw = {}
        if self.source_address:
            extra_kw['source_address'] = self.source_address

        if self.socket_options:
            extra_kw['socket_options'] = self.socket_options

        try:
            conn = socks.create_connection(
                (self.host, self.port),
                proxy_type=self._socks_options['socks_version'],
                proxy_addr=self._socks_options['proxy_host'],
                proxy_port=self._socks_options['proxy_port'],
                proxy_username=self._socks_options['username'],
                proxy_password=self._socks_options['password'],
                timeout=self.timeout,
                **extra_kw
            )

        except SocketTimeout as e:
            raise ConnectTimeoutError(
                self, "Connection to %s timed out. (connect timeout=%s)" %
                (self.host, self.timeout))

        except SocketError as e:
            raise NewConnectionError(
                self, "Failed to establish a new connection: %s" % e)

        return conn


class SOCKSHTTPSConnection(SOCKSConnection, HTTPSConnection):
    pass


class VerifiedSOCKSHTTPSConnection(SOCKSConnection, VerifiedHTTPSConnection):
    pass


class SOCKSHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = SOCKSConnection


class SOCKSHTTPSConnectionPool(HTTPSConnectionPool):
    if ssl:
        ConnectionCls = VerifiedSOCKSHTTPSConnection
    else:
        ConnectionCls = SOCKSHTTPSConnection


class SOCKSProxyManager(PoolManager):
    """
    A version of the urllib3 ProxyManager that routes connections via the
    defined SOCKS proxy.
    """
    pool_classes_by_scheme = {
        'http': SOCKSHTTPConnectionPool,
        'https': SOCKSHTTPSConnectionPool,
    }

    def __init__(self, proxy_url, username=None, password=None,
                 num_pools=10, headers=None, **connection_pool_kw):
        parsed = parse_url(proxy_url)

        if parsed.scheme == 'socks5':
            socks_version = socks.PROXY_TYPE_SOCKS5
        elif parsed.scheme == 'socks4':
            socks_version = socks.PROXY_TYPE_SOCKS4
        else:
            raise ValueError(
                "Unable to determine SOCKS version from %s" % proxy_url
            )

        self.proxy_url = proxy_url

        socks_options = {
            'socks_version': socks_version,
            'proxy_host': parsed.host,
            'proxy_port': parsed.port,
            'username': username,
            'password': password,
        }
        connection_pool_kw['_socks_options'] = socks_options

        super(SOCKSProxyManager, self).__init__(
            num_pools, headers, **connection_pool_kw
        )
