# -*- coding: utf-8 -*-
import functools

from .exceptions import NoEndpointAvailable


def use_algo_as_default(method_name):
    """use algorithm's method if no custom method pass in
    :param method_name: method name in algorithm class
    :return:
    """

    def _wrapper(func):
        @functools.wraps(func)
        def _wrapped(self, method=None, *args, **kwargs):
            if not method:
                # NOTE: the method param name is fixed(`method`)
                method = getattr(self.algorithm, method_name)
            return func(self, method, *args, **kwargs)
        return _wrapped

    return _wrapper


def elect_if_no_active_ep(func):
    """if there is no active endpoint, we will elect one before function
    """
    @functools.wraps(func)
    def _wrapped(self, *args, **kwargs):
        if not self.active:
            self.elect()
        return func(self, *args, **kwargs)
    return _wrapped


def raise_if_no_data(func):
    """raise NoEndpointAvailable if there is no data in pool
    """
    @functools.wraps(func)
    def _wrapped(self, *args, **kwargs):
        if not self.data:
            raise NoEndpointAvailable("no Endpoint available in pool")
        return func(self, *args, **kwargs)
    return _wrapped
