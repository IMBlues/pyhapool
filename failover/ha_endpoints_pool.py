# -*- coding: utf-8 -*-
import logging
import datetime
from threading import RLock
from contextlib import contextmanager
from typing import TypeVar, Any, List, NoReturn, Optional, Callable, Type, Iterable, Tuple
from dataclasses import dataclass, field

from .ha_algorithm import BasicHAAlgorithm
from .exceptions import NoEndpointAvailable
from .decorators import use_algo_as_default, raise_if_no_data, elect_if_no_active

logger = logging.getLogger(__name__)

THAEndpointsPool = TypeVar('THAEndpointsPool', bound='HAEndpointsPool')
THAAlgorithm = TypeVar('THAAlgorithm', bound='HAAlgorithmBase')


@dataclass
class HAEndpointsPool:
    """Endpoints pool which own high available features like failOver"""

    # for safety of thread
    _rlock = RLock()

    _active: Optional['Endpoint'] = None
    # all endpoint
    _all_pool: List['Endpoint'] = field(default_factory=list)
    # only include available endpoints
    _pool: List['Endpoint'] = field(default_factory=list)

    algorithm: THAAlgorithm = field(default_factory=BasicHAAlgorithm)

    success_score_delta: int = 1
    failure_score_delta: int = 50

    def __len__(self):
        """pool could be treat as available pool"""
        return len(self._pool)

    @classmethod
    def from_list(cls, raw_list: Optional[Iterable]) -> THAEndpointsPool:
        pool = cls()
        # generator always return True
        raw_list = list(raw_list)
        if not raw_list:
            raise ValueError("raw list can not be empty")

        # TODO: elements in list may be duplicate
        # Q: Why not use set() which is a easy way to deduplicate?
        # A: Raw object may not contain __hash__ (like default dataclass)
        for raw_endpoint in raw_list:
            pool.add(raw_endpoint)
        return pool

    @property
    def data(self) -> List:
        return self._pool

    @property
    def active(self) -> 'Endpoint':
        return self._active

    def add(self, raw_end_point: Any) -> NoReturn:
        """receive any type，mount on endpoint"""
        self._all_pool.append(Endpoint(raw=raw_end_point))
        self._pool.append(Endpoint(raw=raw_end_point))

    def add_endpoint(self, endpoint: 'Endpoint', available: bool = True) -> NoReturn:
        """add endpoint directly"""
        self._all_pool.append(endpoint)
        if available:
            self._pool.append(endpoint)

    @elect_if_no_active
    def fail(self, isolate_method: Callable[['Endpoint'], bool] = None, score_delta: int = None) -> NoReturn:
        """mark active endpoint as failure，and try to scan entire pool for isolating"""
        if not score_delta:
            score_delta = self.failure_score_delta

        with self._rlock:
            self._active.fail(score_delta=score_delta)
            # only isolate when fail
            self.try_to_isolate(method=isolate_method)

    @elect_if_no_active
    def succeed(self, score_delta: int = None) -> NoReturn:
        if not score_delta:
            score_delta = self.success_score_delta

        with self._rlock:
            self._active.succeed(score_delta=score_delta)

    @use_algo_as_default('isolate')
    def try_to_isolate(self, method: Callable[['Endpoint'], bool] = None) -> NoReturn:
        with self._rlock:
            # both copy.copy() and copy.deepcopy() are not thread safe!
            pool_copy = [x for x in self._pool]
            for ep in pool_copy:
                if method(ep):
                    self._pool.remove(ep)

        if not self._pool:
            raise NoEndpointAvailable("no Endpoint available in pool")

    def recovery(self):
        """recovery endpoints which is not in self._pool"""
        raise NotImplementedError

    def pick(self, elect_method: Callable[[List['Endpoint']], 'Endpoint'] = None) -> Any:
        """elect and pick raw data of active endpoint"""
        self.elect(elect_method)
        return self._active.raw

    @raise_if_no_data
    @use_algo_as_default('elect')
    def elect(self, method: Callable[[List['Endpoint']], 'Endpoint'] = None) -> NoReturn:
        """elect by elect_method and set active"""
        elected = method(self._pool)
        with self._rlock:
            self._active = elected
            logger.info(f"elect {elected.raw} as new active endpoint with score<{elected.score}>")

    @contextmanager
    def get_endpoint(self,
                     auto_reelect: bool = True,
                     isolate_method: Callable[['Endpoint'], bool] = None,
                     elect_method: Callable[[List['Endpoint']], 'Endpoint'] = None,
                     exempt_exceptions: Tuple[Type[Exception]] = None) -> Any:
        """
        use context manager to simplify failOver process

        :param auto_reelect: if auto reelect
        :param isolate_method: custom isolate method
        :param elect_method: custom elect method
        :param exempt_exceptions: exceptions which should not be mark as failure
        """
        try:
            if not self._active:
                self.elect()

            yield self._active.raw
        except Exception as e:
            exempt_exceptions = exempt_exceptions or ()
            if isinstance(e, exempt_exceptions):
                logger.info(f"endpoints pool got exception: {e}, "
                            f"but raising anyway according to upper caller")
                raise

            logger.warning(f"endpoints pool got exception: {e}, "
                           f"the active endpoint {self._active} will be mark as failure")
            self.fail(isolate_method)
            if auto_reelect:
                self.elect(method=elect_method)
        else:
            self.succeed()


@dataclass(order=True)
class Endpoint:
    raw: Any = field(compare=False)
    # score could extend for weight
    _score: int = 100
    success_count: int = 0
    failure_count: int = 0
    # for recovery
    last_failure_time: datetime.datetime = None

    def __repr__(self):
        return repr(self.raw) + f"-score<{self._score}>"

    def __hash__(self):
        return hash(repr(self))

    @property
    def score(self):
        return self._score

    def fail(self, score_delta: int = 0) -> NoReturn:
        """
        :param score_delta:
        :return: no return
        """
        self._update_score(score_delta=score_delta)
        self.last_failure_time = datetime.datetime.now()
        self.failure_count += 1

    def succeed(self, score_delta: int = 0) -> NoReturn:
        self._update_score(score_delta=score_delta, fail=False)
        self.success_count += 1

    def _update_score(self, score_delta: int, fail: bool = True):
        if score_delta < 0:
            raise ValueError("score delta should not be negative")

        if fail:
            self._score -= score_delta
        else:
            self._score += score_delta
